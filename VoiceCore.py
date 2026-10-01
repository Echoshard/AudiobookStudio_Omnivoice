import os
import re
import sys
import time
import traceback
import numpy as np
import soundfile as sf

if sys.platform.startswith("win"):
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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

VALID_OMNIVOICE_INSTRUCTS = {
    "american accent", "australian accent", "british accent", "canadian accent",
    "child", "chinese accent", "elderly", "female", "high pitch", "indian accent",
    "japanese accent", "korean accent", "low pitch", "male", "middle-aged",
    "moderate pitch", "portuguese accent", "russian accent", "teenager",
    "very high pitch", "very low pitch", "whisper", "young adult",
}

# Mapped presets for OmniVoice (must match valid OmniVoice instruct tags)
OMNIVOICE_PRESETS = {
    "alba": "female, american accent, moderate pitch",
    "marius": "male, american accent, low pitch",
    "javert": "male, british accent, very low pitch",
    "jean": "male, american accent, middle-aged",
    "fantine": "female, whisper, low pitch",
    "cosette": "female, young adult, high pitch",
    "eponine": "female, teenager, moderate pitch",
    "azelma": "female, child, very high pitch",
}


def filter_instruct(instruct_str):
    """Filters custom instruct strings to ensure only valid OmniVoice tags are passed."""
    if not instruct_str:
        return "female, american accent"
    tokens = [t.strip().lower() for t in str(instruct_str).replace(";", ",").split(",") if t.strip()]
    valid_tokens = [t for t in tokens if t in VALID_OMNIVOICE_INSTRUCTS]
    if not valid_tokens:
        lower = instruct_str.lower()
        return "female, american accent" if "female" in lower else "male, american accent" if "male" in lower else "female, american accent"
    return ", ".join(valid_tokens)

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


# ---------------------------------------------------------------------------
# Breath / silence fix (see OmniVoiceSlienceFix.md)
#
# OmniVoice treats the reference clip as conversational context and tends to
# synthesize an inhalation breath before the first word. Its built-in silence
# trimmer uses -50 dB, so the breath (~-25 dB) survives, and it then prepends
# 100ms of padding. The fix has three parts:
#   1. Cut the reference clip at a natural pause (not mid-word) + 0.2s silence.
#   2. Generate with pad_duration=0.0 so no artificial dead air is added.
#   3. Strip the leading breath from the output and end it with 0.2s silence.
# ---------------------------------------------------------------------------

SILENCE_PAD_SEC = 0.2
BREATH_THRESHOLD_DB = -22  # relative to the library's standard -6 dBFS output peak
BREATH_LEAD_MS = 35        # cushion kept before speech so /s/, /h/, /t/ aren't clipped


def _windowed_rms(audio, win_size, hop, start=0, end=None):
    end = len(audio) if end is None else end
    starts = range(start, end - win_size, hop)
    rms = np.array([np.sqrt(np.mean(audio[i : i + win_size] ** 2)) for i in starts])
    return rms, list(starts)


def _trim_trailing_dead_air(audio, sr, keep_sec):
    """Cut everything after the last window that still contains speech."""
    win_size = int(sr * 0.05)
    rms, starts = _windowed_rms(audio, win_size, int(sr * 0.01))
    if len(rms) == 0:
        return audio
    speech = np.where(rms > max(0.005, rms.max() * 0.04))[0]
    if len(speech) == 0:
        return audio
    cut = min(len(audio), starts[speech[-1]] + win_size + int(sr * keep_sec))
    return audio[:cut].copy()


def _fade_out_and_pad(audio, sr, silence_pad_sec=SILENCE_PAD_SEC):
    """15ms anti-click fade-out, then append clean digital silence."""
    audio = audio.astype(np.float32, copy=True)
    fade_len = int(sr * 0.015)
    if len(audio) > fade_len:
        audio[-fade_len:] *= np.linspace(1.0, 0.0, fade_len, dtype=np.float32)
    return np.concatenate([audio, np.zeros(int(sr * silence_pad_sec), dtype=np.float32)])


def cut_reference_at_silence(audio_path, min_sec=4.0, max_sec=10.0, silence_pad_sec=SILENCE_PAD_SEC):
    """Load a reference clip, cut it at a natural pause, and append 0.2s of silence.

    Returns (mono_float32_audio, sample_rate).
    """
    data, sr = sf.read(audio_path, dtype="float32", always_2d=True)
    mono = data.mean(axis=1)

    if len(mono) <= max_sec * sr:
        # Short enough already: just drop the trailing dead air after the last word.
        clip = _trim_trailing_dead_air(mono, sr, keep_sec=0.0)
    else:
        # Too long: find the longest pause between min_sec and max_sec and cut there.
        win_size = int(sr * 0.1)
        rms, starts = _windowed_rms(mono, win_size, int(sr * 0.02), int(sr * min_sec), int(sr * max_sec))
        if len(rms) == 0:
            clip = mono[: int(sr * max_sec)].copy()
        else:
            silent = rms < max(0.003, rms.max() * 0.03)
            best_start, best_len, run_start = -1, 0, -1
            for idx, is_sil in enumerate(np.append(silent, False)):
                if is_sil and run_start == -1:
                    run_start = idx
                elif not is_sil and run_start != -1:
                    if idx - run_start > best_len:
                        best_start, best_len = run_start, idx - run_start
                    run_start = -1
            if best_len >= 3:
                pos = best_start + best_len // 2
            else:
                pos = int(np.argmin(rms))  # fall back to the quietest point
            clip = mono[: starts[pos] + win_size // 2].copy()
            print(f"[VoiceCore] Cut reference audio at {len(clip) / sr:.2f}s (natural pause).")

    return _fade_out_and_pad(clip, sr, silence_pad_sec), sr


def strip_leading_breath(audio_np, sample_rate=24000):
    """Remove the pre-speech inhalation that OmniVoice tends to generate.

    The -22 dB threshold from the fix guide assumes OmniVoice's standard output
    level (peak ~0.5 / -6 dBFS). Clone output is scaled to the reference clip's
    loudness, so the threshold is shifted by the same amount; otherwise quiet
    voices would have their first word mistaken for breath.
    """
    peak = float(np.abs(audio_np).max()) if len(audio_np) else 0.0
    if peak < 1e-4:
        return audio_np
    threshold_db = BREATH_THRESHOLD_DB + (20 * np.log10(peak) + 6.0)

    # Same as pydub's detect_leading_silence (10ms chunks, dBFS of chunk RMS).
    chunk = int(sample_rate * 0.01)
    n_chunks = len(audio_np) // chunk
    rms = np.sqrt(np.mean(audio_np[: n_chunks * chunk].reshape(n_chunks, chunk) ** 2, axis=1))
    loud = np.where(20 * np.log10(np.maximum(rms, 1e-10)) >= threshold_db)[0]
    if len(loud) == 0:
        return audio_np
    lead_ms = int(loud[0]) * 10
    if lead_ms > 100:
        cleaned = audio_np[int((lead_ms - BREATH_LEAD_MS) * sample_rate / 1000):]
        if len(cleaned) > int(sample_rate * 0.3):
            print(f"[VoiceCore] Stripped {lead_ms - BREATH_LEAD_MS}ms of leading breath.")
            return cleaned
    return audio_np


def finalize_omnivoice_output(audio_np, sample_rate=24000, silence_pad_sec=SILENCE_PAD_SEC):
    """Strip leading breath, trim trailing dead air, fade out, and pad 0.2s of silence."""
    audio_np = np.asarray(audio_np, dtype=np.float32).squeeze()
    audio_np = strip_leading_breath(audio_np, sample_rate)
    audio_np = _trim_trailing_dead_air(audio_np, sample_rate, keep_sec=0.04)
    return _fade_out_and_pad(audio_np, sample_rate, silence_pad_sec)


def prepare_ref_audio(ref_audio_path):
    if not ref_audio_path or not os.path.exists(ref_audio_path):
        return None
    try:
        # Cut at a natural pause (not an arbitrary 10s mark that can land mid-word)
        # and end with clean silence so the model doesn't "continue" into a breath.
        data, samplerate = cut_reference_at_silence(ref_audio_path)

        temp_file = os.path.abspath("temp_omnivoice_ref.wav")
        sf.write(temp_file, data, samplerate, subtype="PCM_16")
        return temp_file
    except Exception as exc:
        print(f"[VoiceCore] [Warning] Failed to process reference audio: {exc}. Using raw file.")
        return ref_audio_path


def split_into_sentences(text):
    # Normalize line breaks: replace single newlines inside paragraphs with spaces,
    # while preserving double newlines (paragraph boundaries) as distinct breaks.
    text = text.replace("\r\n", "\n")
    text = re.sub(r"\n\n+", "<PARA>", text)
    text = text.replace("\n", " ")
    text = text.replace("<PARA>", "\n")

    # Split by standard punctuation boundaries, keeping delimiters
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
    
    final_sentences = []
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        words = s.split()
        if len(words) <= 100:
            final_sentences.append(s)
        else:
            # Split long sentences into sub-sentences of at most 100 words
            for i in range(0, len(words), 100):
                sub_chunk = " ".join(words[i : i + 100])
                final_sentences.append(sub_chunk)
    return final_sentences


def group_sentences(sentences, sentences_per_chunk=1):
    """Join consecutive sentences into chunks so each generate() call covers more text.

    OmniVoice renders up to ~30s of estimated audio in a single pass; anything
    longer is split internally at punctuation into ~15s pieces and cross-faded,
    so large chunks are safe.
    """
    n = max(1, int(sentences_per_chunk))
    return [" ".join(sentences[i : i + n]) for i in range(0, len(sentences), n)]


def set_seed(seed):
    """Seed all RNGs OmniVoice draws from so generation is reproducible.

    OmniVoice has no `seed` argument; its per-sentence voice variation comes
    from random sampling during decoding. Seeding torch right before each
    generate() call locks the sampled voice to a fixed, repeatable result.
    """
    if seed is None:
        return
    import random
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def generate_audio(text, ref_audio=None, ref_text=None, instruct=None, speed_val=1.0, num_step=32, seed=None, status_cb=None, stop_event=None):
    global _model
    if not text.strip():
        return None
    try:
        if status_cb:
            status_cb("Synthesizing sentence... (takes a moment on CPU)")

        # Re-seed before every sentence so each sentence gets the same voice.
        set_seed(seed)

        # pad_duration=0.0 stops OmniVoice prepending 100ms of dead air before
        # the breath; finalize_omnivoice_output() adds clean padding instead.
        kwargs = {"speed": speed_val, "num_step": num_step, "pad_duration": 0.0, "fade_duration": 0.02}
        if ref_audio:
            kwargs["ref_audio"] = ref_audio
            # Passing the known transcript avoids loading Whisper ASR for cloning.
            if ref_text:
                kwargs["ref_text"] = ref_text
        elif instruct:
            kwargs["instruct"] = filter_instruct(instruct)

        print(f"[VoiceCore] Synthesizing: '{text}'")
        out_list = _model.generate(text=text, **kwargs)
        if out_list and len(out_list) > 0:
            return out_list[0]
    except Exception as e:
        print(f"[VoiceCore] [Warning] Failed to generate: {e}")
        traceback.print_exc()

    return None


def synthesize_audio(text, out_path, voice=None, ref_audio_path=None, ref_text=None, speed=1.0, num_step=32, seed=None, status_cb=None, stop_event=None, prepare_ref=True):
    temp_ref = prepare_ref_audio(ref_audio_path) if prepare_ref else ref_audio_path
    try:
        raw_instruct = OMNIVOICE_PRESETS.get(voice.lower(), voice) if voice else OMNIVOICE_PRESETS["alba"]
        instruct = filter_instruct(raw_instruct)
        # When a reference clip is supplied we are cloning, so the preset instruct
        # must not be sent (ref_audio + instruct are mutually exclusive modes).
        audio_np = generate_audio(
            text,
            ref_audio=temp_ref,
            ref_text=ref_text if temp_ref else None,
            instruct=None if temp_ref else instruct,
            speed_val=speed,
            num_step=num_step,
            seed=seed,
            status_cb=status_cb,
            stop_event=stop_event,
        )
        if audio_np is None:
            raise RuntimeError("OmniVoice returned empty audio.")
        sample_rate = getattr(_model, "sampling_rate", 24000)
        audio_np = finalize_omnivoice_output(audio_np, sample_rate)
        sf.write(out_path, audio_np, sample_rate)
        return True
    finally:
        if prepare_ref and temp_ref and os.path.exists(temp_ref):
            try:
                os.remove(temp_ref)
            except OSError:
                pass
