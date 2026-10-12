import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image

# The packaged app includes its model under _internal/models/u2net.
if getattr(sys, "frozen", False):
    os.environ["REMBG_HOME"] = sys._MEIPASS

from rembg import new_session, remove

# Allows checking the packaged EXE without opening the desktop window.
if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
    result = remove(Image.new("RGB", (32, 32), "white"), session=new_session("u2net"))
    with open(sys.argv[2], "w", encoding="utf-8") as report:
        report.write(f"{result.mode} {result.size}\n")
    sys.exit(0)

session = None


def remove_background():
    global session

    # Select image
    file_path = filedialog.askopenfilename(
        title="Select Image",
        filetypes=[
            ("Images", "*.jpg *.jpeg *.png *.webp")
        ]
    )

    if not file_path:
        return

    button.config(state="disabled")
    status.config(text="Processing image...")
    root.update_idletasks()

    try:
        # Open image
        img = Image.open(file_path).convert("RGBA")

        # Keep original size
        original_size = img.size

        # Remove background
        if session is None:
            session = new_session("u2net")
        output = remove(img, session=session)

        # Restore original resolution
        output = output.resize(
            original_size,
            Image.LANCZOS
        )

        # Save location
        folder = os.path.dirname(file_path)
        filename = os.path.splitext(
            os.path.basename(file_path)
        )[0]

        output_path = os.path.join(
            folder,
            filename + "_no_bg.png"
        )

        # Save transparent PNG
        output.save(
            output_path,
            "PNG",
            optimize=True
        )

        status.config(text="Completed")
        messagebox.showinfo(
            "Completed",
            f"Background removed successfully!\n\nSaved:\n{output_path}"
        )

    except Exception as e:
        status.config(text="Could not process image")
        messagebox.showerror(
            "Error",
            str(e)
        )
    finally:
        button.config(state="normal")


# Create app window
root = tk.Tk()
root.title("AI Background Remover")
root.geometry("350x180")
root.resizable(False, False)


button = tk.Button(
    root,
    text="Select Image & Remove Background",
    command=remove_background,
    font=("Arial", 12),
    width=30,
    height=3
)

button.pack(
    pady=(30, 10)
)

status = tk.Label(root, text="Select an image to begin")
status.pack()


root.mainloop()
