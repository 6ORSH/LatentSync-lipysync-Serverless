"""Composite KeySync's 512x512 face output back into the original frames.

KeySync only changes the mouth/lower face, but outputs the whole 512² crop where
the rest is a VAE reconstruction of the original (slightly different every frame).
So we blend the generated face into the original ONLY over a soft lower-face mask
(mouth + chin + jaw, from face landmarks) and keep the ORIGINAL eyes / forehead /
background untouched. This removes both the eye-flicker and the square-crop seam.
Falls back to a feathered box blend if landmarks are unavailable.

Produces a VIDEO-ONLY file at the original resolution; the caller muxes audio.

Usage:  python paste_back.py <original.mp4> <keysync_out.mp4> <crop_data.json> <out_video.mp4> [landmarks.npy]
"""

import sys
import json
import cv2
import numpy as np

# 68-pt iBUG indices for the lower face: jaw/chin (4..12), nose base (31..35),
# mouth (48..67). Convex hull of these covers what KeySync animates and excludes
# the eyes/forehead.
LOWER_FACE_IDX = list(range(4, 13)) + list(range(31, 36)) + list(range(48, 68))


def _box_feather(h, w, border=0.08):
    m = np.ones((h, w), np.float32)
    b = max(1, int(min(h, w) * border))
    ramp = np.linspace(0.0, 1.0, b, dtype=np.float32)
    m[:b, :] *= ramp[:, None]
    m[-b:, :] *= ramp[::-1][:, None]
    m[:, :b] *= ramp[None, :]
    m[:, -b:] *= ramp[None, ::-1]
    return m[..., None]


def _lower_face_alpha(H, W, lmk):
    """Soft full-frame alpha over the lower face from 68-pt landmarks."""
    pts = lmk[LOWER_FACE_IDX].astype(np.int32)
    hull = cv2.convexHull(pts)
    m = np.zeros((H, W), np.uint8)
    cv2.fillConvexPoly(m, hull, 255)
    # Feather: dilate a touch, then Gaussian blur for a soft edge.
    k = max(11, (int(0.05 * max(H, W)) | 1))
    m = cv2.dilate(m, np.ones((k, k), np.uint8))
    m = cv2.GaussianBlur(m, (k, k), 0)
    return (m.astype(np.float32) / 255.0)[..., None]


def main(orig_path, gen_path, crop_json, out_path, landmarks_path=None):
    with open(crop_json) as f:
        crop = json.load(f)
    landmarks = np.load(landmarks_path) if landmarks_path else None

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
            cand = fo.copy()
            cand[y0:y1, x0:x1] = cv2.resize(fg, (bw, bh))
            if landmarks is not None and i < len(landmarks):
                alpha = _lower_face_alpha(H, W, landmarks[i])  # keep original eyes/bg
            else:
                # Fallback: feathered box over the crop region only.
                alpha = np.zeros((H, W, 1), np.float32)
                alpha[y0:y1, x0:x1] = _box_feather(bh, bw)
            fo = (alpha * cand.astype(np.float32) + (1.0 - alpha) * fo.astype(np.float32)).astype(np.uint8)
        writer.write(fo)
        i += 1

    capo.release()
    capg.release()
    writer.release()
    print(f"paste-back wrote {i} frames -> {out_path} ({W}x{H})")


if __name__ == "__main__":
    main(*sys.argv[1:6])
