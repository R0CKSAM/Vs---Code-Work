"""
Prompt Clipboard Queue - for manually pasting into Midjourney / Leonardo / any web UI
---------------------------------------------------------------------------------------
What this does:
  - Loads all your prompts from Prompts.xlsx
  - Shows one prompt at a time in a small always-on-top window
  - Copies the current prompt to your clipboard automatically
  - You Alt+Tab to Midjourney/Leonardo, hit Ctrl+V, hit Enter - that's
    the one real human action per image, same as typing it yourself,
    just much faster than typing 50 long prompts by hand
  - Tracks which prompts you've done, saved to disk - close the tool
    and reopen later, it remembers exactly where you left off
  - "Next" auto-copies the next prompt so you can just keep clicking
    through: paste -> enter -> click Next -> paste -> enter -> ...

This does NOT click, type, or interact with Midjourney/Leonardo's
website in any way - it only prepares your clipboard. Every actual
generation is a real action you take yourself in their app, same as
manual use - just faster than typing each long prompt from scratch.

SETUP (one-time):
    pip install pandas openpyxl pyperclip

RUN:
    python prompt_clipboard_queue.py
"""

import json
import sys
import tkinter as tk
from pathlib import Path

import pandas as pd

try:
    import pyperclip
except ImportError:
    print("Missing package. Run: pip install pyperclip")
    sys.exit(1)

# ---------------------- CONFIG - edit these if needed ----------------------

EXCEL_FILE = "Prompts.xlsx"
PROMPT_COLUMN = "ChatGPT Image Prompt (Semi-Realistic + Negative Prompt)"
USE_COLUMN_INDEX = 0                 # fallback: column A, if header not found
FRAME_NO_COLUMN = "S.No."            # shown as the label for each prompt

PROGRESS_FILE = "clipboard_queue_progress.json"

# -----------------------------------------------------------------------


def load_prompts(excel_path: Path) -> list[dict]:
    if not excel_path.exists():
        print(f"ERROR: Could not find '{excel_path}'.")
        sys.exit(1)

    df = pd.read_excel(excel_path)

    if PROMPT_COLUMN in df.columns:
        prompt_series = df[PROMPT_COLUMN]
    else:
        prompt_series = df.iloc[:, USE_COLUMN_INDEX]

    has_frame_no = FRAME_NO_COLUMN in df.columns

    rows = []
    for idx, prompt in enumerate(prompt_series.tolist()):
        prompt_str = str(prompt).strip()
        if not prompt_str or prompt_str.lower() == "nan":
            continue

        raw_frame_no = df[FRAME_NO_COLUMN].iloc[idx] if has_frame_no else idx + 1
        try:
            frame_no = int(raw_frame_no)
        except (TypeError, ValueError):
            frame_no = idx + 1

        rows.append({"frame_no": frame_no, "prompt": prompt_str})

    if not rows:
        print("ERROR: No prompts found in the Excel file. Check the file and column.")
        sys.exit(1)

    return rows


def load_progress(progress_path: Path) -> set[int]:
    if progress_path.exists():
        try:
            return set(json.loads(progress_path.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def save_progress(progress_path: Path, done_frame_numbers: set[int]) -> None:
    progress_path.write_text(json.dumps(sorted(done_frame_numbers)), encoding="utf-8")


class QueueApp:
    def __init__(self, root: tk.Tk, rows: list[dict], progress_path: Path):
        self.root = root
        self.rows = rows
        self.progress_path = progress_path
        self.done = load_progress(progress_path)
        self.index = self._first_unfinished_index()

        root.title("Prompt Clipboard Queue")
        root.attributes("-topmost", True)
        root.geometry("560x420")
        root.configure(bg="#1e1e1e")

        self.status_label = tk.Label(
            root, text="", font=("Segoe UI", 10, "bold"),
            bg="#1e1e1e", fg="#7fd97f",
        )
        self.status_label.pack(pady=(12, 0))

        self.frame_label = tk.Label(
            root, text="", font=("Segoe UI", 12, "bold"),
            bg="#1e1e1e", fg="white",
        )
        self.frame_label.pack(pady=(4, 8))

        self.prompt_text = tk.Text(
            root, wrap="word", font=("Segoe UI", 10),
            bg="#2b2b2b", fg="white", height=10, padx=10, pady=10,
            relief="flat",
        )
        self.prompt_text.pack(fill="both", expand=True, padx=12)

        btn_frame = tk.Frame(root, bg="#1e1e1e")
        btn_frame.pack(pady=12)

        self.prev_btn = tk.Button(
            btn_frame, text="< Previous", command=self.go_previous,
            width=12, bg="#3a3a3a", fg="white", relief="flat",
        )
        self.prev_btn.grid(row=0, column=0, padx=5)

        self.copy_btn = tk.Button(
            btn_frame, text="Copy Again", command=self.copy_current,
            width=12, bg="#3a3a3a", fg="white", relief="flat",
        )
        self.copy_btn.grid(row=0, column=1, padx=5)

        self.next_btn = tk.Button(
            btn_frame, text="Done -> Next >", command=self.go_next,
            width=14, bg="#2f6f2f", fg="white", relief="flat",
        )
        self.next_btn.grid(row=0, column=2, padx=5)

        self.progress_label = tk.Label(
            root, text="", font=("Segoe UI", 9),
            bg="#1e1e1e", fg="#aaaaaa",
        )
        self.progress_label.pack(pady=(0, 10))

        self.show_current()

    def _first_unfinished_index(self) -> int:
        for i, row in enumerate(self.rows):
            if row["frame_no"] not in self.done:
                return i
        return 0  # everything done - just show the first one

    def show_current(self):
        if not self.rows:
            return
        row = self.rows[self.index]

        already_done = row["frame_no"] in self.done
        self.status_label.config(
            text="[ALREADY MARKED DONE - showing again]" if already_done else "[NOT YET DONE]"
        )
        self.frame_label.config(text=f"Frame {row['frame_no']:03d}  ({self.index + 1} of {len(self.rows)})")

        self.prompt_text.delete("1.0", tk.END)
        self.prompt_text.insert("1.0", row["prompt"])

        pyperclip.copy(row["prompt"])

        done_count = len(self.done)
        self.progress_label.config(
            text=f"Copied to clipboard - just paste (Ctrl+V) into Midjourney/Leonardo and hit Enter. "
                 f"Progress: {done_count}/{len(self.rows)} done."
        )

    def copy_current(self):
        row = self.rows[self.index]
        pyperclip.copy(row["prompt"])
        self.progress_label.config(text="Re-copied to clipboard.")

    def go_next(self):
        row = self.rows[self.index]
        self.done.add(row["frame_no"])
        save_progress(self.progress_path, self.done)

        if self.index < len(self.rows) - 1:
            self.index += 1
        self.show_current()

    def go_previous(self):
        if self.index > 0:
            self.index -= 1
        self.show_current()


def main():
    base_dir = Path(__file__).parent
    excel_path = base_dir / EXCEL_FILE
    progress_path = base_dir / PROGRESS_FILE

    rows = load_prompts(excel_path)

    root = tk.Tk()
    QueueApp(root, rows, progress_path)
    root.mainloop()


if __name__ == "__main__":
    main()