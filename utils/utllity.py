import os
import cv2
import subprocess
import json

from dotenv import load_dotenv, find_dotenv


def load_environment(env_key: str = "stag"):
    if env_key not in ("stag", "prod"):
        raise ValueError("env_key must be 'stag' or 'prod'")

    env_file = find_dotenv(f"{env_key}.env", usecwd=True)
    if env_file:
        load_dotenv(env_file, override=False)
        print(f"🟢 Loaded local {env_key}.env")
    else:
        print("🟡 Using injected RunPod env vars")

    # R2 credentials are account-wide; only the bucket is environment-specific.
    if env_key == "stag":
        os.environ["R2_BUCKET"] = os.environ["STAG_R2_BUCKET"]
    else:
        os.environ["R2_BUCKET"] = os.environ["PROD_R2_BUCKET"]

    print(f"✅ Runtime environment configured: {env_key}")
    return env_key


def _probe_duration(media_path, kind):
    """
    Return media duration in seconds via ffprobe.

    Raises a clear RuntimeError if ffprobe fails or returns no duration,
    instead of a cryptic KeyError / JSONDecodeError on a broken input.
    `kind` is "audio" / "video" — used only for the error message.
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        media_path
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"ffprobe could not read {kind} '{media_path}': {result.stderr.strip()}"
        )

    try:
        return float(json.loads(result.stdout)["format"]["duration"])
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
        raise RuntimeError(
            f"ffprobe could not read {kind} '{media_path}': "
            f"{result.stderr.strip() or e}"
        )


def get_audio_duration(audio_path):
    """Audio duration in seconds (raises RuntimeError if unreadable)."""
    return _probe_duration(audio_path, "audio")


def get_video_duration(video_path):
    """Video duration in seconds (raises RuntimeError if unreadable)."""
    return _probe_duration(video_path, "video")
