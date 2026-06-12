import os
import base64
import tempfile
import random

import requests
import torch
import runpod
from omegaconf import OmegaConf
from diffusers import AutoencoderKL, DDIMScheduler
from accelerate.utils import set_seed

from latentsync.models.unet import UNet3DConditionModel
from latentsync.pipelines.lipsync_pipeline import LipsyncPipeline
from latentsync.whisper.audio2feature import Audio2Feature

CONFIG_PATH = os.environ.get("UNET_CONFIG_PATH", "configs/unet/stage2.yaml")
CKPT_PATH = os.environ.get("CKPT_PATH", "checkpoints/latentsync_unet.pt")

_pipeline = None
_config = None


def _load_pipeline():
    global _pipeline, _config

    if _pipeline is not None:
        return _pipeline, _config

    _config = OmegaConf.load(CONFIG_PATH)

    is_fp16 = torch.cuda.is_available() and torch.cuda.get_device_capability()[0] > 7
    dtype = torch.float16 if is_fp16 else torch.float32

    scheduler = DDIMScheduler.from_pretrained("configs")

    # Use model name instead of path; Audio2Feature will auto-download if needed
    whisper_model_name = (
        "small"
        if _config.model.cross_attention_dim == 768
        else "tiny"
    )

    os.makedirs("checkpoints/whisper", exist_ok=True)
    audio_encoder = Audio2Feature(
        model_path=whisper_model_name,
        device="cuda",
        num_frames=_config.data.num_frames,
        audio_feat_length=_config.data.audio_feat_length,
    )

    vae = AutoencoderKL.from_pretrained("stabilityai/sd-vae-ft-mse", torch_dtype=dtype)
    vae.config.scaling_factor = 0.18215
    vae.config.shift_factor = 0

    unet, _ = UNet3DConditionModel.from_pretrained(
        OmegaConf.to_container(_config.model),
        CKPT_PATH,
        device="cpu",
    )
    unet = unet.to(dtype=dtype)

    _pipeline = LipsyncPipeline(
        vae=vae,
        audio_encoder=audio_encoder,
        unet=unet,
        scheduler=scheduler,
    ).to("cuda")

    # Soft-link auxiliary VGG weights expected by lpips
    vgg_src = os.path.abspath("checkpoints/auxiliary/vgg16-397923af.pth")
    vgg_dst = os.path.expanduser("~/.cache/torch/hub/checkpoints/vgg16-397923af.pth")
    if os.path.exists(vgg_src) and not os.path.lexists(vgg_dst):
        os.makedirs(os.path.dirname(vgg_dst), exist_ok=True)
        os.symlink(vgg_src, vgg_dst)

    return _pipeline, _config


def _download(url: str, suffix: str) -> str:
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(r.content)
    return path


def handler(job):
    inp = job["input"]

    video_url = inp.get("video_url")
    audio_url = inp.get("audio_url")
    if not video_url or not audio_url:
        return {"error": "video_url and audio_url are required"}

    if not os.path.exists(CKPT_PATH):
        return {
            "error": f"Checkpoint not found at {CKPT_PATH}. "
            "Mount it via RunPod Network Volume or set CKPT_PATH env var to the absolute path."
        }

    guidance_scale = float(inp.get("guidance_scale", 2.0))
    inference_steps = int(inp.get("inference_steps", 20))
    seed = int(inp.get("seed", 0))
    if seed <= 0:
        seed = random.randint(1, 65535)

    pipe, config = _load_pipeline()

    dtype = torch.float16 if torch.cuda.get_device_capability()[0] > 7 else torch.float32

    video_path = audio_path = output_path = None
    try:
        video_path = _download(video_url, ".mp4")
        audio_path = _download(audio_url, ".wav")

        fd, output_path = tempfile.mkstemp(suffix=".mp4")
        os.close(fd)

        set_seed(seed)
        pipe(
            video_path=video_path,
            audio_path=audio_path,
            video_out_path=output_path,
            num_frames=config.data.num_frames,
            num_inference_steps=inference_steps,
            guidance_scale=guidance_scale,
            weight_dtype=dtype,
            width=config.data.resolution,
            height=config.data.resolution,
            mask_image_path=config.data.mask_image_path,
        )

        with open(output_path, "rb") as f:
            video_b64 = base64.b64encode(f.read()).decode("utf-8")

        return {"video_base64": video_b64, "seed": seed}

    finally:
        for p in (video_path, audio_path, output_path):
            if p and os.path.exists(p):
                os.remove(p)


runpod.serverless.start({"handler": handler})
