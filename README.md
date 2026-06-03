# 🎙️ OmniVoice Studio

[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-D22128?style=for-the-badge)](LICENSE)
[![OmniVoice Engine](https://img.shields.io/badge/TTS_Engine-OmniVoice-8ec5ff?style=for-the-badge)](https://github.com/k2-fsa/OmniVoice)
[![CUDA Accelerated](https://img.shields.io/badge/Hardware-CUDA%20Accelerated-green?style=for-the-badge&logo=nvidia)](https://developer.nvidia.com/cuda-zone)

OmniVoice Studio is a unified desktop suite combining high-fidelity **Audiobook Synthesis** and **Video Dubbing** in a single, local application. Powered by state-of-the-art zero-shot diffusion language models, the studio runs entirely locally on your machine with automatic hardware acceleration.

---

## ⚡ Main Studios (Tabs)

### 1. 📚 Audiobook Studio
Turn any book or document into a beautifully narrated audiobook.
- **Multi-Format Ingestion**: Load PDF, EPUB, or raw text files.
- **Reference Audio Clipping**: Select any audio file and use the built-in **`✂ Clip 30s`** tool to trim it to 30 seconds max for clean voice cloning.
- **Automated MP3 Compilation**: Automatically resamples, builds, and merges sentences into a single, high-fidelity MP3.
- **Stop & Resume**: Save your progress and resume generation from any sentence index.

### 2. 🎬 Video Dubbing Studio
Dub videos in any target voice using subtitle timelines.
- **Voice Extraction & Cloning**: Automatically extracts original audio chunks matching subtitle timestamps and uses them as reference clips to clone the speaker's voice.
- **Embedded Subtitles**: Automatically detects and extracts text-based embedded subtitle tracks from video files.
- **Sync & Mixing Control**:
  - **Auto-stretch**: Automatically adjusts voice playback speed using FFmpeg `atempo` to fit subtitle timings.
  - **Ducking**: Automatically lowers background video volume during speech segments with smooth 100ms volume fade ramps to prevent pops and clicks.
- **Sub-section Previewing**: Test and preview your dubbing setup on a 1-5 minute slice starting from any specific timestamp.

---

## 🚀 One-Click Setup & Launch

OmniVoice Studio features a completely self-configuring startup system:

1. Double-click **`run_omnivoice.bat`** or **`run_omnidub.bat`** (both launch the unified studio).
2. The installer will automatically:
   - Initialize an isolated Python Virtual Environment (`.venv`).
   - Query your GPU drivers and install the matching CUDA-accelerated (`cu130`, `cu128`, `cu126`, etc.) or optimized CPU-only PyTorch build.
   - Download and configure isolated **FFmpeg** bin utilities in the project directory.
   - Install all required libraries (PyMuPDF, EbookLib, BeautifulSoup4, soundfile, numpy, etc.).
3. The desktop studio will launch automatically in a dark theme tailored to fit 1080p scaled displays.

---

## 🖱️ Settings & Synthesis Options

- **Voice Profile Design**: Customize speaker properties such as gender, age, pitch, whisper style, and accent. Leaving fields blank lets the model infer them naturally.
- **Synthesis Parameters**: Adjust temperature (0.1 to 2.0), diffusion step counts (4 to 32), and speed scaling directly.
- **Full-Width Controls**: A unified controls bar at the bottom spans the screen, featuring utility commands on the left and action buttons (**`Generate`** / **`Start Dubbing`** and **`Stop`**) on the far right.

---

## 📄 License & Ethical Policy

This project uses the **OmniVoice** model by k2-fsa under the Apache 2.0 license.

> [!IMPORTANT]  
> **Synthetic Voice Ethics Policy**
> - **Consent First:** Do not clone any individual's voice without their explicit, documented consent.
> - **Deception Prevention:** Do not use synthetic voices to impersonate public figures, create deepfakes, or generate deceptive media.
> - **Label Synthetic Output:** Always disclose to listeners that the audiobook/dubbing narration was generated synthetically using AI.
