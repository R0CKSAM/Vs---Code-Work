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
APP_SUBTITLE = ""

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
        self.root.geometry("760x620")
        self.root.minsize(720, 560)

        self.input_paths = []  # Single source of truth for queue
        self.output_folder = None
        self.app_state = "IDLE"
        self.model_name = tk.StringVar(value="✨ Anime 4x (For drawn images)")
        self.outscale = tk.DoubleVar(value=4.0)
        self.tile = tk.IntVar(value=0)
        self.face_enhance = tk.BooleanVar(value=True)
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

        # Live queue state
        self.queue_lock = threading.RLock()
        self.pending_images = deque()
        self.queued_image_keys = set()
        self.skipped_files = set()
        self.current_image = None
        self.current_source_item = None
        self.queue_initialized = False

        self._setup_style()
        self._setup_ui()
        self._setup_styles()

    def _setup_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except:
            pass

        # Configure colors - professional blue theme
        bg_color = "#F8F1E7"
        accent_color = "#B8860B"  # Professional blue
        success_color = "#8A9A5B"
        warning_color = "#B8860B"
        
        style.configure("TFrame", background=bg_color)
        style.configure("TLabel", background=bg_color)
        style.configure("TLabelframe", background=bg_color)
        style.configure("TLabelframe.Label", background=bg_color)

        style.configure("Title.TLabel", font=("Segoe UI", 14, "bold"), background=bg_color, foreground="#1f2937")
        style.configure("Subtitle.TLabel", font=("Segoe UI", 9), background=bg_color, foreground="#6b7280")
        style.configure("Header.TLabel", font=("Segoe UI", 9, "bold"), background=bg_color, foreground="#1f2937")
        style.configure("Custom.TLabel", font=("Segoe UI", 9), background=bg_color)
        style.configure("Info.TLabel", font=("Segoe UI", 9), background=bg_color, foreground="#6b7280")
        style.configure("Warning.TLabel", font=("Segoe UI", 9), background=bg_color, foreground=warning_color)
        style.configure("Success.TLabel", font=("Segoe UI", 9), background=bg_color, foreground=success_color)

        # Button styles
        style.configure("Primary.TButton", font=("Segoe UI", 9, "bold"))
        style.configure("Danger.TButton", font=("Segoe UI", 9, "bold"))
        style.configure("Secondary.TButton", font=("Segoe UI", 9))

        style.configure("Custom.TEntry", font=("Segoe UI", 9))
        style.configure("Custom.TCombobox", font=("Segoe UI", 9))
        style.configure("Custom.TCheckbutton", font=("Segoe UI", 9))
        style.configure("Custom.TRadiobutton", font=("Segoe UI", 9))

    def _setup_style(self):
        pass  # Replaced by _setup_styles


    def create_color_toggle(self, parent, text, variable):
        def update_color():
            if variable.get():
                btn.configure(
                    text="✓ ON  " + text,
                    bg="#2E8B57",
                    fg="white",
                    activebackground="#3CB371"
                )
            else:
                btn.configure(
                    text="✕ OFF " + text,
                    bg="#B22222",
                    fg="white",
                    activebackground="#CD5C5C"
                )

        btn = tk.Checkbutton(
            parent,
            variable=variable,
            command=update_color,
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=10,
            pady=3
        )
        update_color()
        return btn

    def _setup_ui(self):
        main = ttk.Frame(self.root, padding=8)
        main.pack(fill="both", expand=True)

        # Minimal top spacing (no header)

        # Main content in notebook style
        # Upload Section - Minimal Design
        upload_frame = ttk.LabelFrame(main, text="Upload", padding=8)
        upload_frame.pack(fill="x", pady=(0, 8))

        upload_row = ttk.Frame(upload_frame)
        upload_row.pack(fill="x")

        ttk.Button(
            upload_row,
            text="Folder",
            command=self.select_single_folder,
            style="Primary.TButton",
        ).pack(side="left", padx=(0, 8))

        ttk.Button(
            upload_row,
            text="File",
            command=self.select_multiple_files,
            style="Primary.TButton",
        ).pack(side="left")

        self.selection_frame = ttk.Frame(upload_frame)
        self.selection_frame.pack(fill="both", expand=True, pady=6)

        self.selection_text = tk.Listbox(
            self.selection_frame,
            height=3,
            font=("Segoe UI", 9),
            relief="solid",
            borderwidth=1,
            selectmode="extended"
        )
        self.selection_text.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(
            self.selection_frame,
            orient="vertical",
            command=self.selection_text.yview
        )
        scrollbar.pack(side="right", fill="y")

        self.selection_text.configure(yscrollcommand=scrollbar.set)
        self.selection_text.config(state="normal")

        remove_row = ttk.Frame(upload_frame)
        remove_row.pack(fill="x")

        self.selection_hint = ttk.Label(upload_frame, text="Click item to select • Ctrl/Shift for multiple", style="Info.TLabel")
        self.selection_hint.pack(anchor="w")

        self.selection_label = ttk.Label(
            remove_row,
            text="No items selected",
            style="Info.TLabel"
        )
        self.selection_label.pack(side="left")

        ttk.Button(
            remove_row,
            text="Remove Selected",
            command=self.remove_selected_item,
            style="Secondary.TButton",
        ).pack(side="right")

        self.skip_button = ttk.Button(
            remove_row,
            text="Skip Selected File",
            command=self.skip_selected_file,
            style="Secondary.TButton",
            state="disabled",
        )
        self.skip_button.pack(side="right", padx=(0, 8))

        # STEP 2: Choose Settings
        step2_frame = ttk.LabelFrame(main, text="Settings", padding=6)
        step2_frame.pack(fill="x", pady=(0, 5))

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
        self.create_color_toggle(
            step2_frame,
            "AI Face Enhance",
            self.face_enhance
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
        leo_frame = ttk.LabelFrame(main, text="Settings", padding=6)
        leo_frame.pack(fill="x", pady=(0, 5))

        self.create_color_toggle(
            leo_frame,
            "Leonardo AI Compress (under 5MB)",
            self.leonardo_optimize
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

        # STEP 4: Process
        step4_frame = ttk.LabelFrame(main, text="4. Process", padding=6)
        step4_frame.pack(fill="x", pady=(0, 5))

        self.process_info = ttk.Label(step4_frame, text="Ready to start", style="Info.TLabel")
        self.process_info.pack(anchor="w", pady=(0, 10))

        button_row = ttk.Frame(step4_frame)
        button_row.pack(fill="x", pady=(0, 10))

        self.start_button = ttk.Button(
            button_row,
            text="▶ Start",
            command=self.start_upscale_thread,
            style="Primary.TButton",
        )
        self.start_button.pack(side="left", padx=(0, 8))

        self.stop_button = ttk.Button(
            button_row,
            text="■ Stop",
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
        log_frame = ttk.LabelFrame(main, text="Log", padding=5)
        log_frame.pack(fill="both", expand=True)

        self.log_text = tk.Text(
            log_frame,
            height=5,
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
        if torch.cuda.is_available():
            self.log(f"✓ GPU detected: {torch.cuda.get_device_name(0)} - Fast processing!")
        else:
            self.log("📝 Running on CPU - slower but will work. GPU recommended for large batches.")

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


    def get_queue_image_count(self):
        total = 0
        for path in self.input_paths:
            try:
                total += len(self.get_images_from_path(path))
            except Exception:
                pass
        return total

    def get_queue_summary(self):
        items = []
        for path in self.input_paths:
            p = Path(path)
            try:
                if p.is_file():
                    items.append(f"📄 {p.name} (1 image)")
                else:
                    items.append(f"📁 {p.name} ({len(self.get_images_from_path(path))} images)")
            except Exception:
                items.append(f"⚠ Missing: {p.name}")
        return items

    def refresh_queue_display(self):
        if hasattr(self, "selection_text"):
            self.selection_text.delete(0, "end")
            for item in self.get_queue_summary():
                self.selection_text.insert("end", item)

        if hasattr(self, "selection_label"):
            self.selection_label.config(
                text=f"Queue: {len(self.input_paths)} item(s) • {self.get_queue_image_count()} images"
            )

    def clear_queue(self):
        self.input_paths.clear()
        self.update_selection_display()

    def update_selection_display(self):
        """Update the display of selected files/folders"""
        if not self.input_paths:
            self.selection_text.config(state="normal")
            self.selection_text.delete(0, "end")
            self.selection_text.insert("end", "No items selected")
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
                    # Count images in folder (non-recursive)
                    images = [f for f in p.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS]
                    display_text += f"📁 {p.name} ({len(images)} images)\n"
                    total_images += len(images)

            self.selection_text.config(state="normal")
            self.selection_text.delete(0, "end")
            for item in display_text.strip().split("\n"):
                if item:
                    self.selection_text.insert("end", "✓ " + item)
            
            self.selection_label.config(text=f"✓ {len(self.input_paths)} item(s) selected • {total_images} images total")
            self.process_info.config(text=f"Ready to upscale {total_images} image(s)")

    def _path_contains_current_image(self, path):
        if self.current_image is None:
            return False
        p = Path(path)
        current = Path(self.current_image)
        if p.is_file():
            return current == p
        try:
            return current.parent == p
        except Exception:
            return False

    def _remove_pending_for_source(self, source_path):
        source_path = str(source_path)
        with self.queue_lock:
            kept = deque()
            removed = 0
            while self.pending_images:
                image_path, source_item = self.pending_images.popleft()
                if str(source_item) == source_path:
                    self.queued_image_keys.discard(str(Path(image_path).resolve()))
                    removed += 1
                else:
                    kept.append((image_path, source_item))
            self.pending_images = kept
        return removed

    def remove_selected_item(self):
        try:
            selected_indices = list(self.selection_text.curselection())
            if not selected_indices:
                messagebox.showinfo("Remove", "Select one or more items from the list first.")
                return

            paths_to_remove = []
            for index in selected_indices:
                if index < len(self.input_paths):
                    paths_to_remove.append(self.input_paths[index])

            blocked = [p for p in paths_to_remove if self.running and self._path_contains_current_image(p)]
            if blocked:
                messagebox.showwarning(
                    "Cannot Remove Active Folder",
                    "The currently processing file or folder cannot be removed. "
                    "Select a pending item, or use 'Skip Selected File' for an individual image."
                )
                paths_to_remove = [p for p in paths_to_remove if p not in blocked]

            total_removed = 0
            for path in paths_to_remove:
                if path in self.input_paths:
                    self.input_paths.remove(path)
                if self.running:
                    total_removed += self._remove_pending_for_source(path)

            self.update_selection_display()
            if self.running and total_removed:
                self.log(f"🗑 Removed {total_removed} pending image(s) from the active queue.")

        except tk.TclError:
            messagebox.showinfo("Remove", "Select a file or folder name from the list first.")

    def skip_selected_file(self):
        if not self.running:
            messagebox.showinfo("Skip", "Start processing before skipping queued files.")
            return

        selected_indices = list(self.selection_text.curselection())
        if not selected_indices:
            messagebox.showinfo("Skip", "Select a queued file item first.")
            return

        skipped_count = 0
        for index in selected_indices:
            if index >= len(self.input_paths):
                continue
            selected_path = Path(self.input_paths[index])
            if selected_path.is_dir():
                chosen = filedialog.askopenfilename(
                    title=f"Choose a pending image to skip from {selected_path.name}",
                    initialdir=str(selected_path),
                    filetypes=[
                        ("All Images", "*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff"),
                        ("All files", "*.*"),
                    ],
                )
                if not chosen:
                    continue
                selected_path = Path(chosen)
                try:
                    selected_path.relative_to(Path(self.input_paths[index]))
                except ValueError:
                    messagebox.showwarning("Invalid File", "Choose a file from the selected folder.")
                    continue
            if self.current_image is not None and Path(self.current_image) == selected_path:
                messagebox.showwarning("Cannot Skip Active File", "The current file is already processing and cannot be interrupted safely.")
                continue
            key = str(selected_path.resolve())
            self.skipped_files.add(key)
            skipped_count += 1

        if skipped_count:
            self.log(f"⏭ Marked {skipped_count} file(s) to skip.")

    def _enqueue_path_live(self, path):
        images = self.get_images_from_path(path)
        added = 0
        with self.queue_lock:
            for img in images:
                key = str(Path(img).resolve())
                if key in self.queued_image_keys:
                    continue
                self.pending_images.append((Path(img), path))
                self.queued_image_keys.add(key)
                added += 1
            self.total_images += added
            if hasattr(self, "progress"):
                self.progress["maximum"] = max(self.total_images, 1)
        if self.running and added:
            self.log(f"➕ Added {added} image(s) to the active queue from {Path(path).name}.")
        return added

    def select_single_folder(self):
        """Select a single folder"""
        folder = filedialog.askdirectory(title="Select one folder to upscale")
        if folder:
            if folder not in self.input_paths:
                self.input_paths.append(folder)
                if self.running:
                    self._enqueue_path_live(folder)
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
            
            # Ask if user wants to select more folders
            response = messagebox.askyesno(
                "Continue Selection?",
                f"Added: {Path(folder).name}\n\nDo you want to select more folders?"
            )
            
            if not response:
                break

        if folders:
            added_folders = 0
            for folder in folders:
                if folder not in self.input_paths:
                    self.input_paths.append(folder)
                    added_folders += 1
                    if self.running:
                        self._enqueue_path_live(folder)
            self.update_selection_display()
            messagebox.showinfo("Folders Selected", f"Added {added_folders} folder(s) to process")

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

        if file and file not in self.input_paths:
            self.input_paths.append(file)
            if self.running:
                self._enqueue_path_live(file)
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
                    if self.running:
                        self._enqueue_path_live(file)
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
            # Only get files directly in this folder, not subfolders
            images = [f for f in path.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS]
            return images

        return []

    def get_output_path(self, input_path):
        """Determine output path - creates 'upscaled' folder in same location"""
        input_path = Path(input_path)

        if input_path.is_file():
            # For files, create 'upscaled' folder in the file's directory
            output_dir = input_path.parent / "upscaled"
        else:
            # For folders, create 'upscaled' folder inside the selected folder
            output_dir = input_path / "upscaled"

        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def get_model_path(self, model_info):
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        model_path = MODEL_DIR / model_info["filename"]

        if model_path.exists():
            return str(model_path)

        self.log(f"⬇️ Downloading {model_info['filename']}... (happens only once)")
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
            self.log("⚠️ Face enhancement library not installed. Skipping face enhance.")
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
            self.log(f"⚠️ Could not load face enhancement: {exc}")
            return None

    def compress_for_leonardo(self, image, quality, output_format):
        """Compress image to meet Leonardo AI 5MB limit"""
        
        if output_format == "WEBP (smaller)":
            encode_param = [cv2.IMWRITE_WEBP_QUALITY, quality]
            ext = ".webp"
        elif output_format == "JPG (standard)":
            encode_param = [cv2.IMWRITE_JPEG_QUALITY, quality]
            ext = ".jpg"
        else:  # PNG
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

    def upscale_one_image(self, image_path, output_dir, upsampler, face_enhancer):
        if self.stop_event.is_set() or self.stop_requested:
            return None

        image_path = Path(image_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        img = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)

        if img is None:
            raise RuntimeError(f"Could not read image")

        outscale_value = float(self.outscale.get())

        if face_enhancer is not None:
            _, _, output = face_enhancer.enhance(
                img,
                has_aligned=False,
                only_center_face=True,
                paste_back=True,
            )
        else:
            output, _ = upsampler.enhance(img, outscale=outscale_value)

        # Determine output format
        format_choice = self.output_format.get()
        if format_choice == "WEBP (smaller)":
            ext = ".webp"
        elif format_choice == "JPG (standard)":
            ext = ".jpg"
        else:
            ext = ".png"

        output_filename = image_path.stem + f"_upscaled_x{outscale_value:g}{ext}"
        output_path = output_dir / output_filename

        # Safety feature: Never overwrite existing enhanced images
        if output_path.exists():
            self.log(f"⏭ Skipped (already exists): {output_filename}")
            return "SKIPPED", output_path

        # Leonardo AI optimization
        if self.leonardo_optimize.get():
            quality = self.output_quality.get()
            encoded, file_size = self.compress_for_leonardo(output, quality, format_choice)
            
            with open(output_path, "wb") as f:
                f.write(encoded)
            
            return output_path, file_size

        else:
            success = cv2.imwrite(str(output_path), output)
            if not success:
                raise RuntimeError(f"Could not save image")

            file_size = output_path.stat().st_size
            return output_path, file_size

    def request_stop(self):
        """Request to stop processing"""
        self.stop_requested = True
        self.stop_event.set()
        self.log("⏹️ Stopping after current image...")

    def run_upscale(self):
        try:
            self.running = True
            self.stop_requested = False
            self.stop_event = threading.Event()
            self.start_button.configure(state="disabled")
            self.stop_button.configure(state="normal")
            self.skip_button.configure(state="normal")
            self.progress["value"] = 0

            if not self.input_paths:
                raise ValueError("Please select at least one image or folder.")

            self.input_paths = [p for p in self.input_paths if Path(p).exists()]
            if not self.input_paths:
                raise ValueError("Queue is empty or selected files no longer exist.")

            with self.queue_lock:
                self.pending_images.clear()
                self.queued_image_keys.clear()
                self.skipped_files.clear()
                self.total_images = 0
                self.processed_images = 0
                self.current_image = None
                self.current_source_item = None

            for input_path in list(self.input_paths):
                self._enqueue_path_live(input_path)

            if self.total_images == 0:
                raise ValueError("No images found in selected locations.")

            self.cached_upsampler = None
            self.cached_face_enhancer = None
            self.start_time = time.time()
            self.queue_initialized = True

            self.log("")
            self.log(f"🚀 Starting live queue with {self.total_images} image(s)...")
            self.log(f"Model: {self.model_name.get()}")
            self.log(f"Size: {self.outscale.get():g}x larger")
            self.log("You may add new files/folders or remove pending folders while processing.")
            self.log("")

            self.progress["maximum"] = max(self.total_images, 1)
            self.log("📥 Loading AI model...")
            upsampler = self.create_upsampler()
            face_enhancer = self.create_face_enhancer(upsampler)
            if face_enhancer:
                self.log("✓ Face enhancement ready")

            idle_rounds = 0
            while True:
                if self.stop_event.is_set() or self.stop_requested:
                    self.log("⏹️ Stopped by user after the current image.")
                    break

                with self.queue_lock:
                    item = self.pending_images.popleft() if self.pending_images else None

                if item is None:
                    idle_rounds += 1
                    if idle_rounds >= 5:
                        break
                    time.sleep(0.2)
                    continue

                idle_rounds = 0
                image_path, source_path = item
                key = str(Path(image_path).resolve())

                if key in self.skipped_files:
                    self.processed_images += 1
                    self.log(f"⏭ User skipped: {image_path.name}")
                    self._update_live_progress()
                    continue

                self.current_image = image_path
                self.current_source_item = source_path
                self.processed_images += 1
                self._update_live_progress()

                output_dir = self.get_output_path(source_path)
                self.output_folder = str(output_dir)
                self.log(f"[{self.processed_images}/{self.total_images}] Enhancing: {image_path.name}...")

                try:
                    result = self.upscale_one_image(
                        image_path=image_path,
                        output_dir=output_dir,
                        upsampler=upsampler,
                        face_enhancer=face_enhancer,
                    )

                    if isinstance(result, tuple) and result[0] == "SKIPPED":
                        self.log(f"⏭ Existing file skipped: {result[1].name}")
                    elif result is not None:
                        saved_path, file_size = result
                        file_size_mb = file_size / 1024 / 1024
                        self.log(f"  ✓ Saved ({file_size_mb:.1f}MB)")
                        if self.leonardo_optimize.get() and file_size > LEONARDO_MAX_SIZE_BYTES:
                            self.log(f"  ⚠️ Still {file_size_mb:.1f}MB (over 5MB limit)")

                except Exception as exc:
                    self.log(f"  ❌ Error: {str(exc)}")
                finally:
                    self.current_image = None
                    self.current_source_item = None
                    self.root.update_idletasks()

            elapsed = time.time() - self.start_time
            self.log("")
            self.time_label.config(text="")
            if self.stop_requested:
                messagebox.showinfo("Stopped", f"Processing stopped safely after {self.processed_images} queued item(s).")
            else:
                self.log(f"✅ All done! Handled {self.processed_images} queued image(s) in {str(timedelta(seconds=int(elapsed)))}")
                messagebox.showinfo("Done!", f"✅ Queue complete: {self.processed_images} image(s) handled.\n\nAll files saved to 'upscaled' folders.")

        except Exception as exc:
            self.log("")
            self.log(f"❌ Error: {str(exc)}")
            messagebox.showerror("Error", str(exc))

        finally:
            self.running = False
            self.queue_initialized = False
            self.current_image = None
            self.current_source_item = None
            self.start_button.configure(state="normal")
            self.stop_button.configure(state="disabled")
            self.skip_button.configure(state="disabled")
            self.root.update_idletasks()

    def _update_live_progress(self):
        total = max(self.total_images, 1)
        progress_pct = int((self.processed_images / total) * 100)
        self.progress["maximum"] = total
        self.progress["value"] = min(self.processed_images, total)
        self.progress_label.config(text=f"{progress_pct}%")
        elapsed = time.time() - self.start_time if self.start_time else 0
        remaining = self.estimate_time(self.processed_images, total, elapsed)
        self.time_label.config(text=f"⏱️ ~{remaining} remaining")

    def start_upscale_thread(self):
        if self.running:
            messagebox.showinfo("Already running", "Upscaling is already in progress.")
            return

        thread = threading.Thread(target=self.run_upscale, daemon=True)
        thread.start()



    def open_output_folder(self):
        if not self.output_folder:
            messagebox.showinfo("Output", "No output folder available yet.")
            return

        try:
            if platform.system() == "Windows":
                subprocess.Popen(["explorer", self.output_folder])
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", self.output_folder])
            else:
                subprocess.Popen(["xdg-open", self.output_folder])
        except Exception as exc:
            messagebox.showerror("Open Folder Error", str(exc))


def main():
    root = tk.Tk()
    app = UpscalerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()