import runpod
import os
import json
import uuid
import base64
import glob
import shutil
import logging
import subprocess
from pathlib import Path

from serverless_r2 import (
    download_key,
    download_url,
    upload_key,
    presigned_get,
    set_bucket_for_level,
)

logging.basicConfig(level=logging.INFO)

# --- KeySync inference invariants (run from the repo root, /app) ---
REPO = "/app"
KEYFRAMES_CKPT = "pretrained_models/checkpoints/keyframe_dub.pt"
INTERPOLATION_CKPT = "pretrained_models/checkpoints/interpolation_dub.pt"
MODEL_CONFIG = "scripts/sampling/configs/interpolation.yaml"
MODEL_KEYFRAMES_CONFIG = "scripts/sampling/configs/keyframe.yaml"


def _run(cmd, **kw):
    logging.info("$ %s", " ".join(cmd))
    subprocess.run(cmd, check=True, **kw)


def _run_capture(cmd, **kw):
    """Like _run but captures output; on failure raises RuntimeError with the tail."""
    logging.info("$ %s", " ".join(cmd))
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, **kw)
    if r.stdout:
        logging.info(r.stdout.strip()[-2000:])
    if r.returncode != 0:
        tail = "\n".join((r.stdout or "").strip().splitlines()[-15:])
        raise RuntimeError(tail or f"command failed (exit {r.returncode})")


def _standardize_video(src: str, dst: str):
    # KeySync reads raw frames and resizes to 512x512 internally; just normalise fps.
    _run(["ffmpeg", "-y", "-nostdin", "-i", src, "-r", "25", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", dst])


def _standardize_audio(src: str, dst: str):
    _run(["ffmpeg", "-y", "-nostdin", "-i", src, "-ar", "16000", "-ac", "1", dst])


def _probe(path: str, kind: str):
    """Fail fast with a clear message if the input isn't a readable media file."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError(
            f"input {kind} is unreadable or corrupt "
            f"(re-upload a complete file): {r.stderr.strip() or 'ffprobe failed'}"
        )


def handler(event):
    workdir = None
    try:
        payload = event["input"]
        level = payload.get("level", "stag")
        user_id = payload.get("user_id", "anon")
        # Backend sends flat keys for keysync (see backend/src/routes/jobs.ts).
        video_in = payload["video_key"]
        audio_in = payload["audio_key"]
        # Optional per-job knobs (backend validates; defaults match upstream).
        fix_occlusion = bool(payload.get("fix_occlusion", False))
        compute_until = payload.get("compute_until")  # seconds (int) or None -> whole clip
        position = payload.get("position")  # [x, y] in ORIGINAL coords (occluder point) or None
        start_frame = int(payload.get("start_frame", 0))  # frame where the occluder is annotated

        if level not in ("local", "test"):
            set_bucket_for_level(level)

        job_id = str(uuid.uuid4())
        workdir = Path("/tmp") / job_id
        (workdir / "out").mkdir(parents=True, exist_ok=True)

        raw_video = str(workdir / "raw_video.mp4")
        raw_audio = str(workdir / "raw_audio.wav")
        video_25 = str(workdir / "video.mp4")
        video_cropped = str(workdir / "video_cropped.mp4")
        crop_json = str(workdir / "crop_data.json")
        landmarks_npy = str(workdir / "landmarks.npy")
        pasted_video = str(workdir / "pasted.mp4")
        final_out = str(workdir / "final.mp4")
        audio_16 = str(workdir / "audio.wav")
        out_dir = str(workdir / "out")

        # ---- Fetch inputs ----
        if level == "local":
            raw_video, raw_audio = video_in, audio_in
        elif level == "test":
            logging.info("⬇️ Downloading inputs (test URLs)")
            download_url(video_in, raw_video)
            download_url(audio_in, raw_audio)
        else:
            logging.info("⬇️ Downloading inputs (R2)")
            download_key(video_in, raw_video)
            download_key(audio_in, raw_audio)

        # ---- Validate inputs (clear error instead of a deep ffmpeg failure) ----
        _probe(raw_video, "video")
        _probe(raw_audio, "audio")

        # ---- Normalise (25 fps / 16 kHz mono) ----
        _standardize_video(raw_video, video_25)
        _standardize_audio(raw_audio, audio_16)

        # ---- Face-crop to a square (KeySync expects a face-centered clip;
        #      without it the whole frame is squished to 512x512 -> no lip-sync). ----
        logging.info("✂️ Cropping to face")
        try:
            _run_capture(["python", "preprocess_crop.py", video_25, video_cropped, crop_json, landmarks_npy], cwd=REPO)
        except RuntimeError as e:
            if "no face detected" in str(e):
                raise RuntimeError(
                    "no clear face detected — KeySync needs a single, clearly visible, "
                    "roughly frontal face (multi-person / wide shots are not supported)"
                )
            raise

        # ---- Occlusion: map the user's occluder point (original coords) into the
        #      512x512 crop space (sam2 runs on the cropped clip). Occlusion only
        #      runs when a position is supplied — without it sam2 crashes. ----
        position_crop = None
        if fix_occlusion and position is not None:
            # Manual occluder point (ORIGINAL coords) -> 512x512 crop space.
            with open(crop_json) as f:
                crop = json.load(f)
            sf = max(0, min(start_frame, len(crop) - 1))
            x0, y0, x1, y1 = crop[sf]
            bw, bh = max(1, x1 - x0), max(1, y1 - y0)
            cx = (float(position[0]) - x0) * 512.0 / bw
            cy = (float(position[1]) - y0) * 512.0 / bh
            position_crop = [round(cx, 1), round(cy, 1)]
            logging.info("🩹 Occlusion (manual): orig %s @frame %d -> crop %s", position, sf, position_crop)
        elif fix_occlusion:
            # Auto-occlusion needs a class-agnostic, semantic detector (SAM3) — skin
            # heuristics flag beards/brows/open-mouth, and the old MediaPipe path was
            # hand-only + broken. Until SAM3 (roadmap Phase 6), occlusion requires a
            # manual `position`. Run WITHOUT occlusion instead of guessing wrong.
            logging.info("fix_occlusion requested without a position — auto-detect is "
                         "not available (needs SAM3); running WITHOUT occlusion")
        effective_fix = position_crop is not None

        # ---- Run KeySync dubbing pipeline ----
        logging.info("🎬 Running KeySync dubbing pipeline (fix_occlusion=%s)", effective_fix)
        cmd = [
            "python", "scripts/sampling/dubbing_pipeline_raw.py",
            f"--filelist={video_cropped}",
            f"--filelist_audio={audio_16}",
            f"--output_folder={out_dir}",
            f"--keyframes_ckpt={KEYFRAMES_CKPT}",
            f"--interpolation_ckpt={INTERPOLATION_CKPT}",
            f"--model_config={MODEL_CONFIG}",
            f"--model_keyframes_config={MODEL_KEYFRAMES_CONFIG}",
            "--audio_emb_type=hubert",
            "--recompute=True",
            "--add_zero_flag=True",
            "--chunk_size=2",
            "--decoding_t=1",
            # Match upstream infer_raw.sh exactly (these drive classifier-free
            # guidance / conditioning — code defaults degraded quality vs README).
            "--cond_aug=0.",
            "--resize_size=512",
            "--force_uc_zero_embeddings=[cond_frames,audio_emb]",
            # Per-job knob: occlusion handling (hand/object over the face) via SAM2.
            # Enabled only when an occluder position was supplied + mapped above.
            f"--fix_occlusion={effective_fix}",
        ]
        if effective_fix:
            cmd.append(f"--position=[{position_crop[0]},{position_crop[1]}]")
            cmd.append(f"--start_frame={start_frame}")
        # Per-job knob: cap processing length (seconds). Omit -> whole clip.
        if compute_until is not None:
            cmd.append(f"--compute_until={compute_until}")
        _run(cmd, cwd=REPO)

        # ---- Locate output mp4 (512x512 face crop) ----
        produced = sorted(glob.glob(os.path.join(out_dir, "*.mp4")), key=os.path.getmtime)
        if not produced:
            raise RuntimeError(f"KeySync produced no output video in {out_dir}")
        keysync_out = produced[-1]

        # ---- Paste the generated face back into the original frames (full size) ----
        logging.info("🖼️ Pasting result back into the original frame")
        _run(["python", "paste_back.py", video_25, keysync_out, crop_json, pasted_video, landmarks_npy], cwd=REPO)
        # Mux the dubbed audio from KeySync's output onto the composited video.
        _run([
            "ffmpeg", "-y", "-nostdin", "-i", pasted_video, "-i", keysync_out,
            "-map", "0:v:0", "-map", "1:a:0?",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", final_out,
        ])
        result = final_out

        # ---- Deliver ----
        output_encoding = None
        output_url = None
        if level == "local":
            output_video = result
        elif level == "test":
            with open(result, "rb") as f:
                output_video = base64.b64encode(f.read()).decode("utf-8")
            output_encoding = "base64"
        else:
            out_key = f"outputs/{user_id}/{job_id}/result.mp4"
            output_video = upload_key(result, out_key)
            output_url = presigned_get(out_key)

        return {
            "status": "success",
            "model": "keysync",
            "results": [
                {
                    "output_video": output_video,
                    "output_url": output_url,
                    "output_encoding": output_encoding,
                }
            ],
        }

    except subprocess.CalledProcessError as e:
        logging.exception("❌ KeySync subprocess failed")
        return {"error": f"keysync pipeline failed (exit {e.returncode})"}
    except Exception as e:
        logging.exception("❌ KeySync job failed")
        return {"error": str(e)}
    finally:
        if workdir and workdir.exists():
            shutil.rmtree(workdir, ignore_errors=True)


runpod.serverless.start({"handler": handler})
