# LatentSync LipSync – Serverless & Local Deployment

This repository provides a **serverless-ready and local-capable deployment** of **ByteDance’s LatentSync 1.6** lip-sync model.
It supports **explicit environment selection** for **local**, **staging**, and **production** deployments.
This system was ran and tested on **Nvidia RTX 3090 and A40** and consumed **~19 GB video ram**
---

## 🚀 Key Features

* Serverless GPU inference (RunPod compatible)
* Explicit **environment selection** (`local`, `stag`, `prod`)
* Dockerized CUDA environment
* Preloaded models (UNet, Whisper, VAE, InsightFace)
* No runtime model downloads
* Global pipeline reuse
* A specialized Randomizer Algorithm such that every next video is a new video.
* Clean runtime cleanup & GPU memory handling

---

## 🎬 Demo – Before & After (LatentSync)

### Before (Input Video)

[https://github.com/user-attachments/assets/4a9bcf74-76a7-4109-9d52-ed91fb7b3239](https://github.com/user-attachments/assets/4a9bcf74-76a7-4109-9d52-ed91fb7b3239)

### After (LatentSync Output)

[https://github.com/user-attachments/assets/dfdab143-d3b6-4da7-ab69-e343f18928e6](https://github.com/user-attachments/assets/dfdab143-d3b6-4da7-ab69-e343f18928e6)

---

## 🔧 Environment Levels (Required)

> **Important:**
> The `level` field is **mandatory** for all runs.

### 🖥️ Local (Development / Debugging)

```json
{
  "level": "local",
  "ref_video_path": "/absolute/path/to/video.mp4",
  "ref_audio_path": "/absolute/path/to/audio.wav"
}
```

* Uses local filesystem
* No cloud credentials required
* Intended for development and debugging only

---

### ☁️ Staging (AWS)

```json
{
  "level": "stag",
  "ref_video_path": "s3://staging-bucket/path/video.mp4",
  "ref_audio_path": "s3://staging-bucket/path/audio.wav"
}
```

* Uses staging AWS resources
* Separate credentials and buckets
* Mirrors production setup safely

---

### 🚀 Production (AWS)

```json
{
  "level": "prod",
  "ref_video_path": "s3://production-bucket/path/video.mp4",
  "ref_audio_path": "s3://production-bucket/path/audio.wav"
}
```

* Uses production AWS infrastructure
* Strict access and IAM policies
* Intended for live workloads

---

## 🧪 Info / Health Check Mode

```json
{
  "aleef": true
}
```

Returns service metadata without running inference.

---

## 📁 Repository Structure

```
.
├── app.py
├── Dockerfile
├── requirements.txt
├── utils/
├── LatentSync/
├── checkpoints/
└── test_input.json
```

---

## 📦 Docker Build

```bash
docker build -t latentsync-lipsync-serverless .
```

All models are **preloaded at build time**, ensuring fully offline runtime execution.

---

## ☁️ Deploy on RunPod Serverless (Network Volume)

This fork ships a **lightweight image**: model checkpoints are **not** baked in
(the download block in the `Dockerfile` is commented out). Instead they live on a
**RunPod Network Volume** and are mounted at runtime. On serverless the volume is
mounted at `/runpod-volume`; `app.py` symlinks `/app/checkpoints → /runpod-volume/checkpoints`
on startup so both `utils/video.py` and InsightFace's `FaceDetector`
(`root="checkpoints/auxiliary"`) resolve correctly. VAE is the only weight baked
into the image (via `pre_model.py`).

### 1. Create the Network Volume

RunPod → **Storage → Network Volumes** → create a ~20 GB volume **in the same
region** as the serverless endpoint.

### 2. Populate the volume

Attach the volume to a temporary Pod (mounts at `/workspace`) and run:

```bash
pip install -U "huggingface-hub[cli]"

# UNet
huggingface-cli download ByteDance/LatentSync-1.6 latentsync_unet.pt \
  --local-dir /workspace/checkpoints --local-dir-use-symlinks False

# Whisper tiny  (config stage2_512.yaml: cross_attention_dim=384)
huggingface-cli download ByteDance/LatentSync-1.6 whisper/tiny.pt \
  --local-dir /workspace/checkpoints/whisper --local-dir-use-symlinks False

# InsightFace buffalo_l (used by FaceDetector)
apt-get update && apt-get install -y wget unzip
mkdir -p /workspace/checkpoints/auxiliary/models/buffalo_l
wget -O /tmp/buffalo_l.zip \
  https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip
unzip /tmp/buffalo_l.zip -d /workspace/checkpoints/auxiliary/models/buffalo_l
rm /tmp/buffalo_l.zip
```

Required layout on the volume (paths must match exactly):

```
checkpoints/
├── latentsync_unet.pt
├── whisper/whisper/tiny.pt            # double "whisper" is intentional
└── auxiliary/models/buffalo_l/*.onnx  # det_10g.onnx, 2d106det.onnx, ...
```

Delete the temporary Pod afterward — the volume persists. VAE does **not** go on
the volume (it is baked into the image).

### 3. Build & push the image

```bash
docker build -t <registry>/latentsync-custom:v1 .
docker push <registry>/latentsync-custom:v1
```

### 4. Create the endpoint

* **Docker Image** = `<registry>/latentsync-custom:v1`
* **Attach Network Volume** = the volume above (mounts at `/runpod-volume`)
* **Env** = AWS credentials for S3 (required for `stag` / `prod`). `CHECKPOINTS_DIR`
  is *not* needed — the startup symlink handles paths.
* **GPU** ≥ 24 GB (A40 / A5000 / 4090)

### 5. Verify cold start

The logs should show, with no `FileNotFoundError` / `Face not detected`:

```
🔗 Linked /app/checkpoints -> /runpod-volume/checkpoints
Loading LatentSync pipeline...
```

> **Alternative (bake into image):** uncomment the checkpoint-download block in the
> `Dockerfile` instead of using a volume. Produces a self-contained but ~5 GB larger
> image; no volume needed.

---

## 🛠 Tech Stack

* Python 3.10
* PyTorch (CUDA)
* Diffusers
* LatentSync 1.6
* Whisper
* InsightFace
* RunPod Serverless
* AWS S3

---

## 🧹 Runtime Behavior

* Temp files created in `/tmp`
* GPU memory cleared after each job
* Global pipeline reused across warm invocations

---

## 📄 License

* LatentSync: Apache 2.0
* Other dependencies follow upstream licenses

---

## ✅ Status

✔ Local, staging, and production modes supported
✔ Serverless Docker image deployed
✔ Models preloaded and locked

---
🙏 Acknowledgement

Special thanks and sincere appreciation to the ByteDance LatentSync team for their outstanding work on this model.
This deployment builds upon their research and engineering excellence, and we acknowledge their contribution with deep respect and gratitude.

### Run on local
```bash
sudo docker run --rm -it   --runtime=nvidia   --gpus all   -e NVIDIA_VISIBLE_DEVICES=all   -e NVIDIA_DRIVER_CAPABILITIES=video,compute,utility   lat_t_1
```