"""
Leonardo.ai Full Automation
---------------------------
Automatically pastes prompts and generates images on Leonardo.ai

SETUP:
1. Install dependencies: pip install playwright pyperclip pandas openpyxl
2. Run: python leonardo_automator.py
3. Click "Open Leonardo" to launch browser
4. Log in to Leonardo.ai manually
5. Click "Auto Mode" to start generating

How to find selectors (do this once):
- Open Leonardo.ai in Chrome/Firefox
- Right-click on the prompt input box -> Inspect
- Copy the selector (id, class, or placeholder text)
- Update PROMPT_INPUT_SELECTOR below
- Do the same for the Generate button
"""

import json
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox
from typing import Optional

import pandas as pd
from playwright.sync_api import sync_playwright, Page, BrowserContext

try:
    import pyperclip
except ImportError:
    print("Missing pyperclip. Run: pip install pyperclip")
    sys.exit(1)

# ==================== CONFIGURATION ====================

# LEONARDO.AI SPECIFIC SELECTORS - YOU MUST UPDATE THESE!
# How to find them: Right-click on element -> Inspect -> Copy -> Copy selector
PROMPT_INPUT_SELECTOR = "textarea[placeholder*='Describe'], div[role='textbox']"  # ← UPDATE THIS
GENERATE_BUTTON_SELECTOR = "button:has-text('Generate'), button:has-text('Create')"  # ← UPDATE THIS

# Wait times (in seconds) - adjust based on your internet speed
WAIT_AFTER_PASTE = 0.5
WAIT_AFTER_GENERATE = 3.0
WAIT_BETWEEN_PROMPTS = 5.0

# File paths
EXCEL_FILE = "Prompts.xlsx"
PROMPT_COLUMN = "ChatGPT Image Prompt (Semi-Realistic + Negative Prompt)"
FRAME_NO_COLUMN = "S.No."
PROGRESS_FILE = "leonardo_progress.json"
PROFILE_FOLDER = Path("leonardo_browser_profile").resolve()

LEONARDO_URL = "https://app.leonardo.ai/"

# ====================================================


class LeonardoAutomator:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Leonardo.ai Prompt Automator")
        self.root.geometry("750x650")
        self.root.minsize(600, 500)

        # Load prompts
        self.rows = self.load_prompts()
        self.progress_path = Path(__file__).parent / PROGRESS_FILE
        self.done = self.load_progress()
        self.index = self.first_unfinished_index()

        # Browser automation
        self.playwright = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.browser_running = False
        self.auto_mode = False
        self.generating = False  # Track if currently generating

        # Build UI
        self.build_ui()
        self.show_current()

    def load_prompts(self) -> list[dict]:
        excel_path = Path(__file__).parent / EXCEL_FILE
        if not excel_path.exists():
            messagebox.showerror("Error", f"Could not find '{EXCEL_FILE}'")
            sys.exit(1)

        df = pd.read_excel(excel_path)
        
        if PROMPT_COLUMN in df.columns:
            prompt_series = df[PROMPT_COLUMN]
        else:
            prompt_series = df.iloc[:, 0]

        has_frame_no = FRAME_NO_COLUMN in df.columns
        rows = []

        for idx, prompt in enumerate(prompt_series.tolist()):
            prompt_str = str(prompt).strip()
            if not prompt_str or prompt_str.lower() == "nan":
                continue

            frame_no = df[FRAME_NO_COLUMN].iloc[idx] if has_frame_no else idx + 1
            try:
                frame_no = int(frame_no)
            except (TypeError, ValueError):
                frame_no = idx + 1

            rows.append({"frame_no": frame_no, "prompt": prompt_str})

        if not rows:
            messagebox.showerror("Error", "No prompts found in Excel file")
            sys.exit(1)

        return rows

    def load_progress(self) -> set[int]:
        if self.progress_path.exists():
            try:
                return set(json.loads(self.progress_path.read_text(encoding="utf-8")))
            except Exception:
                return set()
        return set()

    def save_progress(self) -> None:
        self.progress_path.write_text(
            json.dumps(sorted(self.done)), 
            encoding="utf-8"
        )

    def first_unfinished_index(self) -> int:
        for i, row in enumerate(self.rows):
            if row["frame_no"] not in self.done:
                return i
        return 0

    def build_ui(self):
        # Style
        style = ttk.Style()
        style.configure("Success.TButton", foreground="green")
        style.configure("Danger.TButton", foreground="red")

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.LabelFrame(self.root, text="Status", padding=6)
        status_bar.pack(fill="x", padx=10, pady=5)
        ttk.Label(status_bar, textvariable=self.status_var).pack(side="left")
        
        # Browser status indicator
        self.browser_status = ttk.Label(status_bar, text="● Browser: Closed", foreground="red")
        self.browser_status.pack(side="right")

        # Prompt display
        prompt_frame = ttk.LabelFrame(self.root, text="Current Prompt", padding=10)
        prompt_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.frame_label = ttk.Label(
            prompt_frame, 
            text="Frame 000 (0/0)",
            font=("Segoe UI", 12, "bold")
        )
        self.frame_label.pack(pady=(0, 5))

        self.prompt_text = tk.Text(
            prompt_frame,
            wrap="word",
            font=("Segoe UI", 10),
            height=12,
            padx=10,
            pady=10,
            relief="flat"
        )
        self.prompt_text.pack(fill="both", expand=True)

        # Controls
        control_frame = ttk.Frame(self.root)
        control_frame.pack(pady=10)

        ttk.Button(
            control_frame,
            text="← Previous",
            command=self.go_previous
        ).pack(side="left", padx=5)

        ttk.Button(
            control_frame,
            text="📋 Copy to Clipboard",
            command=self.copy_to_clipboard
        ).pack(side="left", padx=5)

        ttk.Button(
            control_frame,
            text="✅ Done → Next",
            command=self.go_next
        ).pack(side="left", padx=5)

        # Browser controls
        browser_frame = ttk.LabelFrame(self.root, text="Browser Automation", padding=10)
        browser_frame.pack(fill="x", padx=10, pady=5)

        ttk.Button(
            browser_frame,
            text="🌐 Open Leonardo.ai",
            command=self.open_browser,
            width=20
        ).pack(side="left", padx=5)

        ttk.Button(
            browser_frame,
            text="🚀 Send Current Prompt",
            command=self.send_prompt,
            width=20
        ).pack(side="left", padx=5)

        self.auto_mode_btn = ttk.Button(
            browser_frame,
            text="▶ Auto Mode (Continuous)",
            command=self.toggle_auto_mode,
            width=25
        )
        self.auto_mode_btn.pack(side="left", padx=5)

        ttk.Button(
            browser_frame,
            text="⏹ Stop Auto Mode",
            command=self.stop_auto_mode,
            width=20
        ).pack(side="left", padx=5)

        # Progress
        progress_frame = ttk.LabelFrame(self.root, text="Progress", padding=6)
        progress_frame.pack(fill="x", padx=10, pady=5)

        self.progress_bar = ttk.Progressbar(
            progress_frame,
            length=400,
            mode="determinate"
        )
        self.progress_bar.pack(fill="x")

        self.progress_label = ttk.Label(
            progress_frame,
            text="0 / 0 prompts done"
        )
        self.progress_label.pack()

        # Log
        log_frame = ttk.LabelFrame(self.root, text="Log", padding=6)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.log_text = tk.Text(log_frame, height=5, wrap="word")
        self.log_text.pack(fill="both", expand=True)

        # Help text
        help_text = (
            "⚠️ IMPORTANT: You must update PROMPT_INPUT_SELECTOR and GENERATE_BUTTON_SELECTOR "
            "in the code with the correct selectors for Leonardo.ai. Right-click on the "
            "prompt input box and generate button, select 'Inspect', then copy the selector."
        )
        ttk.Label(
            self.root,
            text=help_text,
            padding=(8, 0, 8, 8),
            wraplength=700,
            foreground="orange"
        ).pack(fill="x")

        # Update progress display
        self.update_progress()

    def update_progress(self):
        total = len(self.rows)
        done = len(self.done)
        self.progress_bar["maximum"] = total
        self.progress_bar["value"] = done
        self.progress_label.config(text=f"{done} / {total} prompts done")

    def log(self, message: str, is_error: bool = False):
        timestamp = time.strftime("%H:%M:%S")
        prefix = "❌" if is_error else "▶"
        self.log_text.insert("end", f"[{timestamp}] {prefix} {message}\n")
        self.log_text.see("end")
        self.status_var.set(message)

    def show_current(self):
        if not self.rows:
            return

        row = self.rows[self.index]
        total = len(self.rows)
        done = len(self.done)

        self.frame_label.config(
            text=f"Frame {row['frame_no']:03d}  ({self.index + 1} of {total})"
        )

        self.prompt_text.delete("1.0", tk.END)
        self.prompt_text.insert("1.0", row["prompt"])

        # Auto-copy to clipboard
        pyperclip.copy(row["prompt"])
        self.update_progress()

    def copy_to_clipboard(self):
        if not self.rows:
            return
        row = self.rows[self.index]
        pyperclip.copy(row["prompt"])
        self.log(f"📋 Copied to clipboard: {row['prompt'][:60]}...")

    def go_next(self):
        row = self.rows[self.index]
        self.done.add(row["frame_no"])
        self.save_progress()

        if self.index < len(self.rows) - 1:
            self.index += 1
        self.show_current()
        self.log(f"✅ Marked Frame {row['frame_no']} as done")

    def go_previous(self):
        if self.index > 0:
            self.index -= 1
            self.show_current()

    def open_browser(self):
        """Open browser to Leonardo.ai"""
        if self.browser_running:
            self.log("Browser already running")
            return

        try:
            self.log("Starting browser...")
            PROFILE_FOLDER.mkdir(parents=True, exist_ok=True)

            self.playwright = sync_playwright().start()
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_FOLDER),
                headless=False,
                viewport={"width": 1400, "height": 900},
                accept_downloads=True,
            )

            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
            self.page.goto(LEONARDO_URL, wait_until="domcontentloaded", timeout=60000)
            
            self.browser_running = True
            self.browser_status.config(text="● Browser: Open", foreground="green")
            self.log("🌐 Browser opened. Log in to Leonardo.ai manually.")
            
            # Wait for user to log in
            time.sleep(3)
            
            # Try to detect if login is needed
            if "login" in self.page.url.lower() or "auth" in self.page.url.lower():
                self.log("⚠️ Please log in to Leonardo.ai manually")

        except Exception as e:
            self.log(f"Browser error: {e}", is_error=True)
            messagebox.showerror("Browser Error", str(e))

    def find_element(self, selector: str, timeout: int = 10000):
        """Helper to find element with error handling"""
        try:
            element = self.page.locator(selector)
            if element.count() > 0:
                return element.first
            return None
        except Exception:
            return None

    def send_prompt(self):
        """Send the current prompt to Leonardo.ai"""
        if not self.browser_running or not self.page:
            self.log("Browser not running. Please open browser first.", is_error=True)
            return

        if not self.rows:
            return

        if self.generating:
            self.log("⏳ Already generating, please wait...")
            return

        try:
            self.generating = True
            
            # Get current prompt
            row = self.rows[self.index]
            prompt = row["prompt"]
            
            self.log(f"🚀 Sending prompt {row['frame_no']}: {prompt[:60]}...")

            # Check if we're on the right page
            if "leonardo" not in self.page.url.lower():
                self.log("Not on Leonardo.ai page. Please navigate to app.leonardo.ai", is_error=True)
                self.generating = False
                return

            # Wait a moment for page to be ready
            time.sleep(1)

            # Find and click on prompt input
            input_element = self.find_element(PROMPT_INPUT_SELECTOR)
            if not input_element:
                self.log(f"❌ Could not find prompt input. Selector: {PROMPT_INPUT_SELECTOR}", is_error=True)
                self.log("Please update PROMPT_INPUT_SELECTOR in the code", is_error=True)
                self.generating = False
                return

            # Click to focus
            input_element.click(timeout=5000)
            time.sleep(0.5)

            # Clear any existing text
            input_element.fill("")
            time.sleep(0.3)

            # Type/paste the prompt
            input_element.fill(prompt)
            time.sleep(WAIT_AFTER_PASTE)

            # Find and click generate button
            generate_button = self.find_element(GENERATE_BUTTON_SELECTOR)
            if not generate_button:
                self.log(f"❌ Could not find generate button. Selector: {GENERATE_BUTTON_SELECTOR}", is_error=True)
                self.log("Please update GENERATE_BUTTON_SELECTOR in the code", is_error=True)
                self.generating = False
                return

            # Click generate
            generate_button.click(timeout=5000)
            self.log(f"✅ Generated image for Frame {row['frame_no']}")
            
            # Wait for generation to complete (or wait a bit)
            time.sleep(WAIT_AFTER_GENERATE)

            # Mark as done and move to next
            self.go_next()

        except Exception as e:
            self.log(f"Error sending prompt: {e}", is_error=True)
        finally:
            self.generating = False

    def toggle_auto_mode(self):
        """Toggle automatic mode"""
        if not self.browser_running:
            self.log("Please open browser first", is_error=True)
            return

        self.auto_mode = not self.auto_mode
        if self.auto_mode:
            self.auto_mode_btn.config(text="⏸ Auto Mode (Running)", style="Success.TButton")
            self.log("▶ Auto mode started")
            self.root.after(1000, self.auto_send_loop)
        else:
            self.auto_mode_btn.config(text="▶ Auto Mode (Continuous)", style="TButton")
            self.log("⏸ Auto mode paused")

    def auto_send_loop(self):
        """Auto send loop"""
        if not self.auto_mode or not self.browser_running:
            return

        # Check if we're done
        if self.index >= len(self.rows) - 1 and len(self.done) == len(self.rows):
            self.auto_mode = False
            self.auto_mode_btn.config(text="▶ Auto Mode (Continuous)", style="TButton")
            self.log("🎉 All prompts completed!")
            return

        # Send current prompt
        self.send_prompt()
        
        # Continue if more prompts
        if self.auto_mode and self.index < len(self.rows):
            self.root.after(int(WAIT_BETWEEN_PROMPTS * 1000), self.auto_send_loop)
        else:
            self.auto_mode = False
            self.auto_mode_btn.config(text="▶ Auto Mode (Continuous)", style="TButton")

    def stop_auto_mode(self):
        """Stop automatic mode"""
        self.auto_mode = False
        self.auto_mode_btn.config(text="▶ Auto Mode (Continuous)", style="TButton")
        self.log("⏹ Auto mode stopped")

    def close(self):
        """Clean up resources"""
        self.auto_mode = False
        try:
            if self.context:
                self.context.close()
        except:
            pass
        
        try:
            if self.playwright:
                self.playwright.stop()
        except:
            pass

        self.root.destroy()


# ==================== FINDING SELECTORS HELPER ====================

def find_selectors_help():
    """Helper function to guide users in finding selectors"""
    print("""
    ========== HOW TO FIND LEONARDO.AI SELECTORS ==========
    
    1. Open Leonardo.ai in your browser (Chrome or Firefox)
    2. Right-click on the text input box where you type prompts
    3. Select "Inspect" (Chrome) or "Inspect Element" (Firefox)
    4. In the developer tools, right-click on the highlighted HTML
    5. Select "Copy" -> "Copy selector" (Chrome) or "Copy" -> "CSS Selector" (Firefox)
    6. Paste this value into PROMPT_INPUT_SELECTOR in the code
    
    7. Do the same for the "Generate" or "Create" button
    8. Paste that value into GENERATE_BUTTON_SELECTOR
    
    Example selectors (these may not work):
    PROMPT_INPUT_SELECTOR = "textarea[placeholder='Describe your image...']"
    GENERATE_BUTTON_SELECTOR = "button[data-testid='generate-button']"
    
    If the first selector doesn't work, try:
    - Using a more specific selector (like an ID or data attribute)
    - Using a class name: ".prompt-input"
    - Using a partial attribute match: "input[name*='prompt']"
    ========================================================
    """)


def main():
    root = tk.Tk()
    
    # Show help on startup
    print("\n" + "="*60)
    print("LEONARDO.AI AUTOMATOR - SETUP REQUIRED")
    print("="*60)
    print("\nBefore using, you MUST update the selectors in the code.")
    print("Find selectors by right-clicking on elements and selecting 'Inspect'.\n")
    
    app = LeonardoAutomator(root)
    root.protocol("WM_DELETE_WINDOW", app.close)
    
    # Show selector help
    root.after(1000, find_selectors_help)
    
    root.mainloop()


if __name__ == "__main__":
    main()