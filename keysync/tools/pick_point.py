"""Pick the occluder point + startFrame for KeySync occlusion — no ffmpeg needed.

Opens the video frame at a given time, you click the occluder (e.g. the hand),
and it prints the values to paste into POST /jobs:
  "position":  [x, y]  -- ORIGINAL pixel coords (the worker maps them to the crop)
  "startFrame": N      -- in the worker's 25 fps space (= round(seconds * 25))

Usage:
    pip install opencv-python
    python pick_point.py <video.mp4> <seconds>

e.g.  python pick_point.py D:\\Files\\LipSync_Project\\inputs\\video4.mp4 2.0
"""

import sys
import cv2

PIPELINE_FPS = 25  # the worker standardises every input to 25 fps


def main(path: str, seconds: float):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise SystemExit(f"cannot open {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    cap.set(cv2.CAP_PROP_POS_FRAMES, round(seconds * fps))
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise SystemExit(f"no frame at {seconds}s (video fps={fps:.2f})")

    start_frame = round(seconds * PIPELINE_FPS)
    print(f"video fps={fps:.2f}  |  startFrame (25fps) = {start_frame}")
    print("Click the occluder (e.g. the hand). Press any key / close the window to exit.")

    win = "click the occluder"

    def on_click(event, x, y, *_):
        if event == cv2.EVENT_LBUTTONDOWN:
            print(f'  "fixOcclusion": true, "position": [{x}, {y}], "startFrame": {start_frame}')

    cv2.namedWindow(win)
    cv2.setMouseCallback(win, on_click)
    cv2.imshow(win, frame)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: python pick_point.py <video.mp4> <seconds>")
    main(sys.argv[1], float(sys.argv[2]))
