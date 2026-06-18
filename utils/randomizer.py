import cv2
import numpy as np
from utils.ultralight_facedetector import UltraLightFaceDetecion


class RandomizedVideoSampler:
    """
    Builds a driving clip of a target length from a source video.

    Forward playback from a random start when the source is long enough (no
    seam, each run differs); when it is too short, the source is extended by
    a seamless boomerang (reverse from the end), avoiding any hard cuts.
    """

    def __init__(
        self,
        face_model_path="utils/ultralight_facedetector/RFB-320.tflite",
        conf_threshold=0.6,
        resize_factor=1,
        seed=None
    ):
        self.resize_factor = resize_factor

        if seed is not None:
            np.random.seed(seed)

        self.face_detector = UltraLightFaceDetecion(
            face_model_path,
            conf_threshold=conf_threshold
        )

    # -------------------------
    # Video loading
    # -------------------------
    def load_video(self, video_path):
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)

        frames = []
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if self.resize_factor > 1:
                frame = cv2.resize(
                    frame,
                    (frame.shape[1] // self.resize_factor,
                     frame.shape[0] // self.resize_factor)
                )

            frames.append(frame)

        cap.release()
        return frames, fps

    # -------------------------
    # Face detection
    # -------------------------
    def face_detect(self, images):
        results = []

        for img in images:
            boxes, scores = self.face_detector.inference(img)

            if len(boxes) == 0:
                results.append([None, None])
                continue

            x1, y1, x2, y2 = boxes[0].round().astype(int)

            y_margin = int((y2 - y1) / 15)
            x_margin = int((x2 - x1) / 15)

            y1 = max(0, y1 - y_margin)
            y2 += y_margin
            x1 = max(0, x1 - x_margin)
            x2 += x_margin

            face = img[y1:y2, x1:x2]
            results.append([face, (y1, y2, x1, x2)])

        return results

    # -------------------------
    # Core randomizer
    # -------------------------
    def randomized_frame_generator(self, frames, num_frames):
        """
        Produce `num_frames` frames with no hard seams.

        - Source long enough (n >= num_frames): a single forward window from a
          random start. The window fits entirely, so there is no wrap and no
          seam, while the random start keeps each clip different.
        - Source too short (n < num_frames): extend by reversing from the END
          (boomerang) — forward 0..n-1, then back n-2..1, then forward again,
          repeating. Direction only flips at the endpoints where frames are
          adjacent, so playback stays smooth; no mid/start seams.
        """
        n = len(frames)

        if n >= num_frames:
            start = np.random.randint(0, n - num_frames + 1)
            for k in range(num_frames):
                yield frames[start + k]
            return

        if n == 1:
            for _ in range(num_frames):
                yield frames[0]
            return

        # Seamless ping-pong cycle: 0,1,..,n-1,n-2,..,1  (length 2n-2)
        cycle = list(range(n)) + list(range(n - 2, 0, -1))
        for k in range(num_frames):
            yield frames[cycle[k % len(cycle)]]

    # -------------------------
    # High-level API
    # -------------------------
    def generate_randomized_video(
        self,
        input_video,
        output_video,
        duration_seconds
    ):
        frames, fps = self.load_video(input_video)
        total_frames = int(duration_seconds * fps)

        h, w, _ = frames[0].shape
        writer = cv2.VideoWriter(
            output_video,
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (w, h)
        )

        gen = self.randomized_frame_generator(frames, total_frames)

        for frame in gen:
            writer.write(frame)

        writer.release()
        return output_video
