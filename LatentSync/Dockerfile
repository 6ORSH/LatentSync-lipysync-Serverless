FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/app/.cache/huggingface

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.10 python3.10-dev python3-pip \
        ffmpeg libgl1 libglib2.0-0 libsm6 libxext6 \
        build-essential git pkg-config libssl-dev \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.10 /usr/bin/python3 \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && pip install --upgrade pip

WORKDIR /app

# Install Python deps before copying source so this layer is cached on code changes
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=100 runpod requests \
    && pip install --no-cache-dir --default-timeout=100 -r requirements.txt

# Pre-download the HuggingFace VAE so cold starts don't need network for it
RUN python -c "from diffusers import AutoencoderKL; AutoencoderKL.from_pretrained('stabilityai/sd-vae-ft-mse')" || true

COPY . .

# IMPORTANT: Model checkpoints are not included in the Docker image (too large).
# You MUST provide them at runtime:
#
# Option 1: RunPod Network Volume (recommended)
#   - Upload checkpoints to a RunPod Network Volume
#   - Mount at /runpod-volume in the template
#   - Set env vars in the template:
#     CKPT_PATH=/runpod-volume/checkpoints/latentsync_unet.pt
#     UNET_CONFIG_PATH=/runpod-volume/configs/unet/stage2.yaml
#
# Option 2: Custom path
#   - Mount your volume at any path
#   - Set CKPT_PATH to the absolute path, e.g. /mnt/models/latentsync_unet.pt
#
# If checkpoints are missing, jobs will fail with a helpful error message
# instead of crashing the worker (which is the correct serverless behavior).

CMD ["python", "handler.py"]
