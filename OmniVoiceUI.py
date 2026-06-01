import gc
import os
import re
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
import tkinter as tk

from tkinter import filedialog, messagebox, simpledialog, ttk

# Import speech synthesis core
import VoiceCore

SAMPLE_TEXT = (
    "Greetings Human, I am here to tell you a cat fact. "
    "Did you know that cats sleep for 70% of their lives?"
)

stop_event = threading.Event()


def combine_output_to_mp3(output_files, output_dir, custom_name="final_output"):
    if not output_files:
        return None

    if not custom_name.lower().endswith(".mp3"):
        custom_name += ".mp3"

    list_file = os.path.join(output_dir, "file_list.txt")
    output_mp3 = os.path.join(output_dir, custom_name)

    try:
        with open(list_file, "w", encoding="utf-8") as handle:
            for file_path in output_files:
                abs_path = os.path.abspath(file_path).replace("'", "'\\''")
                handle.write(f"file '{abs_path}'\n")

        print(f"[System] Merging {len(output_files)} files into {output_mp3}...")
        command = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            list_file,
            "-acodec",
            "libmp3lame",
            "-q:a",
            "2",
            output_mp3,
        ]
        result = subprocess.run(command, capture_output=True, text=True)

        if result.returncode == 0:
            print("[System] MP3 merge successful. Cleaning up WAV files...")
            for file_path in output_files:
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass
            return output_mp3

        print(f"[System] FFmpeg error: {result.stderr}")
        return None
    except Exception as exc:
        print(f"[System] Failed to merge MP3: {exc}")
        return None
    finally:
        if os.path.exists(list_file):
            try:
                os.remove(list_file)
            except OSError:
                pass


class OmniVoiceWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OmniVoice Audiobook Studio")
        self.geometry("820x980")
        self.minsize(850, 780)
        self.configure(bg="#1e222b")

        self.ref_audio_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()
        self.voice_var = tk.StringVar(value="female, low pitch, british accent")
        self.temp_var = tk.DoubleVar(value=0.7)
        self.speed_var = tk.DoubleVar(value=1.0)
        self.start_sentence_var = tk.IntVar(value=1)
        self.combine_mp3_var = tk.BooleanVar(value=True)
        self.mp3_name_var = tk.StringVar(value="final_output")
        self.status_var = tk.StringVar(value="Ready")
        self.sentence_info_var = tk.StringVar(value="")
        self.device_info_var = tk.StringVar(value="Active Device: Detecting...")

        self._configure_theme()
        self._build_layout()

        # Trace reference audio selection to toggle voice entry field
        self.ref_audio_var.trace_add("write", self._on_ref_audio_changed)
        self._on_ref_audio_changed()

        # Start device detection in a background thread to keep launch instant
        threading.Thread(target=self._detect_device_at_startup, daemon=True).start()

    def _on_ref_audio_changed(self, *args):
        if hasattr(self, "voice_entry") and hasattr(self, "voice_label"):
            if self.ref_audio_var.get().strip():
                self.voice_entry.configure(state="disabled")
                self.voice_label.configure(style="DisabledBody.TLabel")
            else:
                self.voice_entry.configure(state="normal")
                self.voice_label.configure(style="Body.TLabel")

    def _detect_device_at_startup(self):
        try:
            device_str = VoiceCore.get_active_device()
        except Exception:
            device_str = "CPU"
        self._ui(self.device_info_var.set, f"Active Device: {device_str}")

    def _configure_theme(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Root.TFrame", background="#1e222b")
        style.configure("Card.TFrame", background="#282c34")
        
        style.configure("Title.TLabel", background="#1e222b", foreground="#61afef", font=("Segoe UI", 18, "bold"))
        style.map("Title.TLabel", foreground=[("!disabled", "#61afef")])
        
        style.configure("Sub.TLabel", background="#1e222b", foreground="#7f848e", font=("Segoe UI", 10))
        style.map("Sub.TLabel", foreground=[("!disabled", "#7f848e")])
        
        style.configure("CardTitle.TLabel", background="#282c34", foreground="#61afef", font=("Segoe UI", 11, "bold"))
        style.map("CardTitle.TLabel", foreground=[("!disabled", "#61afef")])
        
        style.configure("Body.TLabel", background="#282c34", foreground="#edf2f7")
        style.map("Body.TLabel", foreground=[("!disabled", "#edf2f7")])
        
        style.configure("DisabledBody.TLabel", background="#282c34", foreground="#5c6370")
        style.map("DisabledBody.TLabel", foreground=[("!disabled", "#5c6370")])
        
        style.configure("Info.TLabel", background="#282c34", foreground="#abb2bf")
        style.map("Info.TLabel", foreground=[("!disabled", "#abb2bf")])
        
        style.configure("Status.TLabel", background="#282c34", foreground="#98c379", font=("Segoe UI", 11, "bold"))
        style.map("Status.TLabel", foreground=[("!disabled", "#98c379")])
        
        style.configure("TEntry", fieldbackground="#21252b", foreground="#abb2bf")
        style.configure("TCombobox", fieldbackground="#21252b", foreground="#abb2bf")
        style.map("TCombobox", fieldbackground=[("readonly", "#21252b")], foreground=[("readonly", "#abb2bf")])
        style.configure("TSpinbox", fieldbackground="#21252b", foreground="#abb2bf")
        style.configure("TCheckbutton", background="#282c34", foreground="#abb2bf")
        style.configure("TButton", background="#3e4452", foreground="#abb2bf", padding=8)
        style.map("TButton", background=[("active", "#4b5263")])
        style.configure("Accent.TButton", background="#61afef", foreground="#1e222b", padding=9)
        style.map("Accent.TButton", background=[("active", "#75b5ff")])
        style.configure("Danger.TButton", background="#e06c75", foreground="#1e222b", padding=9)
        style.map("Danger.TButton", background=[("active", "#e57c83")])
        style.configure("Sample.TButton", background="#d19a66", foreground="#1e222b", padding=9)
        style.map("Sample.TButton", background=[("active", "#e5b182")])
        style.configure("TProgressbar", troughcolor="#21252b", background="#61afef", bordercolor="#21252b")

    def _build_layout(self):
        root = ttk.Frame(self, style="Root.TFrame", padding=18)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        # Header with title on left and active device on right
        header = ttk.Frame(root, style="Root.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        ttk.Label(header, text="OmniVoice Audiobook Studio", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self.device_info_var, style="Sub.TLabel").grid(row=0, column=1, sticky="e")

        content = ttk.Frame(root, style="Root.TFrame")
        content.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        content.columnconfigure(0, weight=1)
        content.rowconfigure(1, weight=1)

        self._build_inputs_card(content).grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self._build_text_card(content).grid(row=1, column=0, sticky="nsew", pady=(0, 12))
        self._build_settings_card(content).grid(row=2, column=0, sticky="ew", pady=(0, 12))
        self._build_actions_card(content).grid(row=3, column=0, sticky="ew", pady=(0, 12))
        self._build_progress_card(content).grid(row=4, column=0, sticky="ew")

    def _card(self, parent, title):
        frame = ttk.Frame(parent, style="Card.TFrame", padding=14)
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text=title, style="CardTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 10))
        return frame

    def _build_inputs_card(self, parent):
        frame = self._card(parent, "Inputs")
        body = ttk.Frame(frame, style="Card.TFrame")
        body.grid(row=1, column=0, sticky="ew")
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text="Ref Audio (.wav/.mp3):", style="Body.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=5)
        ttk.Entry(body, textvariable=self.ref_audio_var).grid(row=0, column=1, sticky="ew", pady=5)
        ttk.Button(body, text="Browse", command=self.browse_ref_file).grid(row=0, column=2, padx=(10, 0), pady=5)

        ttk.Label(body, text="Output Directory:", style="Body.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=5)
        ttk.Entry(body, textvariable=self.output_dir_var).grid(row=1, column=1, sticky="ew", pady=5)
        ttk.Button(body, text="Browse", command=self.browse_output_dir).grid(row=1, column=2, padx=(10, 0), pady=5)
        return frame

    def _build_text_card(self, parent):
        frame = self._card(parent, "Text to Speak")
        frame.rowconfigure(1, weight=1)

        text_frame = ttk.Frame(frame, style="Card.TFrame")
        text_frame.grid(row=1, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self.text_input = tk.Text(
            text_frame,
            wrap="word",
            height=5,
            bg="#21252b",
            fg="#abb2bf",
            insertbackground="#abb2bf",
            relief="flat",
            padx=10,
            pady=10,
        )
        self.text_input.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.text_input.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text_input.configure(yscrollcommand=scrollbar.set)

        actions = ttk.Frame(frame, style="Card.TFrame")
        actions.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(actions, text="Load PDF/Text/EPUB", command=self.load_text).pack(side="left")
        ttk.Button(actions, text="Scrape from URL", command=self.load_url).pack(side="left", padx=(8, 0))
        return frame

    def _build_settings_card(self, parent):
        frame = self._card(parent, "Settings")
        
        # Subtitle hint explaining custom voice prompts vs ref audio cloning
        ttk.Label(frame, text="Type a custom voice prompt (e.g. 'deep warm male, slow pace') - only used if no Ref Audio is provided", style="Info.TLabel", font=("Segoe UI", 9, "italic")).grid(row=1, column=0, sticky="w", pady=(0, 8))
        
        body = ttk.Frame(frame, style="Card.TFrame")
        body.grid(row=2, column=0, sticky="ew")
        for col in range(4):
            body.columnconfigure(col, weight=1 if col in (1, 3) else 0)

        # Row 0: Voice Prompt
        self.voice_label = ttk.Label(body, text="Voice Prompt:", style="Body.TLabel")
        self.voice_label.grid(row=0, column=0, sticky="w", padx=(0, 10), pady=5)
        self.voice_entry = ttk.Entry(body, textvariable=self.voice_var)
        self.voice_entry.grid(row=0, column=1, columnspan=3, sticky="ew", pady=5)

        # Row 1: Temperature Scale & Speed Scale
        ttk.Label(body, text="Temperature:", style="Body.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=5)
        tk.Scale(body, from_=0.1, to=2.0, resolution=0.1, orient="horizontal", variable=self.temp_var, bg="#282c34", fg="#abb2bf", highlightthickness=0, troughcolor="#21252b").grid(row=1, column=1, sticky="ew", pady=5)

        ttk.Label(body, text="Speed:", style="Body.TLabel").grid(row=1, column=2, sticky="w", padx=(12, 10), pady=5)
        tk.Scale(body, from_=0.5, to=2.0, resolution=0.05, orient="horizontal", variable=self.speed_var, bg="#282c34", fg="#abb2bf", highlightthickness=0, troughcolor="#21252b").grid(row=1, column=3, sticky="ew", pady=5)

        # Row 2: Start Sentence & MP3 Combine settings
        ttk.Label(body, text="Start Sentence:", style="Body.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=5)
        ttk.Spinbox(body, from_=1, to=9999, textvariable=self.start_sentence_var, width=10).grid(row=2, column=1, sticky="w", pady=5)

        mp3_row = ttk.Frame(body, style="Card.TFrame")
        mp3_row.grid(row=2, column=2, columnspan=2, sticky="ew", pady=5)
        ttk.Checkbutton(mp3_row, text="Combine into MP3", variable=self.combine_mp3_var).pack(side="left")
        ttk.Entry(mp3_row, textvariable=self.mp3_name_var, width=30).pack(side="left", padx=(10, 0))
        return frame

    def _build_actions_card(self, parent):
        frame = self._card(parent, "Actions")
        body = ttk.Frame(frame, style="Card.TFrame")
        body.grid(row=1, column=0, sticky="ew")

        ttk.Button(body, text="Export Sentence", command=self.export_sentence).pack(side="left")
        ttk.Button(body, text="Open Folder", command=self.open_output_folder).pack(side="left", padx=(8, 0))

        self.generate_btn = ttk.Button(body, text="Generate Speech", style="Accent.TButton", command=self.start_generation)
        self.generate_btn.pack(side="left", padx=(8, 0))
        ttk.Button(body, text="Stop", style="Danger.TButton", command=self.stop_generation).pack(side="left", padx=(8, 0))
        ttk.Button(body, text="Quick Sample", style="Sample.TButton", command=self.generate_quick_sample).pack(side="left", padx=(8, 0))
        return frame

    def _build_progress_card(self, parent):
        frame = self._card(parent, "Progress")
        body = ttk.Frame(frame, style="Card.TFrame")
        body.grid(row=1, column=0, sticky="ew")
        body.columnconfigure(0, weight=1)

        ttk.Label(body, textvariable=self.sentence_info_var, style="Info.TLabel").grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.progress_bar = ttk.Progressbar(body, mode="determinate", maximum=1)
        self.progress_bar.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(body, textvariable=self.status_var, style="Status.TLabel").grid(row=2, column=0, sticky="ew")
        return frame

    def _get_text(self):
        return self.text_input.get("1.0", "end-1c")

    def _set_text(self, value):
        self.text_input.delete("1.0", "end")
        self.text_input.insert("1.0", value)

    def _ui(self, callback, *args, **kwargs):
        self.after(0, lambda: callback(*args, **kwargs))

    def _set_status(self, text):
        self._ui(self.status_var.set, text)

    def _set_sentence_info(self, text):
        self._ui(self.sentence_info_var.set, text)

    def _set_progress(self, value, maximum):
        self._ui(self.progress_bar.configure, maximum=max(maximum, 1), value=value)

    def _set_progress_mode(self, mode):
        def cb():
            self.progress_bar.configure(mode=mode)
            if mode == "indeterminate":
                self.progress_bar.start(10)
            else:
                self.progress_bar.stop()
                self.progress_bar.configure(value=0, maximum=1)
        self._ui(cb)

    def _set_generate_enabled(self, enabled):
        self._ui(self.generate_btn.configure, state=("normal" if enabled else "disabled"))

    def browse_ref_file(self):
        filename = filedialog.askopenfilename(title="Select Reference Audio", filetypes=[("Audio Files", "*.wav *.mp3"), ("All Files", "*.*")])
        if filename:
            self.ref_audio_var.set(filename)

    def browse_output_dir(self):
        directory = filedialog.askdirectory(title="Select Output Directory")
        if directory:
            self.output_dir_var.set(directory)

    def load_text(self):
        file_path = filedialog.askopenfilename(title="Select Document", filetypes=[("Documents", "*.pdf *.txt *.epub"), ("All Files", "*.*")])
        if not file_path:
            return

        try:
            # Dynamically ensure required libs are loaded in VoiceCore
            VoiceCore.load_libs()
            
            import fitz
            import ebooklib
            from ebooklib import epub
            from bs4 import BeautifulSoup
            
            loaded_text = ""
            lower_path = file_path.lower()

            if lower_path.endswith(".pdf"):
                with fitz.open(file_path) as doc:
                    loaded_text = "".join(page.get_text() for page in doc)
            elif lower_path.endswith(".txt"):
                with open(file_path, "r", encoding="utf-8") as handle:
                    loaded_text = handle.read()
            elif lower_path.endswith(".epub"):
                book = epub.read_epub(file_path)
                parts = []
                for item in book.get_items():
                    if item.get_type() == ebooklib.ITEM_DOCUMENT:
                        soup = BeautifulSoup(item.get_body_content(), "html.parser")
                        parts.append(soup.get_text(" ", strip=True))
                loaded_text = "\n\n".join(part for part in parts if part)

            self._set_text(loaded_text)
            self.status_var.set(f"Loaded text from {os.path.basename(file_path)}.")
        except Exception as exc:
            traceback.print_exc()
            messagebox.showerror("Load Error", f"Failed to load document:\n{exc}")
            self.status_var.set(f"Load error: {exc}")

    def load_url(self):
        url = simpledialog.askstring("Scrape URL", "Enter URL:", parent=self)
        if not url:
            return

        def task():
            try:
                VoiceCore.load_libs()
                import requests
                from bs4 import BeautifulSoup
                
                response = requests.get(url, timeout=20)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, "html.parser")
                scraped = "\n".join(p.get_text(" ", strip=True) for p in soup.find_all("p"))
                self._ui(self._set_text, scraped)
                self._set_status("Text loaded from URL.")
            except Exception as exc:
                self._set_status(f"Error loading URL: {exc}")

        threading.Thread(target=task, daemon=True).start()

    def export_sentence(self):
        try:
            full_text = self._get_text().strip()
            sentences = VoiceCore.split_into_sentences(full_text)

            sentence_id = self.start_sentence_var.get()
            if 1 <= sentence_id <= len(sentences):
                script_dir = os.path.dirname(os.path.abspath(__file__))
                path = os.path.join(script_dir, f"sentence_{sentence_id}.txt")
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(sentences[sentence_id - 1])
                self.status_var.set(f"Sentence {sentence_id} exported.")
            else:
                self.status_var.set("Invalid sentence ID.")
        except Exception as exc:
            self.status_var.set(f"Export error: {exc}")

    def open_output_folder(self):
        output_dir = self.output_dir_var.get().strip() or os.path.dirname(os.path.abspath(__file__))
        try:
            if sys.platform == "win32":
                os.startfile(output_dir)
            else:
                webbrowser.open(f"file://{output_dir}")
        except Exception as exc:
            self.status_var.set(f"Open folder error: {exc}")

    def start_generation(self):
        stop_event.clear()
        self._set_generate_enabled(False)
        threading.Thread(target=self._generate_speech, daemon=True).start()

    def stop_generation(self):
        stop_event.set()
        self.status_var.set("Stopping after current sentence...")

    def _generate_speech(self):
        try:
            output_directory = self.output_dir_var.get().strip() or os.path.dirname(os.path.abspath(__file__))
            self._ui(self.output_dir_var.set, output_directory)
            os.makedirs(output_directory, exist_ok=True)

            self._set_status("Loading model...")
            if not VoiceCore.ensure_model_loaded(
                status_cb=self._set_status,
                progress_cb=self._set_progress_mode,
                device_cb=self.device_info_var.set
            ):
                self._set_status("Failed to load model.")
                return

            ref_path = self.ref_audio_var.get().strip()
            prepared_ref_path = VoiceCore.prepare_ref_audio(ref_path) if ref_path else None
            voice_name = self.voice_var.get().strip()

            full_text = self._get_text().strip()
            if not full_text:
                self._set_status("No text found to synthesize.")
                if prepared_ref_path and os.path.exists(prepared_ref_path):
                    try:
                        os.remove(prepared_ref_path)
                    except OSError:
                        pass
                return

            all_sentences = VoiceCore.split_into_sentences(full_text)
            start_sentence_idx = self.start_sentence_var.get() - 1
            if start_sentence_idx < 0 or start_sentence_idx >= len(all_sentences):
                self._set_status("Invalid start sentence.")
                if prepared_ref_path and os.path.exists(prepared_ref_path):
                    try:
                        os.remove(prepared_ref_path)
                    except OSError:
                        pass
                return

            total_sentences = len(all_sentences[start_sentence_idx:])
            self._set_progress(0, len(all_sentences))
            speed_val = float(self.speed_var.get())
            times = []
            output_files = []

            total_words_generated = 0
            total_time_elapsed = 0.0

            for idx, sentence in enumerate(all_sentences[start_sentence_idx:], start=start_sentence_idx):
                if stop_event.is_set():
                    self._set_status(f"Stopped. Saved {len(output_files)} files so far.")
                    break

                started = time.time()
                sentence_word_count = len(sentence.split())

                if times:
                    avg_time = (sum(times) / len(times)) / 60.0
                    remaining_sentences = total_sentences - (idx - start_sentence_idx + 1)
                    remaining_time = avg_time * remaining_sentences
                    wps = total_words_generated / total_time_elapsed if total_time_elapsed > 0 else 0.0
                    info = f"Processing sentence {idx + 1}/{len(all_sentences)} | Avg: {avg_time:.2f}m | Est. Remaining: {remaining_time:.2f}m | Speed: {wps:.1f} words/sec"
                else:
                    info = f"Processing sentence {idx + 1}/{len(all_sentences)}"

                self._set_sentence_info(info)
                self._set_status(f"Generating sentence {idx + 1}...")

                out_path = os.path.join(output_directory, f"output_{idx + 1}.wav")
                success = False
                for attempt in range(1, 4):
                    if stop_event.is_set():
                        break
                    try:
                        VoiceCore.synthesize_audio(
                            sentence,
                            out_path,
                            voice=voice_name,
                            ref_audio_path=prepared_ref_path,
                            speed=speed_val,
                            status_cb=self._set_status,
                            stop_event=stop_event,
                            prepare_ref=False
                        )
                        success = True
                        break
                    except Exception as sentence_error:
                        print(f"[Sentence {idx + 1}] Attempt {attempt} failed: {sentence_error}")
                        if attempt >= 3:
                            print(f"[Sentence {idx + 1}] Skipping.")
                            break
                        time.sleep(1)

                if stop_event.is_set():
                    if os.path.exists(out_path):
                        try:
                            os.remove(out_path)
                        except OSError:
                            pass
                    break

                if not success:
                    continue

                output_files.append(out_path)
                self._set_progress(idx + 1, len(all_sentences))
                elapsed = time.time() - started
                times.append(elapsed)

                total_words_generated += sentence_word_count
                total_time_elapsed += elapsed

                print(f"[Sentence {idx + 1}] Done in {elapsed:.2f}s")
                gc.collect()

            if not stop_event.is_set():
                self._set_status(f"Done. Saved {len(output_files)} files.")

            if self.combine_mp3_var.get() and output_files:
                self._set_status("Merging to MP3...")
                custom_name = self.mp3_name_var.get().strip() or "final_output"
                mp3_path = combine_output_to_mp3(output_files, output_directory, custom_name)
                if mp3_path:
                    self._set_status(f"Done. MP3 saved: {os.path.basename(mp3_path)}")
                else:
                    self._set_status("Done. Files saved, but MP3 merge failed.")
        except Exception as exc:
            print("\nUncaught error in _generate_speech():")
            traceback.print_exc()
            self._set_status(f"An error occurred: {exc}")
        finally:
            if prepared_ref_path and os.path.exists(prepared_ref_path):
                try:
                    os.remove(prepared_ref_path)
                except OSError:
                    pass
            self._set_generate_enabled(True)

    def generate_quick_sample(self):
        def task():
            temp_out = os.path.abspath("quick_sample.wav")
            try:
                self._set_status("Generating quick sample...")
                if not VoiceCore.ensure_model_loaded(
                    status_cb=self._set_status,
                    progress_cb=self._set_progress_mode,
                    device_cb=self.device_info_var.set
                ):
                    self._set_status("Failed to load model.")
                    return

                ref_path = self.ref_audio_var.get().strip()
                voice_name = self.voice_var.get().strip()
                speed_val = float(self.speed_var.get())

                VoiceCore.synthesize_audio(
                    SAMPLE_TEXT,
                    temp_out,
                    voice=voice_name,
                    ref_audio_path=ref_path,
                    speed=speed_val,
                    status_cb=self._set_status
                )

                self._set_status("Playing quick sample...")
                if sys.platform == "win32":
                    import winsound
                    winsound.PlaySound(temp_out, winsound.SND_FILENAME)
                else:
                    subprocess.run(["aplay", temp_out], capture_output=True)
                self._set_status("Quick sample done.")
            except Exception as exc:
                traceback.print_exc()
                self._set_status(f"Quick sample error: {exc}")
            finally:
                if os.path.exists(temp_out):
                    try:
                        os.remove(temp_out)
                    except OSError:
                        pass

        threading.Thread(target=task, daemon=True).start()


def main():
    app = OmniVoiceWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
