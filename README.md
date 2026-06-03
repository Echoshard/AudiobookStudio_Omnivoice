# 📖 Audiobook Studio: OmniVoice Edition

[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-D22128?style=for-the-badge)](LICENSE)
[![OmniVoice Engine](https://img.shields.io/badge/TTS_Engine-OmniVoice-8ec5ff?style=for-the-badge)](https://github.com/k2-fsa/OmniVoice)
[![CUDA Accelerated](https://img.shields.io/badge/Hardware-CUDA%20Accelerated-green?style=for-the-badge&logo=nvidia)](https://developer.nvidia.com/cuda-zone)

Turn any text, document, or webpage into a beautifully narrated audiobook — executed entirely locally on your desktop, optimized for both CPU and GPU execution.

Audiobook Studio loads PDFs, EPUBs, text files, or scrapes web articles directly. Narrate using built-in high-quality presets, type a natural-language **Voice Design** prompt, or clone any speaker's voice from a short audio clip. The studio splits your text into sentences, synthesizes each section sentence-by-sentence using state-of-the-art zero-shot diffusion language models, and seamlessly compiles them into a single high-fidelity MP3.

---

## ✨ Features

- **🗣️ Advanced Voice Design**
  Synthesize custom voices from dropdown speaker attributes such as gender, age, pitch, whisper style, and English accent. Leave blank any attribute you want the model to infer.
- **👥 State-of-the-Art Zero-Shot Voice Cloning**
  Mimic any target speaker's voice using a short (3 to 10 seconds) `.wav` or `.mp3` audio sample.
- **📚 Multi-Format Document Ingestion**
  Import books and articles instantly from PDFs, EPUBs, raw text files, or directly parse the main reading text from any web URL.
- **⚡ Advanced CUDA & GPU Auto-Detection**
  The double-click runner batch file automatically detects your NVIDIA GPU drivers, handles CUDA toolkit capability checks, and installs the matching hardware-accelerated PyTorch build (`cu130`, `cu128`, `cu126`, `cu124`, `cu121`, or `cu118`) or an optimized CPU-only PyTorch build to save download bandwidth.
- **🎯 Intelligent Sentence-Level Generation**
  Processes text directly sentence-by-sentence. Includes an internal 100-word safety limit that automatically breaks extremely long sentences into sub-sentences, keeping memory footprints low, preventing hallucination, and guaranteeing high-quality neural speech prosody.
- **🔊 Interactive Quick Sampling**
  Generate and play a quick 3-sentence audio preview of your configuration before starting a full multi-hour audiobook render.
- **💿 Fully Automated MP3 Compilation**
  Includes an automated setup that downloads and configures **FFmpeg** locally. It compiles all temporary sentence chunks into a single, high-fidelity metadata-ready MP3 file and cleans up transient WAV files.
- **🔄 Fault-Tolerant Generation (Stop & Resume)**
  Stop the process gracefully at any time. Audiobook Studio saves progress and lets you resume from any specific sentence index.

---

## 🚀 One-Click Setup & Launch

Audiobook Studio features a completely self-configuring startup system. To install and launch the application on Windows:

1. Double-click the **`run_omnivoice.bat`** file.
2. The installer will automatically perform the following steps:
   - Detect your local Python installation.
   - Initialize a isolated Python Virtual Environment (`.venv`) inside the project folder.
   - Run the GPU detector (`detect_cuda.py`) to query `nvidia-smi` and system libraries, installing the best-matching CUDA-accelerated or optimized CPU-only PyTorch builds.
   - Download, configure, and isolate **FFmpeg** directly in the project directory.
   - Install all required libraries (PyMuPDF, EbookLib, BeautifulSoup4, soundfile, omnivoice).
3. The modern, dark-themed Audiobook Studio desktop UI will launch automatically!

### GPU PyTorch Repair

If you changed GPUs or PyTorch installed as CPU-only, double-click **`reinstall_gpu_torch.bat`**. It removes the current Torch packages, detects the NVIDIA driver again, and reinstalls the best CUDA wheel. CUDA 13.x drivers, including newer Blackwell GPUs, default to the stable `cu130` PyTorch wheel target.

Advanced users can edit `TORCH_CUDA_WHEEL` at the top of either BAT file to force `cu130`, `cu128`, `cu126`, `cu124`, `cu121`, `cu118`, or `cpu`.

---

## 🖱️ Controls & Settings Guide

### Input & Files Section

| Control | Function |
| :--- | :--- |
| **Ref Audio (.wav/.mp3)** | Path to an audio clip for zero-shot voice cloning. Select a 3-10s clip. Leave blank to use Voice Design dropdowns instead. |
| **Output Directory** | Where your audiobook sentence audio files and final compiled MP3 will be saved. Defaults to the repository root. |
| **Load PDF/Text/EPUB** | Open a file dialog to parse text from local books and documents. |
| **Scrape from URL** | Enter any web link to download and strip article or chapter content automatically. |

### Settings & Synthesis Engine

| Setting | Range / Options | Description |
| :--- | :--- | :--- |
| **Voice Design** | Gender, Age, Pitch, Style, Accent | English speaker-attribute dropdowns that compose the OmniVoice `instruct` string. Disabled if a **Ref Audio** file is loaded. |
| **Temperature** | 0.1 to 2.0 | Controls synthesis creativity. Lower values are more stable; higher values introduce more expression/variability (0.7 recommended). |
| **Speed** | 0.5x to 2.0x | Model-native playback rate modifier. Modifies speed directly during neural synthesis, preventing robotic pitch shifting. |
| **Steps** | 4 to 32 | Diffusion step count passed to OmniVoice as `num_step`; lower is faster, higher is usually better quality. |
| **Overwrite Existing WAVs** | Checkbox | When off, generation skips existing `output_N.wav` files so an interrupted book can resume automatically. |
| **Combine into MP3** | Checkbox + Output name | Automatically merges generated files and packages them into a single high-fidelity MP3. |

### Action Terminal

| Action | Function |
| :--- | :--- |
| **Export Sentence** | Saves the active sentence text block to a `.txt` file for editing. |
| **Export All Sentences** | Exports every sentence to numbered `.txt` files for preview. |
| **Open Folder** | Opens the designated output directory in Windows Explorer. |
| **Generate Speech** | Begins processing the document. The UI displays real-time statistics (average speed, words/sec, and estimated time remaining). |
| **Stop** | Signals the generator to stop rendering safely immediately after completing the current sentence. |
| **Quick Sample** | Synthesizes and plays a short preview passage using your current voice settings. |

---

## 💡 Professional Narrative Guidelines

1. **Crafting Custom Voices:** Use the **Voice Design** dropdowns to combine one attribute per category, such as `female, young adult, high pitch, british accent`.
2. **Optimizing Voice Clones:** For clean, professional voice cloning, use a 5-to-10 second clip. Ensure the clip has high-quality recording conditions, no background music, no noise, and minimal room reverb.
3. **Resuming Large Books:** Leave **Overwrite Existing WAVs** unchecked. Audiobook Studio scans the output directory, skips completed `output_N.wav` files, and continues with the first missing sentence.
4. **Internal Word Safety Limit:** If any single sentence exceeds 100 words, Audiobook Studio automatically partitions it into sub-segments of at most 100 words during execution. This guarantees perfect model synthesis and keeps neural operations fully stable.

---

## 📄 License, Attribution & Ethics

This project uses the **OmniVoice** model by k2-fsa under the Apache 2.0 license.

> [!IMPORTANT]  
> **Synthetic Voice Ethics Policy**
> - **Consent First:** Do not clone any individual's voice without their explicit, documented consent.
> - **Deception Prevention:** Do not use synthetic voices to impersonate public figures, create deepfakes, or generate deceptive media.
> - **Label Synthetic Output:** Always disclose to listeners that the audiobook narration was generated synthetically using AI.
