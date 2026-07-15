import os
import sys
import threading
from collections import deque
import traceback
import types
from pathlib import Path
from datetime import timedelta
import time
import subprocess
import platform
import tempfile
import queue

# Compatibility patch for newer torchvision
try:
    import torchvision.transforms.functional as F
    functional_tensor = types.ModuleType("torchvision.transforms.functional_tensor")
    functional_tensor.rgb_to_grayscale = F.rgb_to_grayscale
    sys.modules["torchvision.transforms.functional_tensor"] = functional_tensor
except Exception:
    pass

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import cv2
import numpy as np
import torch

from basicsr.archs.rrdbnet_arch import RRDBNet
from basicsr.utils.download_util import load_file_from_url
from realesrgan import RealESRGANer


APP_TITLE = "📸 AI Image Upscaler"
APP_SUBTITLE = "Make your photos crystal clear - it's automatic!"

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff",
}

MODEL_DIR = Path(__file__).resolve().parent / "weights"

MODELS = {
    "⚡ Fast 2x (Quick, good quality)": {
        "filename": "RealESRGAN_x2plus.pth",
        "url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth",
        "scale": 2,
        "num_block": 23,
    },
    "🔧 Balanced 4x (Recommended)": {
        "filename": "RealESRGAN_x4plus.pth",
        "url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
        "scale": 4,
        "num_block": 23,
    },
    "✨ Anime 4x (For drawn images)": {
        "filename": "RealESRGAN_x4plus_anime_6B.pth",
        "url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth",
        "scale": 4,
        "num_block": 6,
    },
}

LEONARDO_MAX_SIZE_MB = 5
LEONARDO_MAX_SIZE_BYTES = LEONARDO_MAX_SIZE_MB * 1024 * 1024
LEONARDO_FORMATS = {".webp", ".jpg", ".jpeg", ".png"}


class UpscalerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("900x800")
        self.root.minsize(850, 750)

        self.input_paths = []
        self.output_folder = None
        self.app_state = "IDLE"
        self.model_name = tk.StringVar(value="🔧 Balanced 4x (Recommended)")
        self.outscale = tk.DoubleVar(value=4.0)
        self.tile = tk.IntVar(value=0)
        self.face_enhance = tk.BooleanVar(value=False)
        self.output_format = tk.StringVar(value="WEBP (smaller)")
        self.output_quality = tk.IntVar(value=92)
        self.leonardo_optimize = tk.BooleanVar(value=True)
        
        self.running = False
        self.stop_requested = False
        self.stop_event = threading.Event()
        self.start_time = None
        self.total_images = 0
        self.processed_images = 0
        self.cached_upsampler = None
        self.cached_face_enhancer = None

        # Thread communication queue for UI updates
        self.msg_queue = queue.Queue()

        # Live queue state with thread safety
        self.queue_lock = threading.RLock()
        self.pending_images = deque()
        self.queued_image_keys = set()
        self.skipped_files = set()
        self.current_image = None
        self.current_source_item = None
        self.queue_initialized = False

        self._setup_styles()
        self._setup_ui()
        
        # Start listening to the background thread immediately
        self.root.after(100, self._check_queue)

    def _check_queue(self):
        """Polls the queue for messages from the background thread to safely update the UI."""
        try:
            while True:
                msg_type, data = self.msg_queue.get_nowait()
                
                if msg_type == "log":
                    self.log_text.insert("end", str(data) + "\n")
                    self.log_text.see("end")
                    
                elif msg_type == "progress":
                    processed, total, elapsed = data
                    if total > 0:
                        progress_pct = int((processed / total) * 100)
                        self.progress["value"] = processed
                        self.progress_label.config(text=f"{progress_pct}%")
                        remaining = self.estimate_time(processed, total, elapsed)
                        self.time_label.config(text=f"⏱️ ~{remaining} remaining")
                    
                elif msg_type == "status":
                    self.process_info.config(text=str(data))
                    
                elif msg_type == "done":
                    self.running = False
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self.time_label.config(text="")
                    messagebox.showinfo("Done!", str(data))
                    
                elif msg_type == "error":
                    self.running = False
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    messagebox.showerror("Error", str(data))
                    
        except queue.Empty:
            pass
        finally:
            # Re-schedule the queue check
            self.root.after(100, self._check_queue)

    def _setup_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except:
            pass

        bg_color = "#f0f4f8"
        accent_color = "#2563eb"
        success_color = "#10b981"
        warning_color = "#f59e0b"
        
        style.configure("TFrame", background=bg_color)
        style.configure("TLabel", background=bg_color)
        style.configure("TLabelframe", background=bg_color)
        style.configure("TLabelframe.Label", background=bg_color)

        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"), background=bg_color, foreground="#1f2937")
        style.configure("Subtitle.TLabel", font=("Segoe UI", 10), background=bg_color, foreground="#6b7280")
        style.configure("Header.TLabel", font=("Segoe UI", 11, "bold"), background=bg_color, foreground="#1f2937")
        style.configure("Custom.TLabel", font=("Segoe UI", 10), background=bg_color)
        style.configure("Info.TLabel", font=("Segoe UI", 9), background=bg_color, foreground="#6b7280")
        style.configure("Warning.TLabel", font=("Segoe UI", 9), background=bg_color, foreground=warning_color)
        style.configure("Success.TLabel", font=("Segoe UI", 9), background=bg_color, foreground=success_color)

        style.configure("Primary.TButton", font=("Segoe UI", 11, "bold"))
        style.configure("Danger.TButton", font=("Segoe UI", 11, "bold"))
        style.configure("Secondary.TButton", font=("Segoe UI", 10))

        style.configure("Custom.TEntry", font=("Segoe UI", 10))
        style.configure("Custom.TCombobox", font=("Segoe UI", 10))
        style.configure("Custom.TCheckbutton", font=("Segoe UI", 10))
        style.configure("Custom.TRadiobutton", font=("Segoe UI", 10))

    def _setup_ui(self):
        main = ttk.Frame(self.root, padding=20)
        main.pack(fill="both", expand=True)

        # Header Section
        header_frame = ttk.Frame(main)
        header_frame.pack(fill="x", pady=(0, 20))

        ttk.Label(header_frame, text=APP_TITLE, style="Title.TLabel").pack(anchor="w")
        ttk.Label(header_frame, text=APP_SUBTITLE, style="Subtitle.TLabel").pack(anchor="w", pady=(2, 0))

        # Separator
        ttk.Separator(main, orient="horizontal").pack(fill="x", pady=(0, 15))

        # STEP 1: Select Images
        step1_frame = ttk.LabelFrame(main, text="Step 1: Select Your Images", padding=12)
        step1_frame.pack(fill="x", pady=(0, 15))

        button_row1 = ttk.Frame(step1_frame)
        button_row1.pack(fill="x", pady=(0, 8))

        ttk.Button(
            button_row1,
            text="📁 Select One Folder",
            command=self.select_single_folder,
            style="Primary.TButton",
        ).pack(side="left", padx=(0, 8))

        ttk.Button(
            button_row1,
            text="📁📁 Select Multiple Folders",
            command=self.select_multiple_folders,
            style="Primary.TButton",
        ).pack(side="left", padx=(0, 8))

        button_row2 = ttk.Frame(step1_frame)
        button_row2.pack(fill="x", pady=(0, 10))

        ttk.Button(
            button_row2,
            text="🖼️ Select One File",
            command=self.select_single_file,
            style="Primary.TButton",
        ).pack(side="left", padx=(0, 8))

        ttk.Button(
            button_row2,
            text="🖼️🖼️ Select Multiple Files",
            command=self.select_multiple_files,
            style="Primary.TButton",
        ).pack(side="left", padx=(0, 8))

        button_row3 = ttk.Frame(step1_frame)
        button_row3.pack(fill="x", pady=(0, 10))

        ttk.Button(
            button_row3,
            text="❌ Clear Selection",
            command=self.clear_selection,
            style="Secondary.TButton",
        ).pack(side="left")

        # Selected items display
        self.selection_frame = ttk.Frame(step1_frame)
        self.selection_frame.pack(fill="both", expand=True, pady=10)

        self.selection_text = tk.Text(
            self.selection_frame,
            height=5,
            width=80,
            font=("Segoe UI", 9),
            wrap="word",
            relief="solid",
            borderwidth=1,
        )
        self.selection_text.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(self.selection_frame, orient="vertical", command=self.selection_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.selection_text.configure(yscrollcommand=scrollbar.set)
        self.selection_text.config(state="disabled")

        self.selection_label = ttk.Label(step1_frame, text="No items selected", style="Info.TLabel")
        self.selection_label.pack(anchor="w", pady=(5, 0))

        # STEP 2: Choose Settings
        step2_frame = ttk.LabelFrame(main, text="Step 2: Choose Settings (Optional)", padding=12)
        step2_frame.pack(fill="x", pady=(0, 15))

        # Model selection
        model_row = ttk.Frame(step2_frame)
        model_row.pack(fill="x", pady=(0, 10))

        ttk.Label(model_row, text="Upscaling Quality:", style="Header.TLabel").pack(side="left", padx=(0, 10))

        model_combo = ttk.Combobox(
            model_row,
            textvariable=self.model_name,
            values=list(MODELS.keys()),
            state="readonly",
            width=40,
        )
        model_combo.pack(side="left")
        model_combo.bind("<<ComboboxSelected>>", self.on_model_changed)

        ttk.Label(step2_frame, text="💡 Recommended: Balanced 4x for most photos", style="Info.TLabel").pack(anchor="w", pady=(0, 10))

        # Scale selection
        scale_row = ttk.Frame(step2_frame)
        scale_row.pack(fill="x", pady=(0, 10))

        ttk.Label(scale_row, text="Size increase:", style="Header.TLabel").pack(side="left", padx=(0, 15))

        for text, value in [("2x bigger", 2.0), ("3x bigger", 3.0), ("4x bigger (best)", 4.0)]:
            ttk.Radiobutton(
                scale_row,
                text=text,
                variable=self.outscale,
                value=value,
                style="Custom.TRadiobutton",
            ).pack(side="left", padx=(0, 15))

        # Face enhance
        ttk.Checkbutton(
            step2_frame,
            text="✨ Enhance faces (make faces look better)",
            variable=self.face_enhance,
            style="Custom.TCheckbutton",
        ).pack(anchor="w", pady=(0, 10))

        # Memory usage tip
        tile_row = ttk.Frame(step2_frame)
        tile_row.pack(fill="x", pady=(0, 10))

        ttk.Label(tile_row, text="Memory mode:", style="Header.TLabel").pack(side="left", padx=(0, 10))

        tile_entry = ttk.Entry(tile_row, textvariable=self.tile, width=10, style="Custom.TEntry")
        tile_entry.pack(side="left")

        ttk.Label(
            tile_row,
            text="← Set to 0 for automatic (recommended). Use 256 only if computer says out of memory.",
            style="Info.TLabel",
        ).pack(side="left", padx=(10, 0))

        # Leonardo AI Settings
        leo_frame = ttk.LabelFrame(main, text="Step 3: File Format (Optional)", padding=12)
        leo_frame.pack(fill="x", pady=(0, 15))

        ttk.Checkbutton(
            leo_frame,
            text="📱 Optimize for AI apps (compress under 5MB) - for apps like Leonardo AI",
            variable=self.leonardo_optimize,
            style="Custom.TCheckbutton",
        ).pack(anchor="w", pady=(0, 10))

        format_quality_row = ttk.Frame(leo_frame)
        format_quality_row.pack(fill="x")

        ttk.Label(format_quality_row, text="Format:", style="Header.TLabel").pack(side="left", padx=(0, 10))

        format_combo = ttk.Combobox(
            format_quality_row,
            textvariable=self.output_format,
            values=["WEBP (smaller)", "JPG (standard)", "PNG (lossless)"],
            state="readonly",
            width=18,
        )
        format_combo.pack(side="left", padx=(0, 30))

        ttk.Label(format_quality_row, text="Quality:", style="Header.TLabel").pack(side="left", padx=(0, 10))

        self.quality_scale = ttk.Scale(
            format_quality_row,
            from_=50,
            to=100,
            orient="horizontal",
            variable=self.output_quality,
            length=150,
        )
        self.quality_scale.pack(side="left", padx=(0, 10))

        self.quality_label = ttk.Label(format_quality_row, text="92%", style="Header.TLabel", width=4)
        self.quality_label.pack(side="left")

        self.output_quality.trace("w", self._update_quality_label)

        ttk.Label(
            leo_frame,
            text="Recommended: WEBP at 92% quality (best compression)",
            style="Info.TLabel",
        ).pack(anchor="w", padx=(20, 0))

        # STEP 4: Process
        step4_frame = ttk.LabelFrame(main, text="Step 4: Process Images", padding=12)
        step4_frame.pack(fill="x", pady=(0, 15))

        self.process_info = ttk.Label(step4_frame, text="Ready to start", style="Info.TLabel")
        self.process_info.pack(anchor="w", pady=(0, 10))

        button_row = ttk.Frame(step4_frame)
        button_row.pack(fill="x", pady=(0, 10))

        self.start_button = ttk.Button(
            button_row,
            text="▶️ START UPSCALING",
            command=self.start_upscale_thread,
            style="Primary.TButton",
        )
        self.start_button.pack(side="left", padx=(0, 8))

        ttk.Button(
            button_row,
            text="⚙️ BENCHMARK",
            command=self.start_benchmark_thread,
            style="Secondary.TButton",
        ).pack(side="left", padx=(0, 8))

        self.stop_button = ttk.Button(
            button_row,
            text="⏹️ STOP",
            command=self.request_stop,
            style="Danger.TButton",
            state="disabled",
        )
        self.stop_button.pack(side="left")

        # Progress bars
        self.progress = ttk.Progressbar(step4_frame, mode="determinate", length=300)
        self.progress.pack(fill="x", pady=(0, 5))

        progress_label_row = ttk.Frame(step4_frame)
        progress_label_row.pack(fill="x")

        self.progress_label = ttk.Label(progress_label_row, text="0%", style="Custom.TLabel", width=5)
        self.progress_label.pack(side="left")

        self.time_label = ttk.Label(progress_label_row, text="", style="Info.TLabel")
        self.time_label.pack(side="left", padx=(20, 0))

        # Log
        log_frame = ttk.LabelFrame(main, text="Process Log", padding=8)
        log_frame.pack(fill="both", expand=True)

        self.log_text = tk.Text(
            log_frame,
            height=10,
            wrap="word",
            font=("Consolas", 9),
            relief="solid",
            borderwidth=1,
        )
        self.log_text.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")

        self.log_text.configure(yscrollcommand=scrollbar.set)

        self.log("✓ Ready to enhance your images!")
        self.log(f"Python: {sys.version.split()[0]}")
        self.log(f"PyTorch: {torch.__version__}")
        self.log(f"CUDA available: {torch.cuda.is_available()}")

        if torch.cuda.is_available():
            self.log(f"GPU: {torch.cuda.get_device_name(0)}")
        else:
            self.log("Running on CPU. Upscaling may be slow.")

    def _update_quality_label(self, *args):
        self.quality_label.config(text=f"{int(self.output_quality.get())}%")

    def on_model_changed(self, event=None):
        selected = self.model_name.get()
        model_info = MODELS.get(selected)
        if model_info:
            self.outscale.set(float(model_info["scale"]))

    def log(self, message):
        self.log_text.insert("end", str(message) + "\n")
        self.log_text.see("end")
        self.root.update_idletasks()

    def update_selection_display(self):
        """Update the display of selected files/folders"""
        if not self.input_paths:
            self.selection_text.config(state="normal")
            self.selection_text.delete("1.0", "end")
            self.selection_text.insert("1.0", "No items selected")
            self.selection_text.config(state="disabled")
            self.selection_label.config(text="No items selected")
            self.process_info.config(text="Select images first")
        else:
            total_images = 0
            display_text = ""
            
            for path in self.input_paths:
                p = Path(path)
                if p.is_file():
                    display_text += f"📄 {p.name}\n"
                    total_images += 1
                else:
                    images = [f for f in p.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS]
                    display_text += f"📁 {p.name} ({len(images)} images)\n"
                    total_images += len(images)

            self.selection_text.config(state="normal")
            self.selection_text.delete("1.0", "end")
            self.selection_text.insert("1.0", display_text)
            self.selection_text.config(state="disabled")
            
            self.selection_label.config(text=f"✓ {len(self.input_paths)} item(s) selected • {total_images} images total")
            self.process_info.config(text=f"Ready to upscale {total_images} image(s)")

    def select_single_folder(self):
        """Select a single folder"""
        folder = filedialog.askdirectory(title="Select one folder to upscale")
        if folder:
            if folder not in self.input_paths:
                self.input_paths.append(folder)
            self.update_selection_display()

    def select_multiple_folders(self):
        """Allow user to select multiple folders with yes/no prompt after each"""
        folders = []
        folder_count = 0
        
        while True:
            folder = filedialog.askdirectory(title=f"Select folder #{folder_count + 1}")
            if not folder:
                break
            
            folders.append(folder)
            folder_count += 1
            
            response = messagebox.askyesno(
                "Continue Selection?",
                f"Added: {Path(folder).name}\n\nDo you want to select more folders?"
            )
            
            if not response:
                break

        if folders:
            for folder in folders:
                if folder not in self.input_paths:
                    self.input_paths.append(folder)
            self.update_selection_display()
            messagebox.showinfo("Folders Selected", f"Added {len(folders)} folder(s) to process")

    def select_single_file(self):
        """Select a single file"""
        file = filedialog.askopenfilename(
            title="Select one image file",
            filetypes=[
                ("All Images", "*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff"),
                ("JPEG", "*.jpg *.jpeg"),
                ("PNG", "*.png"),
                ("WebP", "*.webp"),
                ("All files", "*.*"),
            ],
        )

        if file:
            if file not in self.input_paths:
                self.input_paths.append(file)
            self.update_selection_display()

    def select_multiple_files(self):
        """Allow user to select multiple files at once"""
        files = filedialog.askopenfilenames(
            title="Select multiple images (use Ctrl+Click or Shift+Click to select multiple)",
            filetypes=[
                ("All Images", "*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff"),
                ("JPEG", "*.jpg *.jpeg"),
                ("PNG", "*.png"),
                ("WebP", "*.webp"),
                ("All files", "*.*"),
            ],
        )

        if files:
            for file in files:
                if file not in self.input_paths:
                    self.input_paths.append(file)
            self.update_selection_display()
            messagebox.showinfo("Files Selected", f"Added {len(files)} file(s) to process")

    def clear_selection(self):
        """Clear all selected items"""
        self.input_paths = []
        self.update_selection_display()

    def get_images_from_path(self, path):
        """Get images from a path (file or folder, non-recursive)"""
        path = Path(path)

        if path.is_file():
            if path.suffix.lower() in IMAGE_EXTENSIONS:
                return [path]
            return []

        if path.is_dir():
            images = [f for f in path.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS]
            return images

        return []

    def get_output_path(self, input_path):
        """Determine output path - creates 'upscaled' folder in same location"""
        input_path = Path(input_path)

        if input_path.is_file():
            output_dir = input_path.parent / "upscaled"
        else:
            output_dir = input_path / "upscaled"

        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def get_model_path(self, model_info):
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        model_path = MODEL_DIR / model_info["filename"]

        if model_path.exists():
            return str(model_path)

        self.msg_queue.put(("log", f"⬇️ Downloading {model_info['filename']}... (happens only once)"))
        self.root.update_idletasks()

        downloaded_path = load_file_from_url(
            url=model_info["url"],
            model_dir=str(MODEL_DIR),
            progress=True,
            file_name=model_info["filename"],
        )

        return downloaded_path

    def create_upsampler(self):
        if self.cached_upsampler is not None:
            return self.cached_upsampler

        selected_model = self.model_name.get()
        model_info = MODELS[selected_model]

        model = RRDBNet(
            num_in_ch=3,
            num_out_ch=3,
            num_feat=64,
            num_block=model_info["num_block"],
            num_grow_ch=32,
            scale=model_info["scale"],
        )

        model_path = self.get_model_path(model_info)

        tile_value = int(self.tile.get())
        half = torch.cuda.is_available()

        upsampler = RealESRGANer(
            scale=model_info["scale"],
            model_path=model_path,
            model=model,
            tile=tile_value,
            tile_pad=10,
            pre_pad=0,
            half=half,
            gpu_id=0 if torch.cuda.is_available() else None,
        )

        self.cached_upsampler = upsampler
        return upsampler

    def create_face_enhancer(self, upsampler):
        if self.cached_face_enhancer is not None:
            return self.cached_face_enhancer

        if not self.face_enhance.get():
            return None

        try:
            from gfpgan import GFPGANer
        except Exception:
            self.msg_queue.put(("log", "⚠️ Face enhancement library not installed. Skipping face enhance."))
            return None

        try:
            face_model_url = "https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.3.pth"

            face_model_path = load_file_from_url(
                url=face_model_url,
                model_dir=str(MODEL_DIR),
                progress=True,
                file_name="GFPGANv1.3.pth",
            )

            face_enhancer = GFPGANer(
                model_path=face_model_path,
                upscale=int(self.outscale.get()),
                arch="clean",
                channel_multiplier=2,
                bg_upsampler=upsampler,
            )

            self.cached_face_enhancer = face_enhancer
            return face_enhancer

        except Exception as exc:
            self.msg_queue.put(("log", f"⚠️ Could not load face enhancement: {exc}"))
            return None

    def compress_for_leonardo(self, image, quality, output_format):
        """Compress image to meet Leonardo AI 5MB limit"""
        
        if output_format == "WEBP (smaller)":
            encode_param = [cv2.IMWRITE_WEBP_QUALITY, quality]
            ext = ".webp"
        elif output_format == "JPG (standard)":
            encode_param = [cv2.IMWRITE_JPEG_QUALITY, quality]
            ext = ".jpg"
        else:
            encode_param = [cv2.IMWRITE_PNG_COMPRESSION, 9]
            ext = ".png"

        _, encoded = cv2.imencode(ext, image, encode_param)
        file_size = len(encoded)

        if file_size > LEONARDO_MAX_SIZE_BYTES and output_format != "PNG (lossless)":
            current_quality = quality
            while file_size > LEONARDO_MAX_SIZE_BYTES and current_quality > 50:
                current_quality -= 5
                encode_param[-1] = current_quality
                _, encoded = cv2.imencode(ext, image, encode_param)
                file_size = len(encoded)

            if file_size > LEONARDO_MAX_SIZE_BYTES:
                scale_factor = (LEONARDO_MAX_SIZE_BYTES / file_size) ** 0.5
                height, width = image.shape[:2]
                new_width = int(width * scale_factor)
                new_height = int(height * scale_factor)
                image = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_AREA)
                _, encoded = cv2.imencode(ext, image, encode_param)
                file_size = len(encoded)

        return encoded, file_size

    def estimate_time(self, processed, total, elapsed):
        """Estimate time remaining"""
        if processed == 0:
            return "Calculating..."
        
        time_per_image = elapsed / processed
        remaining_images = total - processed
        remaining_seconds = time_per_image * remaining_images
        
        return str(timedelta(seconds=int(remaining_seconds)))

    def upscale_one_image_safe(self, image_path, output_dir, upsampler, face_enhancer, config):
        """Windows Unicode Safe: Read/write files via binary buffer"""
        if self.stop_event.is_set() or self.stop_requested:
            return None

        image_path = Path(image_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Windows Unicode Fix: Read file safely via raw binary stream buffer
        img_array = np.fromfile(str(image_path), dtype=np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_UNCHANGED)

        if img is None:
            raise RuntimeError(f"Could not read image file structure")

        outscale_value = config["outscale"]

        if face_enhancer is not None:
            _, _, output = face_enhancer.enhance(
                img,
                has_aligned=False,
                only_center_face=False,
                paste_back=True,
            )
        else:
            output, _ = upsampler.enhance(img, outscale=outscale_value)

        # Match output configuration extensions
        format_choice = config["output_format"]
        if format_choice == "WEBP (smaller)":
            ext = ".webp"
        elif format_choice == "JPG (standard)":
            ext = ".jpg"
        else:
            ext = ".png"

        output_filename = image_path.stem + f"_upscaled_x{outscale_value:g}{ext}"
        output_path = output_dir / output_filename

        # Process via our optimized scaling loop
        if config["leonardo_optimize"]:
            quality = config["output_quality"]
            encoded, file_size = self.compress_for_leonardo(output, quality, format_choice)
            
            with open(output_path, "wb") as f:
                f.write(encoded)
            
            return output_path, file_size
        else:
            # Windows Unicode Fix: Write out file safely via binary stream write
            success, encoded_img = cv2.imencode(ext, output)
            if not success:
                raise RuntimeError("Could not compress processed frame layout")
                
            with open(output_path, "wb") as f:
                f.write(encoded_img)

            file_size = output_path.stat().st_size
            return output_path, file_size

    def request_stop(self):
        """Request to stop processing"""
        self.stop_requested = True
        self.stop_event.set()
        self.msg_queue.put(("log", "⏹️ Stopping after current image..."))

    def run_upscale_worker(self, config):
        """Runs entirely in background. Pushes all UI updates to the thread-safe queue."""
        try:
            all_images = []
            folder_mapping = {}

            for path in config["input_paths"]:
                images = self.get_images_from_path(path)
                for img in images:
                    all_images.append(img)
                    folder_mapping[str(img)] = path

            if not all_images:
                self.msg_queue.put(("error", "No valid images found in the selected locations."))
                return

            self.total_images = len(all_images)
            self.processed_images = 0
            self.start_time = time.time()

            self.msg_queue.put(("log", ""))
            self.msg_queue.put(("log", f"🚀 Starting to upscale {self.total_images} image(s)..."))
            self.msg_queue.put(("log", f"Model: {config['model_name']}"))
            self.msg_queue.put(("log", f"Size: {config['outscale']:g}x larger"))
            self.msg_queue.put(("log", ""))
            
            self.root.after(0, lambda: self.progress.config(maximum=max(self.total_images, 1)))

            self.msg_queue.put(("log", "📥 Loading AI model..."))
            upsampler = self.create_upsampler()

            face_enhancer = self.create_face_enhancer(upsampler)
            if face_enhancer:
                self.msg_queue.put(("log", "✓ Face enhancement ready"))

            for image_path in all_images:
                if self.stop_event.is_set() or self.stop_requested:
                    self.msg_queue.put(("log", "⏹️ Stopped by user."))
                    break

                self.processed_images += 1
                elapsed = time.time() - self.start_time
                
                self.msg_queue.put(("progress", (self.processed_images, self.total_images, elapsed)))

                source_path = folder_mapping[str(image_path)]
                output_dir = self.get_output_path(source_path)

                self.msg_queue.put(("log", f"[{self.processed_images}/{self.total_images}] Enhancing: {image_path.name}..."))
                self.msg_queue.put(("status", f"Processing image {self.processed_images} of {self.total_images}"))

                try:
                    saved_path, file_size = self.upscale_one_image_safe(
                        image_path=image_path,
                        output_dir=output_dir,
                        upsampler=upsampler,
                        face_enhancer=face_enhancer,
                        config=config
                    )

                    file_size_mb = file_size / 1024 / 1024
                    self.msg_queue.put(("log", f"  ✓ Saved ({file_size_mb:.1f}MB)"))

                    if config["leonardo_optimize"] and file_size > LEONARDO_MAX_SIZE_BYTES:
                        self.msg_queue.put(("log", f"  ⚠️ Still {file_size_mb:.1f}MB (over 5MB limit)"))

                except Exception as exc:
                    self.msg_queue.put(("log", f"  ❌ Error: {str(exc)}"))
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()

            elapsed = time.time() - self.start_time
            if not self.stop_requested:
                success_msg = f"✅ All done! Processed {self.processed_images} images in {str(timedelta(seconds=int(elapsed)))}"
                self.msg_queue.put(("log", ""))
                self.msg_queue.put(("log", success_msg))
                self.msg_queue.put(("done", f"Upscaled {self.processed_images} image(s) successfully!\nAll files saved to 'upscaled' folders."))
            else:
                self.msg_queue.put(("done", "Process stopped by user."))

        except Exception as exc:
            self.msg_queue.put(("log", f"\n❌ Fatal Engine Error: {str(exc)}"))
            self.msg_queue.put(("error", f"Fatal processing error:\n{str(exc)}"))

    def start_upscale_thread(self):
        if self.running:
            messagebox.showinfo("Already running", "Upscaling is already in progress.")
            return

        if not self.input_paths:
            messagebox.showwarning("No Images Selected", "Please select at least one image or folder first.")
            return

        self.running = True
        self.stop_requested = False
        self.stop_event = threading.Event()
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.progress["value"] = 0
        self.progress_label.config(text="0%")

        # CRITICAL: Extract configuration safely on the main thread
        config = {
            "model_name": self.model_name.get(),
            "outscale": float(self.outscale.get()),
            "tile": int(self.tile.get()),
            "face_enhance": self.face_enhance.get(),
            "output_format": self.output_format.get(),
            "output_quality": self.output_quality.get(),
            "leonardo_optimize": self.leonardo_optimize.get(),
            "input_paths": list(self.input_paths)
        }

        thread = threading.Thread(target=self.run_upscale_worker, args=(config,), daemon=True)
        thread.start()

    def start_benchmark_thread(self):
        if self.running:
            messagebox.showinfo("Benchmark", "Stop the active queue before running a benchmark.")
            return
        
        if not self.input_paths:
            messagebox.showinfo("Benchmark", "Add at least one image or folder to the queue first.")
            return
            
        self.start_button.configure(state="disabled")
        thread = threading.Thread(target=self.run_benchmark, daemon=True)
        thread.start()

    def run_benchmark(self):
        """Benchmark current AI settings"""
        try:
            self.msg_queue.put(("log", ""))
            self.msg_queue.put(("log", f"⚙ Benchmarking settings..."))
            self.msg_queue.put(("log", f"Model: {self.model_name.get()} • Scale: {self.outscale.get():g}x"))
            
            # Get first image
            test_image = None
            for path in self.input_paths:
                images = self.get_images_from_path(path)
                if images:
                    test_image = images[0]
                    break
            
            if test_image is None:
                messagebox.showinfo("Benchmark", "Add at least one image first.")
                return

            benchmark_start = time.perf_counter()
            img = cv2.imread(str(test_image), cv2.IMREAD_UNCHANGED)
            
            if img is None:
                raise RuntimeError("Could not read benchmark image")

            self.cached_upsampler = None
            upsampler = self.create_upsampler()
            face_enhancer = self.create_face_enhancer(upsampler)

            inference_start = time.perf_counter()
            if face_enhancer:
                _, _, output = face_enhancer.enhance(img, has_aligned=False, only_center_face=True, paste_back=True)
            else:
                output, _ = upsampler.enhance(img, outscale=float(self.outscale.get()))
            
            inference_seconds = time.perf_counter() - inference_start
            total_seconds = time.perf_counter() - benchmark_start

            self.msg_queue.put(("log", f"Inference time: {inference_seconds:.1f}s"))
            self.msg_queue.put(("log", f"Total time: {total_seconds:.1f}s"))

            messagebox.showinfo("Benchmark Complete", f"Inference took {inference_seconds:.1f} seconds\nTotal: {total_seconds:.1f} seconds")

        except Exception as exc:
            self.msg_queue.put(("log", f"❌ Benchmark error: {exc}"))
            messagebox.showerror("Benchmark Error", str(exc))
        finally:
            self.cached_upsampler = None
            self.cached_face_enhancer = None
            self.start_button.configure(state="normal")
            self.root.update_idletasks()


def main():
    root = tk.Tk()
    app = UpscalerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
