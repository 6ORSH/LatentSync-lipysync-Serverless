import cv2
import numpy as np
from utils.ultralight_facedetector import UltraLightFaceDetecion


class RandomizedVideoSampler:
    """
    Randomized forward/backward video frame sampler
    (extracted from Wav2Lip-style datagen logic)
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
        Generator yielding randomized frames.

        If the source has enough frames, yield a single contiguous forward
        segment from a random start (variety without the visible back-and-forth
        wobble). Only fall back to forward/backward traversal when the source is
        shorter than needed, to smoothly fill the extra frames without a hard cut.
        """
        n = len(frames)

        if n >= num_frames:
            start = np.random.randint(0, n - num_frames + 1)
            for idx in range(start, start + num_frames):
                yield frames[idx]
            return

        # Source shorter than needed: forward/backward traversal to fill length.
        reverse = False
        reverse_point = np.random.randint(1, n)
        idx = np.random.randint(0, reverse_point)

        for _ in range(num_frames):

            if idx == reverse_point:
                reverse = not reverse
                if reverse:
                    reverse_point = np.random.randint(0, idx)
                else:
                    reverse_point = np.random.randint(idx, n)

            idx = idx - 1 if reverse else idx + 1
            idx = np.clip(idx, 0, n - 1)

            yield frames[idx]

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
