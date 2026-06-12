#!/usr/bin/env python3
"""
Test the RunPod handler locally with your own video and audio files.

Usage:
  python test_handler.py /path/to/video.mp4 /path/to/audio.wav
"""

import sys
import os
import json
import base64
from pathlib import Path

# We don't actually import the handler for testing.
# Instead, we test the core pipeline directly.


def test_with_local_files(video_path: str, audio_path: str):
    """Test the core inference pipeline with local video and audio files."""

    video_path = Path(video_path).resolve()
    audio_path = Path(audio_path).resolve()

    if not video_path.exists():
        print(f"Error: Video file not found: {video_path}")
        sys.exit(1)
    if not audio_path.exists():
        print(f"Error: Audio file not found: {audio_path}")
        sys.exit(1)

    print(f"Testing inference pipeline with:")
    print(f"  Video: {video_path}")
    print(f"  Audio: {audio_path}")
    print()

    # Test the core pipeline using the inference script approach
    from omegaconf import OmegaConf
    import torch
    from diffusers import AutoencoderKL, DDIMScheduler
    from latentsync.models.unet import UNet3DConditionModel
    from latentsync.pipelines.lipsync_pipeline import LipsyncPipeline
    from latentsync.whisper.audio2feature import Audio2Feature
    from accelerate.utils import set_seed

    config_path = "configs/unet/stage2.yaml"
    ckpt_path = "checkpoints/latentsync_unet.pt"

    if not Path(ckpt_path).exists():
        print(f"Error: Checkpoint not found at {ckpt_path}")
        print("Please download the model weights first.")
        sys.exit(1)

    config = OmegaConf.load(config_path)

    is_fp16 = torch.cuda.is_available() and torch.cuda.get_device_capability()[0] > 7
    dtype = torch.float16 if is_fp16 else torch.float32

    print(f"Using dtype: {dtype}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    print()

    scheduler = DDIMScheduler.from_pretrained("configs")

    whisper_path = (
        "checkpoints/whisper/small.pt"
        if config.model.cross_attention_dim == 768
        else "checkpoints/whisper/tiny.pt"
    )

    print("Loading audio encoder...")
    audio_encoder = Audio2Feature(
        model_path=whisper_path,
        device="cuda",
        num_frames=config.data.num_frames,
        audio_feat_length=config.data.audio_feat_length,
    )

    print("Loading VAE...")
    vae = AutoencoderKL.from_pretrained("stabilityai/sd-vae-ft-mse", torch_dtype=dtype)
    vae.config.scaling_factor = 0.18215
    vae.config.shift_factor = 0

    print("Loading UNet...")
    unet, _ = UNet3DConditionModel.from_pretrained(
        OmegaConf.to_container(config.model),
        ckpt_path,
        device="cpu",
    )
    unet = unet.to(dtype=dtype)

    print("Building pipeline...")
    pipeline = LipsyncPipeline(
        vae=vae,
        audio_encoder=audio_encoder,
        unet=unet,
        scheduler=scheduler,
    ).to("cuda")

    output_path = "test_output.mp4"
    seed = 42

    print(f"Running inference (seed={seed})...")
    set_seed(seed)
    pipeline(
        video_path=str(video_path),
        audio_path=str(audio_path),
        video_out_path=output_path,
        num_frames=config.data.num_frames,
        num_inference_steps=20,
        guidance_scale=2.0,
        weight_dtype=dtype,
        width=config.data.resolution,
        height=config.data.resolution,
        mask_image_path=config.data.mask_image_path,
    )

    if Path(output_path).exists():
        size_mb = Path(output_path).stat().st_size / (1024 * 1024)
        print(f"✓ Success! Output saved to: {output_path} ({size_mb:.1f} MB)")
    else:
        print("✗ Failed: Output file not created")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python test_handler.py <video_path> <audio_path>")
        print()
        print("Example:")
        print("  python test_handler.py input.mp4 audio.wav")
        sys.exit(1)

    test_with_local_files(sys.argv[1], sys.argv[2])
