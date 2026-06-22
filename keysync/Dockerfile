FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

# Python 3.11 (deadsnakes) + ffmpeg + build tools for dlib + media libs.
RUN apt-get update && apt-get install -y software-properties-common && \
    add-apt-repository -y ppa:deadsnakes/ppa && apt-get update && apt-get install -y \
    python3.11 python3.11-dev python3.11-distutils \
    build-essential cmake git ffmpeg \
    libgl1 libglib2.0-0 libsndfile1 wget ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3.11 /usr/bin/python && \
    wget -qO /tmp/get-pip.py https://bootstrap.pypa.io/get-pip.py && python3.11 /tmp/get-pip.py && rm /tmp/get-pip.py

WORKDIR /app

# Torch first (KeySync's pinned cu121 versions). requirements.txt does NOT pin
# torch, so installing it here and using --no-deps below keeps it intact.
RUN pip install torch==2.4.1 torchvision==0.19.1 torchaudio==2.4.1 \
    --index-url https://download.pytorch.org/whl/cu121

# KeySync deps — exact pins, no resolver (as upstream README mandates).
COPY requirements.txt /app/requirements.txt
RUN pip install --no-deps -r /app/requirements.txt

# Upstream-documented conflict fix.
RUN pip uninstall -y omegaconf antlr4-python3-runtime && \
    pip install "omegaconf==2.3.0" "antlr4-python3-runtime==4.9.3"

# Serverless + R2 + download deps for our handler.
RUN pip install runpod==1.6.2 boto3==1.34.122 requests "huggingface_hub>=0.23"

# ---- Bake checkpoints (inference set only: keyframe + interpolation + WavLM).
#      svd_no_emb is training-only; sam2/vsr unused without --fix_occlusion. ----
RUN mkdir -p /app/pretrained_models/checkpoints && python -c "\
from huggingface_hub import hf_hub_download as d;\
[d('toninio19/keysync', f, local_dir='/app/pretrained_models') for f in \
 ['checkpoints/keyframe_dub.pt','checkpoints/interpolation_dub.pt','checkpoints/WavLM-Base+.pt']]"

# Bake HuBERT (audio_emb_type=hubert) into the HF cache.
RUN python -c "from transformers import HubertModel; HubertModel.from_pretrained('facebook/hubert-base-ls960')"

# face_alignment is imported by scripts/util/landmarks_extractor.py but missing
# from upstream requirements.txt (so --no-deps never installed it). Its deps
# (numba, scikit-image, scipy, opencv, torch) are already pinned, so --no-deps.
# Pre-bake the SFD face detector + 2D landmark weights so there's no runtime
# download (also acts as a numpy-2 compatibility canary at build time).
RUN pip install --no-deps face-alignment && \
    python -c "import face_alignment; face_alignment.FaceAlignment(face_alignment.LandmarksType.TWO_D, flip_input=False, device='cpu', face_detector='sfd')"

# SAM2 for occlusion handling (--fix_occlusion: hand/object over the face).
# Skip the optional CUDA extension — the runtime base has no nvcc; SAM2 falls
# back to non-accelerated mask post-processing. Deps (hydra-core, iopath,
# omegaconf, portalocker) are already pinned via requirements.txt.
RUN SAM2_BUILD_CUDA=0 pip install --no-deps "git+https://github.com/facebookresearch/sam2.git" && \
    python -c "from sam2.build_sam import build_sam2_video_predictor; print('sam2 import OK')"

# SAM2 checkpoint (occlusion masks) -> pretrained_models/checkpoints/sam2.1_hiera_large.pt
RUN python -c "from huggingface_hub import hf_hub_download as d; d('toninio19/keysync', 'checkpoints/sam2.1_hiera_large.pt', local_dir='/app/pretrained_models')"

# Vendor KeySync code + our handler (last, so code edits don't bust the layers above).
COPY . /app

# Patch the author's hardcoded absolute WavLM path -> relative (matches audio_wrapper.py).
RUN sed -i 's#/vol/paramonos2/projects/antoni/code/Personal/code_prep/keysync/pretrained_models/checkpoints/WavLM-Base+.pt#pretrained_models/checkpoints/WavLM-Base+.pt#g' \
    scripts/sampling/dubbing_pipeline_raw.py

ENV PYTHONPATH=/app
CMD ["python", "handler.py"]
