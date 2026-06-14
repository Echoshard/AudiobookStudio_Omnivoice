import gc
import json
import os
import random
import re
import shutil
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
    "The morning light came through the window as I poured my coffee, checked "
    "the time, and listened to the rain starting softly outside."
)

VOICE_DESIGN_OPTIONS = {
    "Gender": ["", "female", "male"],
    "Age": ["", "child", "teenager", "young adult", "middle-aged", "elderly"],
    "Pitch": ["", "very low pitch", "low pitch", "moderate pitch", "high pitch", "very high pitch"],
    "Style": ["", "whisper"],
    "Accent": [
        "",
        "american accent",
        "british accent",
        "australian accent",
        "canadian accent",
        "indian accent",
        "chinese accent",
        "korean accent",
        "japanese accent",
        "portuguese accent",
        "russian accent",
    ],
}


def clean_text_for_tts(text):
    """
    Cleans subtitle text for text-to-speech by removing formatting tags (<i>, <b>),
    sound description cues ([music], (laughter)), asterisks (*sighs*), and extra whitespace.
    """
    import re
    # Remove HTML/XML formatting tags like <i>, </i>, <b>, <u>, <font color=...>
    text = re.sub(r'<[^>]+>', '', text)
    # Remove text inside square brackets [music], [laughter]
    text = re.sub(r'\[[^\]]*\]', '', text)
    # Remove text inside parentheses (laughs), (sighs)
    text = re.sub(r'\([^)]*\)', '', text)
    # Remove text inside asterisks *groans*, *sighs*
    text = re.sub(r'\*[^*]*\*', '', text)
    # Clean up multiple whitespaces
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def parse_srt_or_vtt(filepath):
    """
    Parses an SRT or VTT subtitle file and returns a list of dictionaries:
    [{'start': float, 'end': float, 'text': str}]
    """
    import re
    if not os.path.exists(filepath):
        return []

    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()

    segments = []
    # Regex to match timestamps like 00:00:01,234 --> 00:00:04,567 or 00:01.200 --> 00:03.400
    timestamp_pattern = re.compile(
        r'(?:(\d+):)?(\d{1,2}):(\d{2})[,.](\d{3})\s*-->\s*(?:(\d+):)?(\d{1,2}):(\d{2})[,.](\d{3})'
    )

    def parse_time_match(h, m, s, ms):
        hours = int(h) if h else 0
        minutes = int(m)
        seconds = int(s)
        milliseconds = int(ms)
        return hours * 3600.0 + minutes * 60.0 + seconds + milliseconds / 1000.0

    current_segment = None
    for line in lines:
        line = line.strip()
        if not line:
            if current_segment:
                segments.append(current_segment)
                current_segment = None
            continue

        match = timestamp_pattern.search(line)
        if match:
            if current_segment:
                segments.append(current_segment)
            g = match.groups()
            start_time = parse_time_match(g[0], g[1], g[2], g[3])
            end_time = parse_time_match(g[4], g[5], g[6], g[7])
            current_segment = {
                'start': start_time,
                'end': end_time,
                'text_lines': []
            }
        elif current_segment is not None:
            # Skip subtitle index lines (numeric lines before timestamp)
            if not current_segment['text_lines'] and line.isdigit():
                continue
            current_segment['text_lines'].append(line)

    if current_segment:
        segments.append(current_segment)

    final_segments = []
    for s in segments:
        text = " ".join(l for l in s['text_lines'] if l)
        cleaned_text = clean_text_for_tts(text)
        if cleaned_text:
            final_segments.append({
                'start': s['start'],
                'end': s['end'],
                'text': cleaned_text
            })

    final_segments.sort(key=lambda x: x['start'])
    return final_segments


def get_video_duration(video_path):
    """Gets video duration in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(res.stdout.strip())
    except Exception:
        return 0.0


def list_subtitle_streams(video_path):
    """Lists subtitle streams in a video using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "s",
        "-show_entries", "stream=index,codec_name:stream_tags=language,title",
        "-of", "json",
        video_path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            data = json.loads(res.stdout)
            streams = data.get("streams", [])
            text_codecs = {"subrip", "srt", "webvtt", "mov_text", "ass", "text"}
            valid_streams = []
            for s in streams:
                codec = s.get("codec_name", "").lower()
                if codec in text_codecs:
                    lang = s.get("tags", {}).get("language", "und")
                    title = s.get("tags", {}).get("title", "")
                    valid_streams.append({
                        "index": s.get("index"),
                        "codec": codec,
                        "language": lang,
                        "title": title
                    })
            return valid_streams
    except Exception as exc:
        print(f"[Subtitles] Listing failed: {exc}")
    return []


def parse_timestamp_to_seconds(ts):
    """Converts HH:MM:SS or MM:SS or SSS to float seconds."""
    ts = ts.strip()
    if not ts:
        return 0.0
    parts = ts.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        else:
            return float(parts[0])
    except Exception:
        return 0.0


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


class AudiobookTab(ttk.Frame):
    def __init__(self, parent, studio_win):
        super().__init__(parent, style="Root.TFrame", padding=10)
        self.studio_win = studio_win
        self.stop_event = threading.Event()

        # Variables
        self.ref_audio_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()
        self.voice_gender_var = tk.StringVar(value="male")
        self.voice_age_var = tk.StringVar(value="middle-aged")
        self.voice_pitch_var = tk.StringVar(value="moderate pitch")
        self.voice_style_var = tk.StringVar(value="")
        self.voice_accent_var = tk.StringVar(value="american accent")
        self.voice_var = tk.StringVar()
        self.temp_var = tk.DoubleVar(value=0.7)
        self.speed_var = tk.DoubleVar(value=1.0)
        self.steps_var = tk.IntVar(value=32)
        # Voice auditioning: each Sample is a fresh random voice; "Save Sample"
        # keeps the last one and uses it as the clone reference for the book.
        self.last_sample_path = os.path.abspath("quick_sample.wav")
        self.saved_voice_path = None
        self._sample_proc = None  # non-Windows sample playback process
        self.overwrite_existing_var = tk.BooleanVar(value=False)
        self.combine_mp3_var = tk.BooleanVar(value=True)
        self.mp3_name_var = tk.StringVar(value="final_output")
        self.status_var = tk.StringVar(value="Ready")
        self.sentence_info_var = tk.StringVar(value="")

        self._build_layout()
        self._update_voice_prompt()

        # Traces
        self.ref_audio_var.trace_add("write", self._on_ref_audio_changed)
        for var in (
            self.voice_gender_var,
            self.voice_age_var,
            self.voice_pitch_var,
            self.voice_style_var,
            self.voice_accent_var,
        ):
            var.trace_add("write", self._update_voice_prompt)
        self._on_ref_audio_changed()

    def _on_ref_audio_changed(self, *args):
        if hasattr(self, "voice_widgets") and hasattr(self, "voice_label"):
            if self.ref_audio_var.get().strip():
                for widget in self.voice_widgets:
                    widget.configure(state="disabled")
                self.voice_label.configure(style="DisabledBody.TLabel")
            else:
                for widget in self.voice_widgets:
                    widget.configure(state="readonly")
                self.voice_label.configure(style="Body.TLabel")

    def _update_voice_prompt(self, *args):
        parts = [
            self.voice_gender_var.get(),
            self.voice_age_var.get(),
            self.voice_pitch_var.get(),
            self.voice_style_var.get(),
            self.voice_accent_var.get(),
        ]
        self.voice_var.set(", ".join(part for part in parts if part))

    def _card(self, parent, title):
        frame = ttk.Frame(parent, style="Card.TFrame", padding=12)
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text=title, style="CardTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        return frame

    def _build_layout(self):
        self.columnconfigure(0, weight=1, minsize=520)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)

        left = ttk.Frame(self, style="Root.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        
        self._build_inputs_card(left).pack(fill="x", pady=(0, 8))
        self._build_settings_card(left).pack(fill="x", pady=(0, 8))

        self._build_text_card(self).grid(row=0, column=1, sticky="nsew")

        # Controls & Progress spans both columns (row 1)
        self._build_controls_card(self).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))

    def _build_inputs_card(self, parent):
        frame = self._card(parent, "Project Directories")
        body = ttk.Frame(frame, style="Card.TFrame")
        body.grid(row=1, column=0, sticky="ew")
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text="Ref Audio (.wav/.mp3):", style="Body.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(body, textvariable=self.ref_audio_var).grid(row=0, column=1, sticky="ew", pady=4)
        
        ref_btn_frame = ttk.Frame(body, style="Card.TFrame")
        ref_btn_frame.grid(row=0, column=2, padx=(8, 0), pady=4, sticky="w")
        ttk.Button(ref_btn_frame, text="Browse", command=self.browse_ref_file).pack(side="left")
        ttk.Button(ref_btn_frame, text="Clip 30s", command=self.clip_ref_audio).pack(side="left", padx=(4, 0))

        ttk.Label(body, text="Output Directory:", style="Body.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(body, textvariable=self.output_dir_var).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(body, text="Browse", command=self.browse_output_dir).grid(row=1, column=2, padx=(8, 0), pady=4, sticky="w")
        return frame

    def _build_text_card(self, parent):
        frame = self._card(parent, "Text Editor")
        frame.rowconfigure(1, weight=1)

        text_frame = ttk.Frame(frame, style="Card.TFrame")
        text_frame.grid(row=1, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self.text_input = tk.Text(
            text_frame,
            wrap="word",
            height=5,
            bg="#2b2b2b",
            fg="#e6e6e6",
            insertbackground="#e6e6e6",
            relief="flat",
            padx=10,
            pady=10,
            font=("Consolas", 10)
        )
        self.text_input.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.text_input.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text_input.configure(yscrollcommand=scrollbar.set)

        actions = ttk.Frame(frame, style="Card.TFrame")
        actions.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(actions, text="Load PDF/Text/EPUB", command=self.load_text).pack(side="left")
        return frame

    def _build_settings_card(self, parent):
        frame = self._card(parent, "Voice Settings")
        body = ttk.Frame(frame, style="Card.TFrame")
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)

        # Voice Profile Design section
        profile_frame = ttk.Frame(body, style="Card.TFrame", padding=(0, 0, 0, 8))
        profile_frame.pack(fill="x", expand=True)
        profile_frame.columnconfigure(0, weight=1)
        profile_frame.columnconfigure(1, weight=1)

        self.voice_label = ttk.Label(profile_frame, text="Voice Profile Design", style="CardTitle.TLabel")
        self.voice_label.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        fields_left = [
            ("Gender", self.voice_gender_var, VOICE_DESIGN_OPTIONS["Gender"]),
            ("Pitch", self.voice_pitch_var, VOICE_DESIGN_OPTIONS["Pitch"]),
            ("Accent", self.voice_accent_var, VOICE_DESIGN_OPTIONS["Accent"]),
        ]
        fields_right = [
            ("Age", self.voice_age_var, VOICE_DESIGN_OPTIONS["Age"]),
            ("Style", self.voice_style_var, VOICE_DESIGN_OPTIONS["Style"]),
        ]

        self.voice_widgets = []

        # Left Column
        for idx, (label, var, vals) in enumerate(fields_left):
            field = ttk.Frame(profile_frame, style="Card.TFrame")
            field.grid(row=idx + 1, column=0, sticky="ew", padx=(0, 4), pady=2)
            field.columnconfigure(1, weight=1)
            ttk.Label(field, text=label, style="Info.TLabel", width=8).grid(row=0, column=0, sticky="w")
            combo = ttk.Combobox(field, textvariable=var, values=vals, state="readonly")
            combo.grid(row=0, column=1, sticky="ew")
            self.voice_widgets.append(combo)

        # Right Column
        for idx, (label, var, vals) in enumerate(fields_right):
            field = ttk.Frame(profile_frame, style="Card.TFrame")
            field.grid(row=idx + 1, column=1, sticky="ew", padx=(4, 0), pady=2)
            field.columnconfigure(1, weight=1)
            ttk.Label(field, text=label, style="Info.TLabel", width=8).grid(row=0, column=0, sticky="w")
            combo = ttk.Combobox(field, textvariable=var, values=vals, state="readonly")
            combo.grid(row=0, column=1, sticky="ew")
            self.voice_widgets.append(combo)

        # Parameter Sliders section - Compact side-by-side gridding
        params_frame = ttk.Frame(body, style="Card.TFrame", padding=(0, 8, 0, 8))
        params_frame.pack(fill="x", expand=True)
        ttk.Label(params_frame, text="OmniVoice Generation Parameters", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 6))

        sliders_row = ttk.Frame(params_frame, style="Card.TFrame")
        sliders_row.pack(fill="x")
        for i in range(3):
            sliders_row.columnconfigure(i, weight=1, uniform="slider")

        numeric_fields = [
            ("Temp", self.temp_var, 0.1, 2.0, 0.1),
            ("Steps", self.steps_var, 4, 32, 1),
            ("Speed", self.speed_var, 0.5, 2.0, 0.05),
        ]
        for col, (label, variable, min_val, max_val, res) in enumerate(numeric_fields):
            field = ttk.Frame(sliders_row, style="Card.TFrame")
            field.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 6, 0))
            field.columnconfigure(1, weight=1)
            ttk.Label(field, text=label, style="Body.TLabel", width=6).grid(row=0, column=0, sticky="w")
            tk.Scale(
                field,
                from_=min_val,
                to=max_val,
                resolution=res,
                orient="horizontal",
                variable=variable,
                bg="#202020",
                fg="#e6e6e6",
                highlightthickness=0,
                troughcolor="#161616",
                width=10,
                length=90
            ).grid(row=0, column=1, sticky="ew")

        # Output options
        output_frame = ttk.Frame(body, style="Card.TFrame", padding=(0, 8, 0, 0))
        output_frame.pack(fill="x", expand=True)
        output_frame.columnconfigure(3, weight=1)

        ttk.Label(output_frame, text="Output Formatting Options", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))
        ttk.Checkbutton(output_frame, text="Overwrite WAVs", variable=self.overwrite_existing_var).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Checkbutton(output_frame, text="Combine MP3", variable=self.combine_mp3_var).grid(row=1, column=1, sticky="w", padx=(0, 8), pady=2)
        ttk.Label(output_frame, text="Name:", style="Info.TLabel").grid(row=1, column=2, sticky="w", padx=(0, 4), pady=2)
        ttk.Entry(output_frame, textvariable=self.mp3_name_var).grid(row=1, column=3, sticky="ew", pady=2)

        return frame

    def _build_controls_card(self, parent):
        # Combined Actions and Progress card to save massive vertical space
        frame = self._card(parent, "Controls & Progress")
        
        # Single action row: Voice Sample group on the left, everything else right
        btns_row = ttk.Frame(frame, style="Card.TFrame")
        btns_row.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        # Voice Sample workflow (audition -> stop -> save) on the left
        ttk.Label(btns_row, text="Voice Sample", style="Info.TLabel").pack(side="left", padx=(0, 10))
        ttk.Button(btns_row, text="Sample", style="Sample.TButton", command=self.generate_quick_sample).pack(side="left")
        ttk.Button(btns_row, text="Stop", style="SampleStop.TButton", command=self.stop_sample).pack(side="left", padx=(6, 0))
        ttk.Button(btns_row, text="Save Sample", command=self.save_sample).pack(side="left", padx=(6, 0))

        # Action buttons on the right (Generate on the far right). Packed in
        # reverse so they read left-to-right as: Export, Open Folder, Stop, Generate.
        self.generate_btn = ttk.Button(btns_row, text="Generate", style="Success.TButton", command=self.start_generation)
        self.generate_btn.pack(side="right", padx=(6, 0))
        ttk.Button(btns_row, text="Stop", style="Danger.TButton", command=self.stop_generation).pack(side="right", padx=(6, 0))
        ttk.Button(btns_row, text="Open Folder", command=self.open_output_folder).pack(side="right", padx=(6, 0))
        ttk.Button(btns_row, text="Export", command=self.export_sentence).pack(side="right", padx=(6, 0))

        # Progress elements
        prog_row = ttk.Frame(frame, style="Card.TFrame")
        prog_row.grid(row=2, column=0, sticky="ew")
        prog_row.columnconfigure(0, weight=1)
        prog_row.columnconfigure(1, weight=1)

        ttk.Label(prog_row, textvariable=self.sentence_info_var, style="Info.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 4))
        ttk.Label(prog_row, textvariable=self.status_var, style="Status.TLabel").grid(row=0, column=1, sticky="e", pady=(0, 4))
        
        self.progress_bar = ttk.Progressbar(prog_row, mode="determinate", maximum=1)
        self.progress_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 0))
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

    def clip_ref_audio(self):
        input_path = self.ref_audio_var.get().strip()
        if not input_path or not os.path.exists(input_path):
            messagebox.showerror("Error", "Please select a valid reference audio file first.")
            return

        initial_dir = os.path.dirname(input_path)
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        suggested_name = f"{base_name}_clipped.wav"
        
        output_path = filedialog.asksaveasfilename(
            title="Save Clipped Reference Audio",
            initialdir=initial_dir,
            initialfile=suggested_name,
            filetypes=[("WAV Audio", "*.wav"), ("MP3 Audio", "*.mp3"), ("All Files", "*.*")]
        )
        
        if not output_path:
            return

        self._set_status("Clipping reference audio...")
        
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-t", "30",
            output_path
        ]
        
        def run_clip():
            try:
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    self._ui(self.ref_audio_var.set, output_path)
                    self._set_status(f"Clipped reference saved: {os.path.basename(output_path)}")
                    self._ui(messagebox.showinfo, "Success", f"Reference audio clipped to 30s and saved to:\n{output_path}")
                else:
                    self._set_status("Clipping failed.")
                    self._ui(messagebox.showerror, "Error", f"FFmpeg clipping failed:\n{res.stderr}")
            except Exception as e:
                self._set_status("Clipping error.")
                self._ui(messagebox.showerror, "Error", f"An error occurred while clipping:\n{e}")

        threading.Thread(target=run_clip, daemon=True).start()

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


    def export_sentence(self):
        try:
            full_text = self._get_text().strip()
            sentences = VoiceCore.split_into_sentences(full_text)
            if not sentences:
                self.status_var.set("No sentences to export.")
                return

            sentence_id = simpledialog.askinteger("Export Sentence", f"Sentence number (1-{len(sentences)}):", parent=self, minvalue=1, maxvalue=len(sentences))
            if not sentence_id:
                return
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
        self.stop_event.clear()
        self._set_generate_enabled(False)
        threading.Thread(target=self._generate_speech, daemon=True).start()

    def stop_generation(self):
        self.stop_event.set()
        self.status_var.set("Stopping after current sentence...")

    def _generate_speech(self):
        prepared_ref_path = None
        try:
            output_directory = self.output_dir_var.get().strip() or os.path.dirname(os.path.abspath(__file__))
            self._ui(self.output_dir_var.set, output_directory)
            os.makedirs(output_directory, exist_ok=True)

            self._set_status("Loading model...")
            if not VoiceCore.ensure_model_loaded(
                status_cb=self._set_status,
                progress_cb=self._set_progress_mode,
                device_cb=self.studio_win.device_info_var.set
            ):
                self._set_status("Failed to load model.")
                return

            ref_path = self.ref_audio_var.get().strip()
            is_saved_voice = bool(ref_path) and ref_path == self.saved_voice_path
            if is_saved_voice:
                # Saved sample is already 24k mono; keep it full-length so it stays
                # in sync with its known transcript (SAMPLE_TEXT) for clean cloning.
                prepared_ref_path = ref_path
            else:
                prepared_ref_path = VoiceCore.prepare_ref_audio(ref_path) if ref_path else None
            voice_name = self.voice_var.get().strip()

            full_text = self._get_text().strip()
            if not full_text:
                self._set_status("No text found to synthesize.")
                if prepared_ref_path and prepared_ref_path != ref_path and os.path.exists(prepared_ref_path):
                    try:
                        os.remove(prepared_ref_path)
                    except OSError:
                        pass
                return

            all_sentences = VoiceCore.split_into_sentences(full_text)
            if not all_sentences:
                self._set_status("No sentences found to synthesize.")
                if prepared_ref_path and prepared_ref_path != ref_path and os.path.exists(prepared_ref_path):
                    try:
                        os.remove(prepared_ref_path)
                    except OSError:
                        pass
                return

            overwrite_existing = self.overwrite_existing_var.get()
            self._set_progress(0, len(all_sentences))
            speed_val = float(self.speed_var.get())
            steps_val = int(self.steps_var.get())

            # Voice consistency comes from cloning the reference clip. When the
            # reference is the saved sample we already know its transcript
            # (SAMPLE_TEXT), so we pass it and skip the Whisper ASR step.
            clone_ref_path = prepared_ref_path
            ref_text_val = SAMPLE_TEXT if (ref_path and ref_path == self.saved_voice_path) else None

            times = []
            output_files = []
            skipped_existing = 0
            stopped = False

            total_words_generated = 0
            total_time_elapsed = 0.0

            for idx, sentence in enumerate(all_sentences):
                if self.stop_event.is_set():
                    stopped = True
                    self._set_status(f"Stopped. Saved {len(output_files)} files so far.")
                    break

                out_path = os.path.join(output_directory, f"output_{idx + 1}.wav")
                if not overwrite_existing and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                    skipped_existing += 1
                    output_files.append(out_path)
                    self._set_progress(idx + 1, len(all_sentences))
                    self._set_sentence_info(f"Skipping existing sentence {idx + 1}/{len(all_sentences)} | Resume skipped: {skipped_existing}")
                    continue

                started = time.time()
                sentence_word_count = len(sentence.split())

                if times:
                    avg_time = (sum(times) / len(times)) / 60.0
                    remaining_sentences = len(all_sentences) - (idx + 1)
                    remaining_time = avg_time * remaining_sentences
                    wps = total_words_generated / total_time_elapsed if total_time_elapsed > 0 else 0.0
                    info = f"Processing sentence {idx + 1}/{len(all_sentences)} | Avg: {avg_time:.2f}m | Est. Remaining: {remaining_time:.2f}m | Speed: {wps:.1f} words/sec"
                else:
                    info = f"Processing sentence {idx + 1}/{len(all_sentences)}"

                self._set_sentence_info(info)
                self._set_status(f"Generating sentence {idx + 1}...")

                success = False
                for attempt in range(1, 4):
                    if self.stop_event.is_set():
                        break
                    try:
                        VoiceCore.synthesize_audio(
                            sentence,
                            out_path,
                            voice=voice_name,
                            ref_audio_path=clone_ref_path,
                            ref_text=ref_text_val,
                            speed=speed_val,
                            num_step=steps_val,
                            status_cb=self._set_status,
                            stop_event=self.stop_event,
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

                if self.stop_event.is_set():
                    stopped = True
                    if success and os.path.exists(out_path):
                        output_files.append(out_path)
                        self._set_progress(idx + 1, len(all_sentences))
                    self._set_status(f"Stopped. Saved {len(output_files)} files so far.")
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

            if not stopped:
                self._set_status(f"Done. Saved {len(output_files)} files. Skipped {skipped_existing} existing.")

            if not stopped and self.combine_mp3_var.get() and output_files:
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
            if prepared_ref_path and prepared_ref_path != ref_path and os.path.exists(prepared_ref_path):
                try:
                    os.remove(prepared_ref_path)
                except OSError:
                    pass
            self._set_generate_enabled(True)

    def generate_quick_sample(self):
        # Interrupt any sample still playing so the new one isn't talked over.
        self._stop_playback()

        def task():
            temp_out = self.last_sample_path
            try:
                self._set_status("Auditioning a new random voice...")
                if not VoiceCore.ensure_model_loaded(
                    status_cb=self._set_status,
                    progress_cb=self._set_progress_mode,
                    device_cb=self.studio_win.device_info_var.set
                ):
                    self._set_status("Failed to load model.")
                    return

                voice_name = self.voice_var.get().strip()
                speed_val = float(self.speed_var.get())
                steps_val = int(self.steps_var.get())

                # Always a fresh random voice so you can audition until you like
                # one, then click "Save Sample" to lock it in as the clone source.
                seed = random.randint(0, 2**31 - 1)
                VoiceCore.synthesize_audio(
                    SAMPLE_TEXT,
                    temp_out,
                    voice=voice_name,
                    speed=speed_val,
                    num_step=steps_val,
                    seed=seed,
                    status_cb=self._set_status,
                )

                self._set_status("Playing sample... Save Sample to keep it, or Sample again.")
                # Play asynchronously so the Stop Sample button can interrupt it.
                if sys.platform == "win32":
                    import winsound
                    winsound.PlaySound(temp_out, winsound.SND_FILENAME | winsound.SND_ASYNC)
                else:
                    self._sample_proc = subprocess.Popen(
                        ["aplay", temp_out],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
            except Exception as exc:
                traceback.print_exc()
                self._set_status(f"Sample error: {exc}")

        threading.Thread(target=task, daemon=True).start()

    def _stop_playback(self):
        """Silently stop any sample that is currently playing."""
        try:
            if sys.platform == "win32":
                import winsound
                winsound.PlaySound(None, winsound.SND_PURGE)
            elif self._sample_proc and self._sample_proc.poll() is None:
                self._sample_proc.terminate()
        except Exception:
            pass

    def stop_sample(self):
        """Stop the currently playing sample preview."""
        self._stop_playback()
        self._set_status("Sample playback stopped.")

    def save_sample(self):
        """Keep the last auditioned sample and set it as the clone reference."""
        if not os.path.exists(self.last_sample_path):
            messagebox.showinfo("Save Sample", "Generate a sample first (click 'Sample').")
            return
        out_dir = self.output_dir_var.get().strip() or os.path.dirname(os.path.abspath(__file__))
        saved_path = os.path.join(out_dir, "saved_voice.wav")
        try:
            shutil.copyfile(self.last_sample_path, saved_path)
        except OSError as exc:
            messagebox.showerror("Save Sample", f"Could not save voice: {exc}")
            return
        # Point the reference-audio field at the saved clip; generation will clone
        # it for every sentence, so the whole book uses this exact voice.
        self.saved_voice_path = saved_path
        self.ref_audio_var.set(saved_path)
        self._set_status(f"Voice saved. The book will now use this voice: {os.path.basename(saved_path)}")



class VideoDubberTab(ttk.Frame):
    def __init__(self, parent, studio_win):
        super().__init__(parent, style="Root.TFrame", padding=10)
        self.studio_win = studio_win
        self.stop_event = threading.Event()

        # Variables
        self.video_path_var = tk.StringVar()
        self.subtitle_path_var = tk.StringVar()
        self.embedded_sub_var = tk.StringVar(value="None (Use external file)")
        self.output_dir_var = tk.StringVar()
        self.output_name_var = tk.StringVar(value="dubbed_video")

        self.clone_voice_var = tk.BooleanVar(value=True)
        self.voice_gender_var = tk.StringVar(value="female")
        self.voice_age_var = tk.StringVar(value="young adult")
        self.voice_pitch_var = tk.StringVar(value="moderate pitch")
        self.voice_style_var = tk.StringVar(value="")
        self.voice_accent_var = tk.StringVar(value="american accent")
        self.voice_var = tk.StringVar()

        self.sync_mode_var = tk.StringVar(value="Auto-stretch")
        self.mix_mode_var = tk.StringVar(value="Duck original audio")
        self.ducking_factor_var = tk.DoubleVar(value=0.1)

        self.preview_mode_var = tk.BooleanVar(value=False)
        self.preview_start_var = tk.StringVar(value="00:00:00")
        self.preview_duration_var = tk.IntVar(value=5)

        self.temp_var = tk.DoubleVar(value=0.7)
        self.speed_var = tk.DoubleVar(value=1.0)
        self.steps_var = tk.IntVar(value=32)

        self.status_var = tk.StringVar(value="Ready")
        self.progress_info_var = tk.StringVar(value="")

        self.embedded_subs_list = []

        self._build_layout()
        self._update_voice_prompt()

        # Traces
        self.video_path_var.trace_add("write", self._on_video_path_changed)
        self.clone_voice_var.trace_add("write", self._on_clone_voice_changed)
        self.preview_mode_var.trace_add("write", self._on_preview_mode_changed)
        for var in (
            self.voice_gender_var,
            self.voice_age_var,
            self.voice_pitch_var,
            self.voice_style_var,
            self.voice_accent_var,
        ):
            var.trace_add("write", self._update_voice_prompt)

        self._on_clone_voice_changed()
        self._on_preview_mode_changed()

    def _on_video_path_changed(self, *args):
        path = self.video_path_var.get().strip()
        if path and os.path.exists(path):
            threading.Thread(target=self._detect_embedded_subs, args=(path,), daemon=True).start()
        else:
            self._ui(self._clear_embedded_subs)

    def _detect_embedded_subs(self, video_path):
        self._ui(self.status_var.set, "Checking for embedded subtitles...")
        streams = list_subtitle_streams(video_path)
        self.embedded_subs_list = streams
        
        def update_ui():
            if streams:
                options = ["None (Use external file)"]
                for s in streams:
                    desc = f"Track {s['index']}: {s['language'].upper()}"
                    if s['title']:
                        desc += f" - {s['title']}"
                    desc += f" ({s['codec']})"
                    options.append(desc)
                
                self.embedded_sub_combo.configure(state="readonly", values=options)
                self.embedded_sub_var.set(options[1])
                self.status_var.set(f"Found {len(streams)} embedded subtitle tracks. Auto-selected Track {streams[0]['index']}.")
            else:
                self._clear_embedded_subs()
                self.status_var.set("No text-based embedded subtitles found.")

        self._ui(update_ui)

    def _clear_embedded_subs(self):
        self.embedded_subs_list = []
        self.embedded_sub_combo.configure(state="disabled", values=["None (Use external file)"])
        self.embedded_sub_var.set("None (Use external file)")

    def _on_clone_voice_changed(self, *args):
        state = "disabled" if self.clone_voice_var.get() else "readonly"
        label_style = "DisabledBody.TLabel" if self.clone_voice_var.get() else "Body.TLabel"
        if hasattr(self, "voice_widgets") and hasattr(self, "voice_label"):
            for w in self.voice_widgets:
                w.configure(state=state)
            self.voice_label.configure(style=label_style)

    def _on_preview_mode_changed(self, *args):
        state = "normal" if self.preview_mode_var.get() else "disabled"
        if hasattr(self, "preview_start_entry") and hasattr(self, "preview_duration_scale"):
            self.preview_start_entry.configure(state=state)
            self.preview_duration_scale.configure(state=state)

    def _update_voice_prompt(self, *args):
        parts = [
            self.voice_gender_var.get(),
            self.voice_age_var.get(),
            self.voice_pitch_var.get(),
            self.voice_style_var.get(),
            self.voice_accent_var.get(),
        ]
        self.voice_var.set(", ".join(part for part in parts if part))

    def _card(self, parent, title):
        frame = ttk.Frame(parent, style="Card.TFrame", padding=12)
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text=title, style="CardTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        return frame

    def _build_layout(self):
        self.columnconfigure(0, weight=1, minsize=520)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)

        left = ttk.Frame(self, style="Root.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        self._build_inputs_card(left).pack(fill="x", pady=(0, 8))
        self._build_mixing_card(left).pack(fill="x", pady=(0, 8))
        self._build_preview_card(left).pack(fill="x")

        right = ttk.Frame(self, style="Root.TFrame")
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        
        self._build_voice_card(right).pack(fill="x", pady=(0, 8))

        # Controls & Progress spans both columns (row 1)
        self._build_controls_card(self).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))

    def _build_inputs_card(self, parent):
        frame = self._card(parent, "Media & Subtitles Setup")
        body = ttk.Frame(frame, style="Card.TFrame")
        body.grid(row=1, column=0, sticky="ew")
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text="Input Video:", style="Body.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(body, textvariable=self.video_path_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(body, text="Browse", command=self.browse_video_file).grid(row=0, column=2, padx=(8, 0), pady=4)

        ttk.Label(body, text="Subtitle (SRT/VTT):", style="Body.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(body, textvariable=self.subtitle_path_var).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(body, text="Browse", command=self.browse_subtitle_file).grid(row=1, column=2, padx=(8, 0), pady=4)

        ttk.Label(body, text="Embedded Subtitles:", style="Body.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=4)
        self.embedded_sub_combo = ttk.Combobox(body, textvariable=self.embedded_sub_var, values=["None (Use external file)"], state="disabled")
        self.embedded_sub_combo.grid(row=2, column=1, columnspan=2, sticky="ew", pady=4)

        ttk.Label(body, text="Output Directory:", style="Body.TLabel").grid(row=3, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(body, textvariable=self.output_dir_var).grid(row=3, column=1, sticky="ew", pady=4)
        ttk.Button(body, text="Browse", command=self.browse_output_dir).grid(row=3, column=2, padx=(8, 0), pady=4)

        name_frame = ttk.Frame(body, style="Card.TFrame")
        name_frame.grid(row=4, column=0, columnspan=3, sticky="ew", pady=4)
        name_frame.columnconfigure(1, weight=1)
        ttk.Label(name_frame, text="Output Video Name:", style="Body.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10))
        ttk.Entry(name_frame, textvariable=self.output_name_var).grid(row=0, column=1, sticky="ew")
        return frame

    def _build_mixing_card(self, parent):
        frame = self._card(parent, "Dubbing & Mixing Options")
        body = ttk.Frame(frame, style="Card.TFrame")
        body.grid(row=1, column=0, sticky="ew")
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        sync_frame = ttk.Frame(body, style="Card.TFrame")
        sync_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ttk.Label(sync_frame, text="Audio Sync Mode:", style="Body.TLabel").pack(anchor="w", pady=(0, 2))
        sync_combo = ttk.Combobox(sync_frame, textvariable=self.sync_mode_var, values=["Auto-stretch", "Keep original speed"], state="readonly")
        sync_combo.pack(fill="x")

        mix_frame = ttk.Frame(body, style="Card.TFrame")
        mix_frame.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        ttk.Label(mix_frame, text="Audio Mixing Mode:", style="Body.TLabel").pack(anchor="w", pady=(0, 2))
        mix_combo = ttk.Combobox(mix_frame, textvariable=self.mix_mode_var, values=["Duck original audio", "Replace original audio", "Mute original audio"], state="readonly")
        mix_combo.pack(fill="x")

        duck_frame = ttk.Frame(frame, style="Card.TFrame")
        duck_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        duck_frame.columnconfigure(1, weight=1)
        ttk.Label(duck_frame, text="Ducking Background Volume:", style="Body.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10))
        
        self.duck_scale = tk.Scale(
            duck_frame,
            from_=0.0,
            to=1.0,
            resolution=0.05,
            orient="horizontal",
            variable=self.ducking_factor_var,
            bg="#202020",
            fg="#e6e6e6",
            highlightthickness=0,
            troughcolor="#161616",
            label="Volume factor (0.1 = 10%)",
            width=10
        )
        self.duck_scale.grid(row=0, column=1, sticky="ew")
        return frame

    def _build_preview_card(self, parent):
        frame = self._card(parent, "Sub-section Testing (Preview Mode)")
        body = ttk.Frame(frame, style="Card.TFrame")
        body.grid(row=1, column=0, sticky="ew")
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        # Row 0: Checkbox and Start Time side-by-side
        ttk.Checkbutton(body, text="Process sub-section only", variable=self.preview_mode_var).grid(row=0, column=0, sticky="w", pady=(0, 6))

        start_frame = ttk.Frame(body, style="Card.TFrame")
        start_frame.grid(row=0, column=1, sticky="ew", pady=(0, 6))
        start_frame.columnconfigure(1, weight=1)
        ttk.Label(start_frame, text="Start (HH:MM:SS):", style="Info.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 4))
        self.preview_start_entry = ttk.Entry(start_frame, textvariable=self.preview_start_var, width=10)
        self.preview_start_entry.grid(row=0, column=1, sticky="w")

        # Row 1: Duration slider
        dur_frame = ttk.Frame(body, style="Card.TFrame")
        dur_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=2)
        dur_frame.columnconfigure(1, weight=1)
        
        ttk.Label(dur_frame, text="Duration (Minutes):", style="Body.TLabel", width=18).grid(row=0, column=0, sticky="w")
        self.preview_duration_scale = tk.Scale(
            dur_frame,
            from_=1,
            to=5,
            resolution=1,
            orient="horizontal",
            variable=self.preview_duration_var,
            bg="#202020",
            fg="#e6e6e6",
            highlightthickness=0,
            troughcolor="#161616",
            width=10
        )
        self.preview_duration_scale.grid(row=0, column=1, sticky="ew")
        return frame

    def _build_voice_card(self, parent):
        frame = self._card(parent, "Voice Settings")
        body = ttk.Frame(frame, style="Card.TFrame")
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)

        ttk.Checkbutton(body, text="Clone Speaker's Voice (Extract from Video Timeline)", variable=self.clone_voice_var).pack(anchor="w", pady=(0, 8))

        # Fallback profile frame
        voice_frame = ttk.Frame(body, style="Card.TFrame", padding=(0, 0, 0, 8))
        voice_frame.pack(fill="x")
        voice_frame.columnconfigure(0, weight=1)
        voice_frame.columnconfigure(1, weight=1)

        self.voice_label = ttk.Label(voice_frame, text="Fallback / Custom Design Voice", style="CardTitle.TLabel")
        self.voice_label.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        fields_left = [
            ("Gender", self.voice_gender_var, VOICE_DESIGN_OPTIONS["Gender"]),
            ("Pitch", self.voice_pitch_var, VOICE_DESIGN_OPTIONS["Pitch"]),
            ("Accent", self.voice_accent_var, VOICE_DESIGN_OPTIONS["Accent"]),
        ]
        fields_right = [
            ("Age", self.voice_age_var, VOICE_DESIGN_OPTIONS["Age"]),
            ("Style", self.voice_style_var, VOICE_DESIGN_OPTIONS["Style"]),
        ]

        self.voice_widgets = []

        # Left Column
        for idx, (label, var, vals) in enumerate(fields_left):
            field = ttk.Frame(voice_frame, style="Card.TFrame")
            field.grid(row=idx + 1, column=0, sticky="ew", padx=(0, 4), pady=2)
            field.columnconfigure(1, weight=1)
            ttk.Label(field, text=label, style="Info.TLabel", width=8).grid(row=0, column=0, sticky="w")
            combo = ttk.Combobox(field, textvariable=var, values=vals, state="readonly")
            combo.grid(row=0, column=1, sticky="ew")
            self.voice_widgets.append(combo)

        # Right Column
        for idx, (label, var, vals) in enumerate(fields_right):
            field = ttk.Frame(voice_frame, style="Card.TFrame")
            field.grid(row=idx + 1, column=1, sticky="ew", padx=(4, 0), pady=2)
            field.columnconfigure(1, weight=1)
            ttk.Label(field, text=label, style="Info.TLabel", width=8).grid(row=0, column=0, sticky="w")
            combo = ttk.Combobox(field, textvariable=var, values=vals, state="readonly")
            combo.grid(row=0, column=1, sticky="ew")
            self.voice_widgets.append(combo)

        # Generation parameters frame - Compact side-by-side gridding
        params_frame = ttk.Frame(body, style="Card.TFrame", padding=(0, 8, 0, 0))
        params_frame.pack(fill="x")
        ttk.Label(params_frame, text="OmniVoice Generation Parameters", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 6))

        sliders_row = ttk.Frame(params_frame, style="Card.TFrame")
        sliders_row.pack(fill="x")
        for i in range(3):
            sliders_row.columnconfigure(i, weight=1, uniform="slider")

        numeric_fields = [
            ("Temp", self.temp_var, 0.1, 2.0, 0.1),
            ("Steps", self.steps_var, 4, 32, 1),
            ("Speed", self.speed_var, 0.5, 2.0, 0.05),
        ]
        for col, (label, variable, min_val, max_val, res) in enumerate(numeric_fields):
            field = ttk.Frame(sliders_row, style="Card.TFrame")
            field.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 6, 0))
            field.columnconfigure(1, weight=1)
            ttk.Label(field, text=label, style="Body.TLabel", width=6).grid(row=0, column=0, sticky="w")
            tk.Scale(
                field,
                from_=min_val,
                to=max_val,
                resolution=res,
                orient="horizontal",
                variable=variable,
                bg="#202020",
                fg="#e6e6e6",
                highlightthickness=0,
                troughcolor="#161616",
                width=10,
                length=90
            ).grid(row=0, column=1, sticky="ew")

        return frame

    def _build_controls_card(self, parent):
        # Combined Actions and Progress card to save massive vertical space
        frame = self._card(parent, "Controls & Progress")
        
        # Action Buttons
        btns_row = ttk.Frame(frame, style="Card.TFrame")
        btns_row.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        
        # Utility buttons on the left
        ttk.Button(btns_row, text="Open Folder", command=self.open_output_folder).pack(side="left")
        
        # Action buttons on the right (Start Dubbing on the far right)
        self.generate_btn = ttk.Button(btns_row, text="Start Dubbing", style="Success.TButton", command=self.start_dubbing)
        self.generate_btn.pack(side="right", padx=(6, 0))
        ttk.Button(btns_row, text="Stop", style="Danger.TButton", command=self.stop_dubbing).pack(side="right", padx=(6, 0))

        # Progress elements
        prog_row = ttk.Frame(frame, style="Card.TFrame")
        prog_row.grid(row=2, column=0, sticky="ew")
        prog_row.columnconfigure(0, weight=1)
        prog_row.columnconfigure(1, weight=1)

        ttk.Label(prog_row, textvariable=self.progress_info_var, style="Info.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 4))
        ttk.Label(prog_row, textvariable=self.status_var, style="Status.TLabel").grid(row=0, column=1, sticky="e", pady=(0, 4))
        
        self.progress_bar = ttk.Progressbar(prog_row, mode="determinate", maximum=1)
        self.progress_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        return frame

    def _ui(self, callback, *args, **kwargs):
        self.after(0, lambda: callback(*args, **kwargs))

    def _set_status(self, text):
        self._ui(self.status_var.set, text)

    def _set_progress_info(self, text):
        self._ui(self.progress_info_var.set, text)

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
        state = "normal" if enabled else "disabled"
        self._ui(self.generate_btn.configure, state=state)

    def browse_video_file(self):
        fn = filedialog.askopenfilename(title="Select Video File", filetypes=[("Video Files", "*.mp4 *.mkv *.avi *.mov *.webm"), ("All Files", "*.*")])
        if fn:
            self.video_path_var.set(fn)
            if not self.output_dir_var.get():
                self.output_dir_var.set(os.path.dirname(fn))

    def browse_subtitle_file(self):
        fn = filedialog.askopenfilename(title="Select Subtitle File", filetypes=[("Subtitle Files", "*.srt *.vtt"), ("All Files", "*.*")])
        if fn:
            self.subtitle_path_var.set(fn)
            self.embedded_sub_var.set("None (Use external file)")

    def browse_output_dir(self):
        directory = filedialog.askdirectory(title="Select Output Directory")
        if directory:
            self.output_dir_var.set(directory)

    def open_output_folder(self):
        output_dir = self.output_dir_var.get().strip() or os.path.dirname(os.path.abspath(__file__))
        try:
            if sys.platform == "win32":
                os.startfile(output_dir)
            else:
                webbrowser.open(f"file://{output_dir}")
        except Exception as exc:
            self.status_var.set(f"Open folder error: {exc}")

    def start_dubbing(self):
        self.stop_event.clear()
        self._set_generate_enabled(False)
        threading.Thread(target=self._run_dubbing_pipeline, daemon=True).start()

    def stop_dubbing(self):
        self.stop_event.set()
        self._set_status("Stopping... will exit after current segment completes.")

    def _run_dubbing_pipeline(self):
        import numpy as np
        import soundfile as sf

        video_path = self.video_path_var.get().strip()
        subtitle_path = self.subtitle_path_var.get().strip()
        embedded_sub_selection = self.embedded_sub_var.get()
        output_dir = self.output_dir_var.get().strip()
        output_name = self.output_name_var.get().strip()

        temp_files = []

        if not video_path or not os.path.exists(video_path):
            messagebox.showerror("Error", "Please select a valid input video file.")
            self._set_generate_enabled(True)
            return

        use_embedded = (embedded_sub_selection != "None (Use external file)")

        if not use_embedded and (not subtitle_path or not os.path.exists(subtitle_path)):
            messagebox.showerror("Error", "Please select a valid subtitle file, or select an embedded subtitle track.")
            self._set_generate_enabled(True)
            return
        if not output_dir:
            messagebox.showerror("Error", "Please select a valid output directory.")
            self._set_generate_enabled(True)
            return
        if not output_name:
            output_name = "dubbed_video"

        try:
            os.makedirs(output_dir, exist_ok=True)

            if use_embedded:
                self._set_status("Extracting embedded subtitle track...")
                m = re.match(r"Track (\d+):", embedded_sub_selection)
                if not m:
                    messagebox.showerror("Error", f"Could not parse track index from selection: {embedded_sub_selection}")
                    self._set_generate_enabled(True)
                    return
                
                stream_idx = int(m.group(1))
                temp_extracted_srt = os.path.join(output_dir, f"temp_extracted_subtitles_{stream_idx}.srt")
                temp_files.append(temp_extracted_srt)

                cmd_extract_sub = [
                    "ffmpeg", "-y",
                    "-i", video_path,
                    "-map", f"0:{stream_idx}",
                    temp_extracted_srt
                ]
                res_sub = subprocess.run(cmd_extract_sub, capture_output=True, text=True)
                if res_sub.returncode != 0 or not os.path.exists(temp_extracted_srt) or os.path.getsize(temp_extracted_srt) < 10:
                    messagebox.showerror("Error", f"Failed to extract subtitle track {stream_idx} using FFmpeg.")
                    self._set_generate_enabled(True)
                    return

                subtitle_path = temp_extracted_srt

            self._set_status("Parsing subtitle file...")
            segments = parse_srt_or_vtt(subtitle_path)
            if not segments:
                self._set_status("Failed to parse subtitle segments or file is empty.")
                self._set_generate_enabled(True)
                return

            self._set_status("Calculating timeline...")
            full_video_duration = get_video_duration(video_path)
            if full_video_duration == 0.0 and segments:
                full_video_duration = segments[-1]['end'] + 10.0

            out_extension = os.path.splitext(video_path)[1] or ".mp4"
            crop_start = 0.0
            crop_duration = full_video_duration
            is_preview = self.preview_mode_var.get()

            if is_preview:
                crop_start = parse_timestamp_to_seconds(self.preview_start_var.get())
                crop_duration = float(self.preview_duration_var.get()) * 60.0

                crop_end = crop_start + crop_duration
                if crop_end > full_video_duration:
                    crop_end = full_video_duration
                    crop_duration = crop_end - crop_start

                filtered_segments = []
                for seg in segments:
                    if seg['start'] >= crop_start and seg['end'] <= crop_end:
                        filtered_segments.append({
                            'start': seg['start'] - crop_start,
                            'end': seg['end'] - crop_start,
                            'text': seg['text']
                        })
                segments = filtered_segments
                self._set_status(f"Preview mode: Processing {len(segments)} segments from {crop_start}s to {crop_end}s.")
                if not segments:
                    messagebox.showinfo("Preview Mode", f"No subtitle segments found within time range {crop_start}s to {crop_end}s.")
                    self._set_generate_enabled(True)
                    self._set_status("Ready")
                    return

            self._set_status("Extracting audio track from video...")
            temp_original_audio = os.path.join(output_dir, "temp_original_audio.wav")
            temp_files.append(temp_original_audio)

            if is_preview:
                temp_cropped_video = os.path.join(output_dir, "temp_cropped_video" + out_extension)
                temp_files.append(temp_cropped_video)
                
                cmd_trim = [
                    "ffmpeg", "-y",
                    "-ss", f"{crop_start:.3f}",
                    "-t", f"{crop_duration:.3f}",
                    "-i", video_path,
                    "-c", "copy",
                    temp_cropped_video
                ]
                self._set_status("Extracting sub-section video...")
                subprocess.run(cmd_trim, capture_output=True, check=True)
                
                try:
                    shutil.copy(temp_cropped_video, os.path.join(output_dir, f"{output_name}_undubbed_subsection{out_extension}"))
                except Exception as copy_exc:
                    print(f"[Preview Mode] Failed to save undubbed video copy: {copy_exc}")
                
                cmd_audio = [
                    "ffmpeg", "-y",
                    "-i", temp_cropped_video,
                    "-vn",
                    "-acodec", "pcm_s16le",
                    "-ar", "24000",
                    "-ac", "1",
                    temp_original_audio
                ]
                working_video = temp_cropped_video
            else:
                cmd_audio = [
                    "ffmpeg", "-y",
                    "-i", video_path,
                    "-vn",
                    "-acodec", "pcm_s16le",
                    "-ar", "24000",
                    "-ac", "1",
                    temp_original_audio
                ]
                working_video = video_path

            subprocess.run(cmd_audio, capture_output=True, check=True)

            self._set_status("Loading OmniVoice model (~2.5GB)...")
            if not VoiceCore.ensure_model_loaded(
                status_cb=self._set_status,
                progress_cb=self._set_progress_mode,
                device_cb=self.studio_win.device_info_var.set
            ):
                self._set_status("Failed to load model.")
                self._set_generate_enabled(True)
                return

            self._set_status("Reading audio data...")
            orig_audio_samples, sample_rate = sf.read(temp_original_audio)
            
            mix_mode = self.mix_mode_var.get()
            ducking_factor = float(self.ducking_factor_var.get())
            if mix_mode == "Mute original audio":
                dubbed_audio = np.zeros_like(orig_audio_samples)
            else:
                dubbed_audio = orig_audio_samples.copy()

            total_segments = len(segments)
            self._set_progress(0, total_segments)

            voice_name = self.voice_var.get().strip()
            speed_val = float(self.speed_var.get())
            steps_val = int(self.steps_var.get())
            clone_enabled = self.clone_voice_var.get()

            times = []
            total_words_generated = 0
            total_time_elapsed = 0.0

            for idx, seg in enumerate(segments):
                if self.stop_event.is_set():
                    self._set_status("Synthesis cancelled by user.")
                    break

                started = time.time()
                text = seg['text']
                start_time = seg['start']
                end_time = seg['end']
                target_duration = end_time - start_time
                word_count = len(text.split())

                if times:
                    avg_time = (sum(times) / len(times)) / 60.0
                    remaining = total_segments - idx
                    est_rem = avg_time * remaining
                    wps = total_words_generated / total_time_elapsed if total_time_elapsed > 0 else 0.0
                    info = f"Dubbing segment {idx + 1}/{total_segments} | Avg: {avg_time:.2f}m | Remaining: {est_rem:.2f}m | Speed: {wps:.1f} w/s\n'{text[:50]}...'"
                else:
                    info = f"Dubbing segment {idx + 1}/{total_segments}\n'{text[:50]}...'"

                self._set_progress_info(info)
                self._set_status(f"Generating segment {idx + 1}...")

                start_sample = int(start_time * sample_rate)
                end_sample = int(end_time * sample_rate)
                
                start_sample = max(0, min(start_sample, len(orig_audio_samples)))
                end_sample = max(0, min(end_sample, len(orig_audio_samples)))

                temp_ref_path = None
                use_cloning = False

                if clone_enabled and (end_sample > start_sample):
                    ref_slice = orig_audio_samples[start_sample:end_sample]
                    if len(ref_slice) >= 2400:
                        max_amplitude = np.max(np.abs(ref_slice))
                        if max_amplitude > 0.005:
                            temp_ref_path = os.path.join(output_dir, f"temp_ref_{idx}.wav")
                            sf.write(temp_ref_path, ref_slice, sample_rate)
                            temp_files.append(temp_ref_path)
                            use_cloning = True

                temp_dub_path = os.path.join(output_dir, f"temp_dub_{idx}.wav")
                temp_files.append(temp_dub_path)

                success = False
                for attempt in range(1, 4):
                    if self.stop_event.is_set():
                        break
                    try:
                        VoiceCore.synthesize_audio(
                            text,
                            temp_dub_path,
                            voice=voice_name,
                            ref_audio_path=temp_ref_path if use_cloning else None,
                            speed=speed_val,
                            num_step=steps_val,
                            status_cb=self._set_status,
                            stop_event=self.stop_event,
                            prepare_ref=True
                        )
                        success = True
                        break
                    except Exception as exc:
                        print(f"[Segment {idx+1}] Attempt {attempt} failed: {exc}")
                        if attempt < 3:
                            time.sleep(1)

                if self.stop_event.is_set():
                    break

                if not success:
                    print(f"[Segment {idx+1}] Skipping due to generation failure.")
                    self._set_progress(idx + 1, total_segments)
                    continue

                seg_samples, seg_sr = sf.read(temp_dub_path)
                seg_duration = len(seg_samples) / float(seg_sr)

                sync_mode = self.sync_mode_var.get()
                if sync_mode == "Auto-stretch" and target_duration > 0.1:
                    speed_ratio = seg_duration / target_duration
                    if 0.95 > speed_ratio or speed_ratio > 1.05:
                        temp_stretched_path = os.path.join(output_dir, f"temp_dub_stretched_{idx}.wav")
                        temp_files.append(temp_stretched_path)
                        
                        speed_ratio = max(0.5, min(speed_ratio, 2.0))
                        cmd_stretch = [
                            "ffmpeg", "-y",
                            "-i", temp_dub_path,
                            "-filter:a", f"atempo={speed_ratio:.4f}",
                            temp_stretched_path
                        ]
                        try:
                            subprocess.run(cmd_stretch, capture_output=True, check=True)
                            seg_samples, seg_sr = sf.read(temp_stretched_path)
                        except Exception as exc:
                            print(f"[AudioSync] FFmpeg speed stretch failed: {exc}")

                start_sample = int(start_time * sample_rate)
                N = len(seg_samples)
                
                if start_sample >= len(dubbed_audio):
                    continue
                if start_sample + N > len(dubbed_audio):
                    N = len(dubbed_audio) - start_sample
                    seg_samples = seg_samples[:N]

                if mix_mode == "Duck original audio" or mix_mode == "Replace original audio":
                    factor = 0.0 if mix_mode == "Replace original audio" else ducking_factor
                    
                    fade_samples = int(0.1 * sample_rate)
                    if N < fade_samples * 2:
                        fade_samples = N // 2

                    gain_env = np.ones(N) * factor
                    if fade_samples > 0:
                        for i in range(fade_samples):
                            gain_env[i] = 1.0 - (1.0 - factor) * (i / float(fade_samples))
                        for i in range(fade_samples):
                            gain_env[N - fade_samples + i] = factor + (1.0 - factor) * (i / float(fade_samples))

                    dubbed_audio[start_sample : start_sample + N] = dubbed_audio[start_sample : start_sample + N] * gain_env

                dubbed_audio[start_sample : start_sample + N] += seg_samples

                elapsed = time.time() - started
                times.append(elapsed)
                total_words_generated += word_count
                total_time_elapsed += elapsed
                self._set_progress(idx + 1, total_segments)
                gc.collect()

            if self.stop_event.is_set():
                self._set_status("Stopped by user. Cleaned up.")
                self._set_generate_enabled(True)
                return

            self._set_status("Saving final dubbed audio track...")
            temp_final_audio = os.path.join(output_dir, "temp_final_audio.wav")
            temp_files.append(temp_final_audio)
            sf.write(temp_final_audio, dubbed_audio, sample_rate)

            self._set_status("Combining dubbed audio and video streams...")
            if is_preview:
                final_output_video = os.path.join(output_dir, f"{output_name}_dubbed_subsection{out_extension}")
            else:
                final_output_video = os.path.join(output_dir, f"{output_name}{out_extension}")

            cmd_combine = [
                "ffmpeg", "-y",
                "-i", working_video,
                "-i", temp_final_audio,
                "-map", "0:v",
                "-map", "1:a",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                final_output_video
            ]
            subprocess.run(cmd_combine, capture_output=True, check=True)

            self._set_status("Done!")
            msg = f"Dubbed video successfully exported to:\n{final_output_video}"
            if is_preview:
                msg += f"\n\nAlso saved original undubbed subsection video:\n{output_name}_undubbed_subsection{out_extension}"
            self._set_progress_info(f"Dubbing complete!\nSaved to: {os.path.basename(final_output_video)}")
            messagebox.showinfo("Success", msg)

        except Exception as e:
            traceback.print_exc()
            self._set_status("An error occurred during dubbing.")
            messagebox.showerror("Dubbing Error", f"An error occurred:\n{e}")
        finally:
            self._set_status("Cleaning up temporary files...")
            for tf in temp_files:
                if os.path.exists(tf):
                    try:
                        os.remove(tf)
                    except OSError:
                        pass
            self._set_generate_enabled(True)
            self._set_progress_mode("determinate")


class OmniVoiceStudioWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OmniVoice Studio")
        self.geometry("1120x800") # Starting height; 50px taller for breathing room
        self.minsize(1000, 600)
        self.configure(bg="#161616")

        self.device_info_var = tk.StringVar(value="Active Device: Detecting...")

        self._configure_theme()
        self._build_layout()

        # Start device detection
        threading.Thread(target=self._detect_device, daemon=True).start()

    def _configure_theme(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        
        # Redesigned Dashboard Theme Colors
        style.configure("Root.TFrame", background="#161616")
        style.configure("Card.TFrame", background="#202020")
        
        style.configure("Title.TLabel", background="#161616", foreground="#a3e635", font=("Segoe UI", 18, "bold"))
        style.configure("Sub.TLabel", background="#161616", foreground="#8a8a8a", font=("Segoe UI", 10))
        
        # Sleek accent colored Card Titles
        style.configure("CardTitle.TLabel", background="#202020", foreground="#a3e635", font=("Segoe UI", 11, "bold"))
        
        style.configure("Body.TLabel", background="#202020", foreground="#e6e6e6")
        style.configure("DisabledBody.TLabel", background="#202020", foreground="#555555")
        style.configure("Info.TLabel", background="#202020", foreground="#8a8a8a")
        style.configure("Status.TLabel", background="#202020", foreground="#a3e635", font=("Segoe UI", 11, "bold"))
        
        style.configure("TEntry", fieldbackground="#2b2b2b", foreground="#e6e6e6")
        style.configure("TCombobox", fieldbackground="#2b2b2b", foreground="#e6e6e6")
        style.map("TCombobox", fieldbackground=[("readonly", "#2b2b2b")], foreground=[("readonly", "#e6e6e6")])
        style.configure("TCheckbutton", background="#202020", foreground="#8a8a8a")
        
        # Premium Modern Buttons
        # All buttons share padding=(10, 4) so they line up in a row regardless of style.
        style.configure("TButton", background="#2b2b2b", foreground="#e6e6e6", padding=(10, 4), font=("Segoe UI", 10))
        style.map("TButton", background=[("active", "#383838")])

        # Green success buttons for starts
        style.configure("Success.TButton", background="#a3e635", foreground="#161616", padding=(10, 4), font=("Segoe UI", 10, "bold"))
        style.map("Success.TButton", background=[("active", "#b6ee5c")])

        # Muted red danger buttons for stops
        style.configure("Danger.TButton", background="#c75d5d", foreground="#e6e6e6", padding=(10, 4), font=("Segoe UI", 10, "bold"))
        style.map("Danger.TButton", background=[("active", "#d97a7a")])

        # Voice Sample group: muted green + muted red so it reads calmer than the
        # primary Generate / Stop actions on the right.
        style.configure("Sample.TButton", background="#7cb342", foreground="#161616", padding=(10, 4), font=("Segoe UI", 10, "bold"))
        style.map("Sample.TButton", background=[("active", "#8bc34a")])

        style.configure("SampleStop.TButton", background="#b5564f", foreground="#e6e6e6", padding=(10, 4), font=("Segoe UI", 10, "bold"))
        style.map("SampleStop.TButton", background=[("active", "#c46b64")])
        
        style.configure("TProgressbar", troughcolor="#161616", background="#a3e635", bordercolor="#161616")

        # Tab notebook styling
        style.configure("TNotebook", background="#161616", borderwidth=0)
        style.configure("TNotebook.Tab", background="#202020", foreground="#8a8a8a", padding=10, font=("Segoe UI", 10, "bold"))
        style.map("TNotebook.Tab",
                  background=[("selected", "#a3e635")],
                  foreground=[("selected", "#161616")],
                  padding=[("selected", 10)])

    def _build_layout(self):
        root_frame = ttk.Frame(self, style="Root.TFrame", padding=14)
        root_frame.pack(fill="both", expand=True)
        root_frame.columnconfigure(0, weight=1)
        root_frame.rowconfigure(1, weight=1)

        # Header
        header = ttk.Frame(root_frame, style="Root.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="OmniVoice Studio", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self.device_info_var, style="Sub.TLabel").grid(row=0, column=1, sticky="e")

        # Notebook tabs
        self.notebook = ttk.Notebook(root_frame)
        self.notebook.grid(row=1, column=0, sticky="nsew")

        # Audiobook tab
        self.audiobook_tab = AudiobookTab(self.notebook, self)
        self.notebook.add(self.audiobook_tab, text="  Audiobook Studio  ")

        # Video Dubbing tab
        self.dubbing_tab = VideoDubberTab(self.notebook, self)
        self.notebook.add(self.dubbing_tab, text="  Video Dubbing Studio  ")

    def _detect_device(self):
        try:
            device_str = VoiceCore.get_active_device()
        except Exception:
            device_str = "CPU"
        self.after(0, lambda: self.device_info_var.set(f"Active Device: {device_str}"))


def main():
    app = OmniVoiceStudioWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
