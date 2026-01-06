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