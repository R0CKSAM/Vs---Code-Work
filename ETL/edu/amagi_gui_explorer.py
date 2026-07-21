from __future__ import annotations

import json
import re
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Optional

from playwright.sync_api import (
    BrowserContext,
    Error as PlaywrightError,
    Frame,
    Locator,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

PORTAL_URL = "https://indiatvfast.now3.amagi.tv/partner/analytics/concurrency"
PROFILE_FOLDER = Path("amagi_browser_profile").resolve()
DOWNLOAD_FOLDER = Path("downloads").resolve()

SCAN_SELECTOR = """
button,
a[href],
select,
input[type="button"],
input[type="submit"],
input[type="radio"],
input[type="checkbox"],
[role="button"],
[role="link"],
[role="tab"],
[role="radio"],
[role="checkbox"],
[role="combobox"],
[role="menuitem"],
[role="option"],
[aria-label],
[title]
"""


class AmagiExplorer:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Amagi Dashboard Control Explorer")
        self.root.geometry("1280x820")
        self.root.minsize(1000, 650)

        self.playwright_manager = None
        self.playwright: Optional[Playwright] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

        self.controls: list[dict[str, Any]] = []
        self.filtered_controls: list[dict[str, Any]] = []
        self.actions: list[dict[str, Any]] = []
        self.native_options: list[dict[str, str]] = []

        self.search_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Starting browser...")
        self.force_click_var = tk.BooleanVar(value=False)

        self._build_ui()
        self.search_var.trace_add("write", lambda *_: self.apply_filter())

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(150, self.start_browser)

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self.root, padding=8)
        toolbar.pack(fill="x")

        ttk.Button(
            toolbar,
            text="Open Dashboard",
            command=self.open_dashboard,
        ).pack(side="left", padx=(0, 6))

        ttk.Button(
            toolbar,
            text="Refresh Controls",
            command=self.refresh_controls,
        ).pack(side="left", padx=6)

        ttk.Button(
            toolbar,
            text="Click Selected",
            command=self.click_selected,
        ).pack(side="left", padx=6)

        ttk.Button(
            toolbar,
            text="Click + Refresh",
            command=lambda: self.click_selected(refresh_after=True),
        ).pack(side="left", padx=6)

        ttk.Button(
            toolbar,
            text="Click + Save Download",
            command=self.click_selected_as_download,
        ).pack(side="left", padx=6)

        ttk.Button(
            toolbar,
            text="Export Recorded Steps",
            command=self.export_steps,
        ).pack(side="left", padx=6)

        ttk.Checkbutton(
            toolbar,
            text="Force click",
            variable=self.force_click_var,
        ).pack(side="right")

        search_frame = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        search_frame.pack(fill="x")

        ttk.Label(search_frame, text="Filter controls:").pack(side="left")
        ttk.Entry(
            search_frame,
            textvariable=self.search_var,
            width=55,
        ).pack(side="left", padx=(8, 12))

        ttk.Label(
            search_frame,
            textvariable=self.status_var,
        ).pack(side="left", fill="x", expand=True)

        main_pane = ttk.Panedwindow(self.root, orient="horizontal")
        main_pane.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        left_frame = ttk.Frame(main_pane)
        right_frame = ttk.Frame(main_pane)
        main_pane.add(left_frame, weight=3)
        main_pane.add(right_frame, weight=2)

        controls_group = ttk.LabelFrame(
            left_frame,
            text="Visible controls on the current page",
            padding=6,
        )
        controls_group.pack(fill="both", expand=True)

        columns = ("kind", "name", "frame")
        self.tree = ttk.Treeview(
            controls_group,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("kind", text="Type")
        self.tree.heading("name", text="Visible name / label")
        self.tree.heading("frame", text="Frame")
        self.tree.column("kind", width=120, stretch=False)
        self.tree.column("name", width=520, stretch=True)
        self.tree.column("frame", width=180, stretch=False)

        tree_scroll = ttk.Scrollbar(
            controls_group,
            orient="vertical",
            command=self.tree.yview,
        )
        self.tree.configure(yscrollcommand=tree_scroll.set)

        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")

        self.tree.bind("<<TreeviewSelect>>", self.on_control_selected)
        self.tree.bind("<Double-1>", lambda _event: self.click_selected())

        details_group = ttk.LabelFrame(
            right_frame,
            text="Selected control details",
            padding=6,
        )
        details_group.pack(fill="both", expand=True)

        self.details = tk.Text(
            details_group,
            height=16,
            wrap="word",
        )
        self.details.pack(fill="both", expand=True)

        options_group = ttk.LabelFrame(
            right_frame,
            text="Native <select> options",
            padding=6,
        )
        options_group.pack(fill="both", expand=False, pady=(8, 0))

        self.options_list = tk.Listbox(
            options_group,
            height=8,
            exportselection=False,
        )
        self.options_list.pack(
            side="left",
            fill="both",
            expand=True,
        )

        options_scroll = ttk.Scrollbar(
            options_group,
            orient="vertical",
            command=self.options_list.yview,
        )
        self.options_list.configure(yscrollcommand=options_scroll.set)
        options_scroll.pack(side="right", fill="y")

        ttk.Button(
            right_frame,
            text="Select highlighted native option",
            command=self.select_native_option,
        ).pack(fill="x", pady=(6, 0))

        log_group = ttk.LabelFrame(
            self.root,
            text="Recorded test actions",
            padding=6,
        )
        log_group.pack(fill="both", expand=False, padx=8, pady=(0, 8))

        self.log = tk.Text(
            log_group,
            height=9,
            wrap="word",
        )
        self.log.pack(fill="both", expand=True)

        help_text = (
            "Tip: manually log in or navigate in the browser at any time, then click "
            "'Refresh Controls'. For custom dropdowns, choose the dropdown and use "
            "'Click + Refresh'; its visible options should then appear in the list."
        )
        ttk.Label(
            self.root,
            text=help_text,
            padding=(8, 0, 8, 8),
            wraplength=1200,
        ).pack(fill="x")

    def set_status(self, message: str) -> None:
        self.status_var.set(message)
        self.root.update_idletasks()

    def start_browser(self) -> None:
        PROFILE_FOLDER.mkdir(parents=True, exist_ok=True)
        DOWNLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

        try:
            self.playwright_manager = sync_playwright()
            self.playwright = self.playwright_manager.start()

            launch_options = {
                "user_data_dir": str(PROFILE_FOLDER),
                "headless": False,
                "viewport": {"width": 1440, "height": 900},
                "accept_downloads": True,
            }

            try:
                self.context = self.playwright.chromium.launch_persistent_context(
                    channel="msedge",
                    **launch_options,
                )
            except PlaywrightError:
                self.context = self.playwright.chromium.launch_persistent_context(
                    **launch_options,
                )

            self.page = (
                self.context.pages[0]
                if self.context.pages
                else self.context.new_page()
            )
            self.page.set_default_timeout(30_000)

            self.open_dashboard()

        except Exception as error:
            self.set_status("Browser startup failed.")
            messagebox.showerror(
                "Could not start browser",
                (
                    f"{error}\n\n"
                    "Close other automation browser windows that use "
                    "'amagi_browser_profile'. If Chromium is missing, run:\n"
                    "python -m playwright install chromium"
                ),
            )

    def open_dashboard(self) -> None:
        if not self.page:
            return

        self.set_status("Opening the Concurrency dashboard...")

        try:
            self.page.goto(
                PORTAL_URL,
                wait_until="domcontentloaded",
                timeout=60_000,
            )
        except PlaywrightTimeoutError:
            pass
        except Exception as error:
            messagebox.showerror("Navigation failed", str(error))
            return

        self.page.wait_for_timeout(2500)

        if "login.amagi.tv" in self.page.url.lower():
            self.set_status(
                "Log in manually in the browser, then click Refresh Controls."
            )
        else:
            self.set_status("Dashboard opened. Scanning visible controls...")
            self.refresh_controls()

    def refresh_controls(self) -> None:
        if not self.page:
            return

        self.set_status("Scanning visible buttons, links, tabs, and dropdowns...")
        new_controls: list[dict[str, Any]] = []
        scan_stamp = int(time.time() * 1000)

        for frame_index, frame in enumerate(self.page.frames):
            try:
                frame_name = frame.name or "main"
                frame_url = frame.url or ""
                prefix = f"amagi-{scan_stamp}-{frame_index}"

                raw_items = frame.locator(SCAN_SELECTOR).evaluate_all(
                    """
                    (elements, prefix) => {
                        const isVisible = (el) => {
                            const style = window.getComputedStyle(el);
                            const rect = el.getBoundingClientRect();
                            return (
                                style.visibility !== "hidden" &&
                                style.display !== "none" &&
                                rect.width > 0 &&
                                rect.height > 0
                            );
                        };

                        const implicitRole = (el) => {
                            const tag = el.tagName.toLowerCase();
                            const type = (el.getAttribute("type") || "").toLowerCase();

                            if (tag === "button") return "button";
                            if (tag === "a" && el.hasAttribute("href")) return "link";
                            if (tag === "select") return "combobox";
                            if (tag === "input" && ["button", "submit"].includes(type)) {
                                return "button";
                            }
                            if (tag === "input" && type === "radio") return "radio";
                            if (tag === "input" && type === "checkbox") return "checkbox";
                            return "";
                        };

                        return elements
                            .filter(isVisible)
                            .map((el, index) => {
                                const marker = `${prefix}-${index}`;
                                el.setAttribute("data-amagi-explorer-id", marker);

                                const text = (
                                    el.innerText ||
                                    el.value ||
                                    el.textContent ||
                                    ""
                                ).replace(/\\s+/g, " ").trim();

                                const labelText = (
                                    el.labels &&
                                    el.labels.length > 0 &&
                                    el.labels[0].innerText
                                ) ? el.labels[0].innerText.replace(/\\s+/g, " ").trim() : "";

                                const options = el.tagName.toLowerCase() === "select"
                                    ? Array.from(el.options).map((option) => ({
                                        text: (option.textContent || "").trim(),
                                        value: option.value,
                                        selected: option.selected,
                                        disabled: option.disabled
                                    }))
                                    : [];

                                return {
                                    marker,
                                    tag: el.tagName.toLowerCase(),
                                    role: el.getAttribute("role") || implicitRole(el),
                                    text,
                                    labelText,
                                    ariaLabel: el.getAttribute("aria-label") || "",
                                    title: el.getAttribute("title") || "",
                                    id: el.id || "",
                                    className: typeof el.className === "string"
                                        ? el.className
                                        : "",
                                    name: el.getAttribute("name") || "",
                                    type: el.getAttribute("type") || "",
                                    value: el.getAttribute("value") || "",
                                    disabled: Boolean(el.disabled),
                                    options
                                };
                            });
                    }
                    """,
                    prefix,
                )

                for item in raw_items:
                    display_name = self._display_name(item)
                    kind = item.get("role") or item.get("tag") or "control"

                    new_controls.append(
                        {
                            **item,
                            "display_name": display_name,
                            "kind": kind,
                            "frame": frame,
                            "frame_index": frame_index,
                            "frame_name": frame_name,
                            "frame_url": frame_url,
                        }
                    )

            except Exception:
                continue

        self.controls = new_controls
        self.apply_filter()
        self.set_status(
            f"Found {len(self.controls)} visible controls. "
            "Double-click one to test it."
        )

    def _display_name(self, item: dict[str, Any]) -> str:
        parts = [
            item.get("ariaLabel", ""),
            item.get("labelText", ""),
            item.get("text", ""),
            item.get("title", ""),
            item.get("name", ""),
            item.get("value", ""),
        ]

        for part in parts:
            clean = " ".join(str(part).split())
            if clean:
                return clean[:220]

        css_hint = item.get("id") or item.get("className") or item.get("tag")
        return f"[unnamed: {css_hint}]"

    def apply_filter(self) -> None:
        query = self.search_var.get().strip().lower()

        if query:
            self.filtered_controls = [
                item
                for item in self.controls
                if query
                in " ".join(
                    [
                        item.get("display_name", ""),
                        item.get("kind", ""),
                        item.get("tag", ""),
                        item.get("className", ""),
                        item.get("id", ""),
                        item.get("frame_url", ""),
                    ]
                ).lower()
            ]
        else:
            self.filtered_controls = list(self.controls)

        for row in self.tree.get_children():
            self.tree.delete(row)

        for index, item in enumerate(self.filtered_controls):
            frame_label = (
                "main"
                if item["frame_index"] == 0
                else item.get("frame_name") or f"frame {item['frame_index']}"
            )

            self.tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    item.get("kind", ""),
                    item.get("display_name", ""),
                    frame_label,
                ),
            )

    def get_selected_control(self) -> Optional[dict[str, Any]]:
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo(
                "Select a control",
                "Choose a row from the controls list first.",
            )
            return None

        index = int(selection[0])
        if index >= len(self.filtered_controls):
            return None

        return self.filtered_controls[index]

    def on_control_selected(self, _event=None) -> None:
        item = self.get_selected_control()
        if not item:
            return

        details = {
            key: value
            for key, value in item.items()
            if key
            not in {
                "frame",
                "options",
            }
        }

        self.details.delete("1.0", "end")
        self.details.insert(
            "1.0",
            json.dumps(details, indent=2, ensure_ascii=False, default=str),
        )

        self.native_options = item.get("options", [])
        self.options_list.delete(0, "end")

        for option in self.native_options:
            marker = "✓ " if option.get("selected") else "  "
            disabled = " [disabled]" if option.get("disabled") else ""
            self.options_list.insert(
                "end",
                f"{marker}{option.get('text', '')} | value={option.get('value', '')}{disabled}",
            )

    def locator_for(self, item: dict[str, Any]) -> Locator:
        frame: Frame = item["frame"]
        marker = item["marker"]
        return frame.locator(
            f'[data-amagi-explorer-id="{marker}"]'
        )

    def click_selected(self, refresh_after: bool = False) -> None:
        item = self.get_selected_control()
        if not item:
            return

        try:
            locator = self.locator_for(item)
            locator.scroll_into_view_if_needed()
            locator.click(
                timeout=30_000,
                force=self.force_click_var.get(),
            )

            self.record_action(
                action_type="click",
                item=item,
            )
            self.set_status(
                f"Clicked: {item.get('display_name', '')}"
            )

            if refresh_after:
                self.root.after(1200, self.refresh_controls)

        except Exception as error:
            messagebox.showerror(
                "Click failed",
                (
                    f"{error}\n\n"
                    "The page may have re-rendered. Click Refresh Controls "
                    "and try again."
                ),
            )

    def click_selected_as_download(self) -> None:
        item = self.get_selected_control()
        if not item or not self.page:
            return

        try:
            locator = self.locator_for(item)
            locator.scroll_into_view_if_needed()

            with self.page.expect_download(timeout=90_000) as download_info:
                locator.click(
                    timeout=30_000,
                    force=self.force_click_var.get(),
                )

            download = download_info.value
            suggested_name = Path(download.suggested_filename).name
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            original = Path(suggested_name)
            if original.suffix:
                output_name = (
                    f"{original.stem}_{timestamp}{original.suffix}"
                )
            else:
                output_name = f"amagi_download_{timestamp}.bin"

            output_path = DOWNLOAD_FOLDER / output_name
            download.save_as(str(output_path))

            self.record_action(
                action_type="download",
                item=item,
                extra={"saved_to": str(output_path)},
            )

            self.set_status(f"Downloaded: {output_path}")
            messagebox.showinfo(
                "Download complete",
                f"Saved to:\n{output_path}",
            )

        except PlaywrightTimeoutError:
            messagebox.showerror(
                "No download detected",
                (
                    "The selected control did not start a browser download "
                    "within 90 seconds. It may have opened a format menu. "
                    "Use Click + Refresh, choose the CSV/Excel option, then "
                    "use Click + Save Download on that option."
                ),
            )
        except Exception as error:
            messagebox.showerror("Download failed", str(error))

    def select_native_option(self) -> None:
        item = self.get_selected_control()
        if not item:
            return

        selection = self.options_list.curselection()
        if not selection:
            messagebox.showinfo(
                "Select an option",
                "Choose an option from the native options list first.",
            )
            return

        option = self.native_options[selection[0]]

        if option.get("disabled"):
            messagebox.showwarning(
                "Disabled option",
                "That option is disabled on the webpage.",
            )
            return

        try:
            locator = self.locator_for(item)
            locator.select_option(value=option.get("value", ""))

            self.record_action(
                action_type="select_option",
                item=item,
                extra={
                    "option_text": option.get("text", ""),
                    "option_value": option.get("value", ""),
                },
            )

            self.set_status(
                f"Selected option: {option.get('text', '')}"
            )
            self.root.after(1200, self.refresh_controls)

        except Exception as error:
            messagebox.showerror("Selection failed", str(error))

    def suggested_locator_code(self, item: dict[str, Any]) -> str:
        role = item.get("role", "").strip()
        name = item.get("ariaLabel") or item.get("labelText") or item.get("text")
        name = " ".join(str(name or "").split())

        if role and name:
            return (
                f'page.get_by_role({role!r}, name={name!r}, exact=True)'
            )

        if name:
            return f"page.get_by_text({name!r}, exact=True)"

        element_id = item.get("id", "").strip()
        if element_id:
            escaped_id = re.sub(r'([#.;:[\],>+~*="\'\\])', r"\\\1", element_id)
            return f"page.locator('#{escaped_id}')"

        class_name = item.get("className", "").strip()
        if class_name:
            first_class = class_name.split()[0]
            escaped_class = re.sub(
                r'([#.;:[\],>+~*="\'\\])',
                r"\\\1",
                first_class,
            )
            return f"page.locator('.{escaped_class}')"

        return f"page.locator({item.get('tag', '*')!r})"

    def record_action(
        self,
        action_type: str,
        item: dict[str, Any],
        extra: Optional[dict[str, Any]] = None,
    ) -> None:
        action = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "type": action_type,
            "name": item.get("display_name", ""),
            "kind": item.get("kind", ""),
            "frame_url": item.get("frame_url", ""),
            "locator_code": self.suggested_locator_code(item),
        }

        if extra:
            action.update(extra)

        self.actions.append(action)
        self.log.insert(
            "end",
            json.dumps(action, ensure_ascii=False) + "\n",
        )
        self.log.see("end")

    def export_steps(self) -> None:
        if not self.actions:
            messagebox.showinfo(
                "No actions recorded",
                "Test some controls first.",
            )
            return

        default_path = Path("recorded_amagi_steps.py").resolve()
        chosen = filedialog.asksaveasfilename(
            title="Save recorded Python steps",
            initialfile=default_path.name,
            defaultextension=".py",
            filetypes=[("Python file", "*.py"), ("All files", "*.*")],
        )

        if not chosen:
            return

        lines = [
            "from pathlib import Path",
            "from playwright.sync_api import sync_playwright",
            "",
            f"PORTAL_URL = {PORTAL_URL!r}",
            "PROFILE_FOLDER = Path('amagi_browser_profile').resolve()",
            "DOWNLOAD_FOLDER = Path('downloads').resolve()",
            "",
            "with sync_playwright() as p:",
            "    context = p.chromium.launch_persistent_context(",
            "        user_data_dir=str(PROFILE_FOLDER),",
            "        channel='msedge',",
            "        headless=False,",
            "        accept_downloads=True,",
            "    )",
            "    page = context.pages[0] if context.pages else context.new_page()",
            "    page.goto(PORTAL_URL, wait_until='domcontentloaded')",
            "    page.wait_for_timeout(3000)",
            "",
        ]

        for index, action in enumerate(self.actions, start=1):
            locator_code = action["locator_code"]
            lines.append(
                f"    # Step {index}: {action['type']} - {action['name']}"
            )

            if action["type"] == "click":
                lines.append(f"    {locator_code}.click()")
                lines.append("    page.wait_for_timeout(1500)")

            elif action["type"] == "select_option":
                value = action.get("option_value", "")
                lines.append(
                    f"    {locator_code}.select_option(value={value!r})"
                )
                lines.append("    page.wait_for_timeout(1500)")

            elif action["type"] == "download":
                lines.extend(
                    [
                        "    with page.expect_download(timeout=90000) as download_info:",
                        f"        {locator_code}.click()",
                        "    download = download_info.value",
                        "    DOWNLOAD_FOLDER.mkdir(parents=True, exist_ok=True)",
                        (
                            "    download.save_as(str("
                            "DOWNLOAD_FOLDER / download.suggested_filename))"
                        ),
                    ]
                )

            lines.append("")

        lines.extend(
            [
                "    input('Press Enter to close the browser... ')",
                "    context.close()",
                "",
            ]
        )

        Path(chosen).write_text(
            "\n".join(lines),
            encoding="utf-8",
        )

        messagebox.showinfo(
            "Export complete",
            (
                f"Recorded steps saved to:\n{chosen}\n\n"
                "These are suggested semantic locators. We can refine any "
                "duplicate or unstable locator after your testing."
            ),
        )

    def close(self) -> None:
        try:
            if self.context:
                self.context.close()
        except Exception:
            pass

        try:
            if self.playwright_manager:
                self.playwright_manager.stop()
        except Exception:
            pass

        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    AmagiExplorer(root)
    root.mainloop()


if __name__ == "__main__":
    main()
