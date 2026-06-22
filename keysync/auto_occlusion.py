"""Auto-detect a hand occluding the face, for KeySync occlusion (Step B).

Runs MediaPipe Hands over the CROPPED 512x512 clip (the same video SAM2 runs on,
so coordinates are already in crop space). Finds the earliest frame where a hand
landmark falls inside the central lower-face zone (i.e. the hand is over the
mouth/chin), and reports a point on that hand + the frame index. SAM2 then tracks
that hand forward.

Usage:  python auto_occlusion.py <video_cropped_512.mp4>
Prints exactly one line:
    OCCLUSION position=[x,y] start_frame=N      (found)
    NONE                                        (no hand over the face)
"""

import sys
import cv2
import mediapipe as mp

# Crop is face-centered (VideoPreProcessor, scale 2) at 512x512. The mouth/chin
# sits in the central-lower area; a hand landmark here means it occludes the face.
ZONE_X = (140, 372)   # central horizontal band
ZONE_Y = (210, 470)   # mid-to-lower face
CENTER = (256.0, 320.0)  # ~mouth center, to pick the most central hand point


def main(video_path: str):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("NONE")
        return

    hands = mp.solutions.hands.Hands(
        static_image_mode=False, max_num_hands=2, min_detection_confidence=0.5
    )

    idx = 0
    found = None
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        h, w = frame.shape[:2]
        res = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        if res.multi_hand_landmarks:
            best, best_d = None, 1e18
            for hl in res.multi_hand_landmarks:
                for lm in hl.landmark:
                    x, y = lm.x * w, lm.y * h
                    if ZONE_X[0] <= x <= ZONE_X[1] and ZONE_Y[0] <= y <= ZONE_Y[1]:
                        d = (x - CENTER[0]) ** 2 + (y - CENTER[1]) ** 2
                        if d < best_d:
                            best_d, best = d, (x, y)
            if best is not None:
                found = (idx, best)
                break
        idx += 1

    cap.release()
    hands.close()

    if found is None:
        print("NONE")
    else:
        fi, (x, y) = found
        print(f"OCCLUSION position=[{round(x, 1)},{round(y, 1)}] start_frame={fi}")


if __name__ == "__main__":
    main(sys.argv[1])
