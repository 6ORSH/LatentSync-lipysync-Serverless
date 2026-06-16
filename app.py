import runpod
import uuid
import os
import base64
import logging
import shutil
import torch
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from utils.s3 import download_key, download_url, upload_key, presigned_get
from utils.utllity import load_environment, get_audio_duration
from utils.video import load_pipe, generate_lipsync
from utils.caption_burn import burn_captions_with_audio_gpu
from utils.randomizer import RandomizedVideoSampler

logging.basicConfig(level=logging.INFO)

# -------------------------
# Checkpoints on RunPod Network Volume
# -------------------------
# In serverless the Network Volume is mounted at /runpod-volume, but both
# utils/video.py and insightface's FaceDetector (root="checkpoints/auxiliary")
# expect the weights under /app/checkpoints. Link them if the volume is present
# so nothing has to change in the rest of the code. No-op for local runs or
# when checkpoints are baked into the image.

def _link_checkpoints():
    volume_ckpt = Path("/runpod-volume/checkpoints")
    local_ckpt = Path("/app/checkpoints")
    if volume_ckpt.exists() and not local_ckpt.exists():
        local_ckpt.symlink_to(volume_ckpt, target_is_directory=True)
        logging.info(f"🔗 Linked {local_ckpt} -> {volume_ckpt}")


_link_checkpoints()

# -------------------------
# Global initialization
# -------------------------

_ = load_pipe()  # preload LatentSync (GPU)
SEED = 1247

video_randomizer = RandomizedVideoSampler(
    resize_factor=1,
    seed=None
)

# Thread pool for IO + CPU work
io_pool = ThreadPoolExecutor(max_workers=3)


# -------------------------
# Handler
# -------------------------

def handler(event):
    workdir = None

    try:
        payload = event["input"]
        inp_meta_list = payload["inp_meta"]
        level = payload.get("level")
        user_id = payload.get("user_id", "anon")

        # Optional per-job quality/speed knobs (fall back to model defaults).
        inference_steps = int(payload.get("inference_steps", 20))
        guidance_scale = float(payload.get("guidance_scale", 1.5))

        results = []

        # ---- Environment selection ----
        # "test"  = infra-free smoke test: inputs are public http(s) URLs,
        #           output is returned inline as base64 (no R2 needed).
        # "local" = local file paths, no upload.
        # else    = R2: inputs are object keys, results uploaded to R2.
        if level not in ("local", "test"):
            level = level or "stag"
            load_environment(level)

        # ---- Working directory ----
        workdir = Path("/tmp") / str(uuid.uuid4())
        workdir.mkdir(parents=True, exist_ok=True)

        # =============================
        # Loop over reference videos
        # =============================
        for meta in inp_meta_list:
            ref_video_path = meta["ref_video_path"]
            cc_enabled = meta.get("cc", False)
            audio_meta_list = meta["ref_audio_meta"]

            meta_outputs = []

            # ---- Download ref video ONCE ----
            ref_dir = workdir / "ref"
            ref_dir.mkdir(exist_ok=True)

            local_ref_video = ref_dir / "ref.mp4"

            if level == "local":
                local_ref_video = Path(ref_video_path)
            elif level == "test":
                logging.info("⬇️ Downloading reference video (test URL)")
                download_url(ref_video_path, str(local_ref_video))
            else:
                logging.info("⬇️ Downloading reference video (R2)")
                download_key(ref_video_path, str(local_ref_video))

            # =============================
            # Loop over audios
            # =============================
            for audio_meta in audio_meta_list:
                audio_path = audio_meta["audio_path"]
                srt_path = audio_meta.get("srt_path")

                job_id = str(uuid.uuid4())
                job_dir = workdir / job_id
                job_dir.mkdir(parents=True, exist_ok=True)

                local_audio = job_dir / "input.wav"
                local_srt = job_dir / "subs.srt"

                randomized_video = job_dir / "randomized_input.mp4"
                lipsync_out = job_dir / "lipsync.mp4"
                final_out = job_dir / "final.mp4"
                temp_dir = job_dir / "temp"

                # ---- Download audio / srt ----
                if level == "local":
                    local_audio = Path(audio_path)
                    if srt_path:
                        local_srt = Path(srt_path)
                elif level == "test":
                    download_url(audio_path, str(local_audio))
                    if srt_path:
                        download_url(srt_path, str(local_srt))
                else:
                    download_key(audio_path, str(local_audio))
                    if srt_path:
                        download_key(srt_path, str(local_srt))

                # ---- Randomize video (ASYNC, CPU) ----
                logging.info("🎲 Randomizing reference video")
                duration = get_audio_duration(local_audio) or 5

                randomize_future = io_pool.submit(
                    video_randomizer.generate_randomized_video,
                    input_video=str(local_ref_video),
                    output_video=str(randomized_video),
                    duration_seconds=duration
                )

                # ---- Wait before GPU ----
                randomize_future.result()

                # ---- Lip-sync (GPU, SEQUENTIAL) ----
                logging.info("🎬 Generating lip-sync")
                generate_lipsync(
                    video_path=str(randomized_video),
                    audio_path=str(local_audio),
                    output_path=str(lipsync_out),
                    temp_dir=str(temp_dir),
                    seed=SEED,
                    inference_steps=inference_steps,
                    guidance_scale=guidance_scale,
                )

                # ---- Caption burn (GPU, optional) ----
                if cc_enabled and srt_path:
                    logging.info("📝 Burning captions")
                    burn_captions_with_audio_gpu(
                        input_video=str(lipsync_out),
                        srt_path=str(local_srt),
                        output_video=str(final_out),
                    )
                    upload_target = final_out
                else:
                    upload_target = lipsync_out

                # ---- Deliver result ----
                output_encoding = None
                output_url = None
                if level == "local":
                    output_video = str(upload_target)
                elif level == "test":
                    # Return the rendered video inline as base64 (no R2).
                    with open(upload_target, "rb") as f:
                        output_video = base64.b64encode(f.read()).decode("utf-8")
                    output_encoding = "base64"
                else:
                    out_key = f"outputs/{user_id}/{job_id}/result.mp4"
                    upload_future = io_pool.submit(
                        upload_key,
                        str(upload_target),
                        out_key
                    )
                    output_video = upload_future.result()
                    output_url = presigned_get(out_key)

                meta_outputs.append({
                    "audio_path": audio_path,
                    "srt_path": srt_path,
                    "output_video": output_video,   # R2 key (or base64 / local path)
                    "output_url": output_url,        # presigned GET (None for test/local)
                    "output_encoding": output_encoding,
                    "cc_applied": cc_enabled and bool(srt_path),
                })

            results.append({
                "ref_video_path": ref_video_path,
                "outputs": meta_outputs,
            })

        return {
            "status": "success",
            "results": results,
        }

    except Exception as e:
        logging.exception("❌ Pipeline failed")
        return {"error": str(e)}

    finally:
        # ---- Cleanup ----
        if workdir and workdir.exists():
            shutil.rmtree(workdir, ignore_errors=True)
        torch.cuda.empty_cache()


# -------------------------
# RunPod entry
# -------------------------

runpod.serverless.start({"handler": handler})
