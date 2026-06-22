"""Composite KeySync's 512x512 face output back into the original frames.

KeySync outputs only the square face crop. Using the per-frame crop boxes saved
by preprocess_crop.py, we resize each generated face back to its box and blend it
into the original full-resolution frame (feathered edges to avoid a hard seam).
Produces a VIDEO-ONLY file at the original resolution; the caller muxes audio.

Usage:  python paste_back.py <original.mp4> <keysync_out.mp4> <crop_data.json> <out_video.mp4>
"""

import sys
import json
import cv2
import numpy as np


def _feather(h, w, border=0.08):
    m = np.ones((h, w), np.float32)
    b = max(1, int(min(h, w) * border))
    ramp = np.linspace(0.0, 1.0, b, dtype=np.float32)
    m[:b, :] *= ramp[:, None]
    m[-b:, :] *= ramp[::-1][:, None]
    m[:, :b] *= ramp[None, :]
    m[:, -b:] *= ramp[None, ::-1]
    return m[..., None]  # h,w,1


def main(orig_path, gen_path, crop_json, out_path):
    with open(crop_json) as f:
        crop = json.load(f)

    capo = cv2.VideoCapture(orig_path)
    capg = cv2.VideoCapture(gen_path)
    fps = capo.get(cv2.CAP_PROP_FPS) or 25.0
    W = int(capo.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(capo.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))

    i = 0
    while True:
        ro, fo = capo.read()
        rg, fg = capg.read()
        if not ro or not rg or i >= len(crop):
            break
        x0, y0, x1, y1 = crop[i]
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(W, x1), min(H, y1)
        bw, bh = x1 - x0, y1 - y0
        if bw > 0 and bh > 0:
            face = cv2.resize(fg, (bw, bh)).astype(np.float32)
            region = fo[y0:y1, x0:x1].astype(np.float32)
            a = _feather(bh, bw)
            fo[y0:y1, x0:x1] = (a * face + (1.0 - a) * region).astype(np.uint8)
        writer.write(fo)
        i += 1

    capo.release()
    capg.release()
    writer.release()
    print(f"paste-back wrote {i} frames -> {out_path} ({W}x{H})")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
