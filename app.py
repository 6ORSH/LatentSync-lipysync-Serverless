import runpod
import uuid
import os
import base64
import logging
import shutil
import torch
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from utils.s3 import download_file, upload_file
from utils.utllity import load_environment, classify_env, get_audio_duration
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

        results = []

        # ---- Environment selection ----
        # "test" = infra-free smoke test: inputs are public http(s) URLs,
        # output is returned inline as base64 (no AWS / S3 needed).
        if level not in ("local", "test"):
            ref_video_path = inp_meta_list[0]["ref_video_path"]
            if not level and ref_video_path:
                parts = ref_video_path.split("/")
                level = classify_env(parts[2]) if len(parts) > 2 else None
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
            else:
                logging.info("⬇️ Downloading reference video")
                download_file(ref_video_path, str(local_ref_video))

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
                else:
                    download_file(audio_path, str(local_audio))
                    if srt_path:
                        download_file(srt_path, str(local_srt))

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
                if level == "local":
                    s3_output = str(upload_target)
                elif level == "test":
                    # Return the rendered video inline as base64 (no S3).
                    with open(upload_target, "rb") as f:
                        s3_output = base64.b64encode(f.read()).decode("utf-8")
                    output_encoding = "base64"
                else:
                    s3_key = f"video_gen/latentsync/{job_id}.mp4"
                    upload_future = io_pool.submit(
                        upload_file,
                        str(upload_target),
                        s3_key
                    )
                    s3_output = upload_future.result()

                meta_outputs.append({
                    "audio_path": audio_path,
                    "srt_path": srt_path,
                    "output_video": s3_output,
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
