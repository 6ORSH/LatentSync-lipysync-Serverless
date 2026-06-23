"""Face-crop a video for KeySync, using the repo's own utilities.

KeySync's dubbing_pipeline_raw.py does NOT crop — it resizes the whole frame to
512x512, so a wide/non-square input gets squished and produces no lip-sync +
artifacts. Their intended preprocessing crops a square region around the face
(scripts/util/gen_landmarks.py -> crop_video.py -> VideoPreProcessor). We do the
same in-process here, then feed the cropped clip to the pipeline.

Usage:  python preprocess_crop.py <in_video.mp4> <out_video_cropped.mp4> <out_crop_data.json>
The crop_data JSON (per-frame [x_start, y_start, x_end, y_end]) lets paste_back.py
composite the generated face back into the original full-resolution frames.
Run from /app with PYTHONPATH=/app.
"""

import sys
import json
import cv2
import numpy as np
import torch
from torchvision.io import write_video
from einops import rearrange

from scripts.util.landmarks_extractor import LandmarksExtractor
from scripts.util.video_processor import VideoPreProcessor


def _read_rgb_frames(path):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError(f"could not open video {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frames = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    cap.release()
    if not frames:
        raise RuntimeError(f"no frames decoded from {path}")
    return frames, float(fps)


def _extract_landmarks(frames, extractor, batch_size=16):
    """Per-frame 68x2 landmarks with nearest-valid fallback (mirrors gen_landmarks.py)."""
    raw = []
    for i in range(0, len(frames), batch_size):
        batch = torch.from_numpy(np.array(frames[i : i + batch_size])).permute(0, 3, 1, 2)
        raw.extend(extractor.extract_landmarks(batch))

    cleaned = []
    for lm in raw:
        if isinstance(lm, list):
            lm = lm[0] if lm else None
        cleaned.append(lm if (lm is not None and getattr(lm, "shape", None) == (68, 2)) else None)

    if all(lm is None for lm in cleaned):
        raise RuntimeError("no face detected in the input video")

    # forward fill, then backward fill leading Nones
    last = None
    for i in range(len(cleaned)):
        if cleaned[i] is None:
            cleaned[i] = last
        else:
            last = cleaned[i]
    nxt = None
    for i in range(len(cleaned) - 1, -1, -1):
        if cleaned[i] is None:
            cleaned[i] = nxt
        else:
            nxt = cleaned[i]
    return np.stack(cleaned).astype(np.float32)


def main(in_path, out_path, crop_json_path, landmarks_npy_path=None):
    frames, fps = _read_rgb_frames(in_path)
    video = torch.from_numpy(np.array(frames)).permute(0, 3, 1, 2)  # T,C,H,W uint8

    extractor = LandmarksExtractor(device="cuda" if torch.cuda.is_available() else "cpu")
    landmarks = _extract_landmarks(frames, extractor)  # (T,68,2) in ORIGINAL pixel coords

    # Save original-coords landmarks so paste_back can blend only the lower face
    # (mouth/chin) and keep the original eyes/forehead/background (no VAE flicker,
    # no square seam).
    if landmarks_npy_path:
        np.save(landmarks_npy_path, landmarks)

    pre = VideoPreProcessor(crop_scale_factor=2, crop_type="per_frame", resize_size=512)
    out = pre(video, landmarks)
    cropped = out.video  # T,C,512,512 uint8

    # Per-frame square crop boxes — used to paste the generated face back later.
    crop = [
        [int(c.x_start), int(c.y_start), int(c.x_end), int(c.y_end)] for c in out.crop_data
    ]
    with open(crop_json_path, "w") as f:
        json.dump(crop, f)

    write_video(out_path, rearrange(cropped, "t c h w -> t h w c"), fps=fps, video_codec="libx264")
    print(f"cropped video written: {out_path} ({cropped.shape[0]} frames @ {fps:.2f}fps)")


if __name__ == "__main__":
    main(*sys.argv[1:5])
