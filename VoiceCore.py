import os
import re
import sys
import time
import traceback
import numpy as np
import soundfile as sf

# Force HuggingFace directory at script load
os.environ["HF_HOME"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# Suppress Transformers warning logs
import warnings
warnings.filterwarnings("ignore")
try:
    from transformers import logging as tf_logging
    tf_logging.set_verbosity_error()
except Exception:
    pass

_model = None
_libs_loaded = False

# Mapped presets for OmniVoice
OMNIVOICE_PRESETS = {
    "alba": "female, pleasant voice, clear pronunciation, natural speed",
    "marius": "male, low pitch, warm voice, deep tone",
    "javert": "male, deep voice, serious tone, dramatic",
    "jean": "male, mature voice, expressive, clear speech",
    "fantine": "female, soft voice, gentle, slow pace",
    "cosette": "female, young voice, bright, cheerful",
    "eponine": "female, warm voice, friendly, engaging",
    "azelma": "female, high pitch, energetic, fast pace",
}

def load_libs():
    global _libs_loaded, torch, OmniVoice
    if _libs_loaded:
        return True
    try:
        import torch as _torch
        from omnivoice import OmniVoice as _omnivoice
        torch = _torch
        OmniVoice = _omnivoice
        _libs_loaded = True
        return True
    except ImportError:
        print("ERROR: omnivoice or torch not installed!")
        return False


def get_active_device():
    if not load_libs():
        return "Unknown"
    try:
        import torch
        return "GPU (CUDA)" if torch.cuda.is_available() else "CPU"
    except Exception:
        return "CPU"


def ensure_model_loaded(status_cb=None, progress_cb=None, device_cb=None):
    global _model
    if _model is not None:
        return True
    if not load_libs():
        if status_cb:
            status_cb("ERROR: omnivoice package not installed.")
        return False
    try:
        if status_cb:
            status_cb("Downloading/Loading OmniVoice Model (~2.5GB)... Please wait.")
        if progress_cb:
            progress_cb("indeterminate")

        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32
        if device_cb:
            device_str = "GPU (CUDA)" if device == "cuda" else "CPU"
            device_cb(f"Active Device: {device_str}")

        print("[VoiceCore] Loading OmniVoice model...")
        _model = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map=device, dtype=dtype)
        print("[VoiceCore] OmniVoice model loaded successfully.")
        return True
    except Exception as e:
        print(f"[VoiceCore] Failed to load OmniVoice: {e}")
        traceback.print_exc()
        return False
    finally:
        if progress_cb:
            progress_cb("determinate")


def prepare_ref_audio(ref_audio_path):
    if not ref_audio_path or not os.path.exists(ref_audio_path):
        return None
    try:
        data, samplerate = sf.read(ref_audio_path)
        max_samples = 10 * samplerate
        if len(data) > max_samples:
            print(f"[VoiceCore] Truncating reference audio from {len(data)} to {max_samples} samples.")
            data = data[:max_samples]

        # Convert stereo to mono
        if len(data.shape) > 1:
            data = data.mean(axis=1)

        temp_file = os.path.abspath("temp_omnivoice_ref.wav")
        sf.write(temp_file, data, samplerate, subtype="PCM_16")
        return temp_file
    except Exception as exc:
        print(f"[VoiceCore] [Warning] Failed to process reference audio: {exc}. Using raw file.")
        return ref_audio_path


def generate_audio(text, ref_audio=None, instruct=None, speed_val=1.0, status_cb=None, stop_event=None):
    global _model
    # Split text into sentences using standard punctuation boundaries, keeping delimiters
    raw_parts = re.split(r"([.!?\n]+)", text)
    sentences = []
    for part in raw_parts:
        if not part:
            continue
        if re.match(r"^[.!?\n]+$", part):
            if sentences:
                sentences[-1] += part
            else:
                sentences.append(part)
        else:
            sentences.append(part)
    sentences = [s.strip() for s in sentences if s.strip()]
    total = len(sentences)

    full_audio = []
    for idx, sentence in enumerate(sentences):
        if stop_event and stop_event.is_set():
            break
        if not sentence:
            continue
        try:
            if status_cb:
                status_cb(f"Synthesizing sentence {idx + 1}/{total}... (takes a moment on CPU)")

            kwargs = {"speed": speed_val}
            if ref_audio:
                kwargs["ref_audio"] = ref_audio
            elif instruct:
                kwargs["instruct"] = instruct

            print(f"[VoiceCore] Synthesizing sentence {idx + 1}/{total}: '{sentence}'")
            out_list = _model.generate(text=sentence, **kwargs)
            if out_list and len(out_list) > 0:
                full_audio.append(out_list[0])
        except Exception as e:
            print(f"[VoiceCore] [Warning] Failed to generate: {e}")
            traceback.print_exc()

    if not full_audio:
        return None
    return np.concatenate(full_audio)


def synthesize_audio(text, out_path, voice=None, ref_audio_path=None, speed=1.0, status_cb=None, stop_event=None):
    temp_ref = prepare_ref_audio(ref_audio_path)
    try:
        instruct = OMNIVOICE_PRESETS.get(voice.lower(), voice) if voice else OMNIVOICE_PRESETS["alba"]
        audio_np = generate_audio(text, ref_audio=temp_ref, instruct=instruct, speed_val=speed, status_cb=status_cb, stop_event=stop_event)
        if audio_np is None:
            raise RuntimeError("OmniVoice returned empty audio.")
        sf.write(out_path, audio_np, 24000)
        return True
    finally:
        if temp_ref and os.path.exists(temp_ref):
            try:
                os.remove(temp_ref)
            except OSError:
                pass
