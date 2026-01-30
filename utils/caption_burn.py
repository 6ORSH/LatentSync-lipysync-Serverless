import subprocess
import os
import json


def _nvenc_usable():
    try:
        return False
        out = subprocess.check_output(
            ["nvidia-smi", "-q"],
            stderr=subprocess.DEVNULL
        ).decode()
        return "Encoder" in out
    except Exception:
        return False


def get_video_resolution(video_path):
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json",
        video_path
    ]
    out = subprocess.check_output(cmd)
    data = json.loads(out)
    s = data["streams"][0]
    return s["width"], s["height"]


def compute_caption_style(height):
    font_size = int(height * 0.045)
    bottom_margin = int(height * 0.10)
    outline = max(1, int(font_size * 0.04))
    return font_size, bottom_margin, outline


def burn_captions_with_audio_gpu(
    input_video: str,
    srt_path: str,
    output_video: str,
    font_name: str = "DejaVu Sans",
    prefer_nvenc: bool = True,
):
    # ---- Resolution-aware styling ----
    w, h = get_video_resolution(input_video)
    font_size, bottom_margin, outline = compute_caption_style(h)

    style = (
        f"FontName={font_name},"
        f"FontSize={font_size},"
        f"PrimaryColour=&H00FFFFFF,"
        f"OutlineColour=&H00000000,"
        f"Outline={outline},"
        f"Shadow=0,"
        f"MarginV={bottom_margin}"
    )

    subtitles_filter = (
        f"subtitles='{srt_path}':"
        f"force_style='"
        f"PlayResX={w},"
        f"PlayResY={h},"
        f"FontName={font_name},"
        f"FontSize={font_size},"
        f"PrimaryColour=&H00FFFFFF,"
        f"OutlineColour=&H00000000,"
        f"Outline={outline},"
        f"Shadow=0,"
        f"MarginV={bottom_margin}"
        f"'"
    )


    use_nvenc = prefer_nvenc and _nvenc_usable()

    if use_nvenc:
        print("🚀 Using NVENC")
        cmd = [
            "ffmpeg", "-y",
            "-i", input_video,
            "-vf", subtitles_filter,
            "-c:v", "h264_nvenc",
            "-preset", "p4",
            "-rc", "vbr",
            "-cq", "19",
            "-c:a", "copy",
            output_video,
        ]
    else:
        print("⚠️ NVENC unavailable, using CPU")
        cmd = [
            "ffmpeg", "-y",
            "-i", input_video,
            "-vf", subtitles_filter,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "18",
            "-c:a", "copy",
            output_video,
        ]

    subprocess.run(cmd, check=True)
