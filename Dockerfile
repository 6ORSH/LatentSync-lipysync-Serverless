FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

# System dependencies
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    python3-dev \
    build-essential \
    git \
    ffmpeg \
    libgl1 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Make python3.10 default
RUN ln -sf /usr/bin/python3.10 /usr/bin/python

WORKDIR /app

# Python tooling
RUN python3 -m pip install --upgrade pip setuptools wheel


RUN pip install \
    torch==2.5.1 \
    torchvision==0.20.1 \
    --extra-index-url https://download.pytorch.org/whl/cu121

# Install Python deps
COPY requirements.txt .

RUN pip install -r requirements.txt

# HuggingFace CLI
RUN pip install huggingface-hub
RUN pip install tensorflow-cpu

# Copy application code
COPY . .

# ---- Bake model checkpoints into the image (no Network Volume needed) ----
# Paths must match utils/video.py and insightface FaceDetector(root="checkpoints/auxiliary").
RUN apt-get update && apt-get install -y wget unzip && rm -rf /var/lib/apt/lists/*

# UNet (~4.8 GB) -> /app/checkpoints/latentsync_unet.pt
RUN hf download ByteDance/LatentSync-1.6 latentsync_unet.pt --local-dir /app/checkpoints

# Whisper tiny -> /app/checkpoints/whisper/whisper/tiny.pt
RUN hf download ByteDance/LatentSync-1.6 whisper/tiny.pt --local-dir /app/checkpoints/whisper

# InsightFace buffalo_l -> /app/checkpoints/auxiliary/models/buffalo_l/*.onnx
RUN mkdir -p /app/checkpoints/auxiliary/models/buffalo_l && \
    wget -O /tmp/buffalo_l.zip \
      https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip && \
    unzip /tmp/buffalo_l.zip -d /app/checkpoints/auxiliary/models/buffalo_l && \
    rm /tmp/buffalo_l.zip

# Pre-download VAE into the HF cache
RUN python3 pre_model.py

ENV PYTHONPATH="/app/LatentSync:${PYTHONPATH}"

# Runtime command
CMD ["python3", "app.py"]
