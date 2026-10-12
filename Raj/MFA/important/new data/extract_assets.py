"""
Extract assets and crops from the reference Davis Cup graphic
into the local assets/ directory for high-fidelity use in davis_cup_generator.py.
"""
import os
from PIL import Image

SRC_PATHS = [
    r"C:\Users\Intern\.gemini\antigravity\brain\147731cc-6015-4d01-ba8e-88f517a3586b\.user_uploaded\media_1789105854522.jpg",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "davis_cup_reference.jpg"),
    r"C:\Users\Intern\.gemini\antigravity\brain\7c96226f-c7ef-42d3-9462-b6632e2fc9a6\.user_uploaded\media_1789044053864.jpg",
]

DEST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def extract():
    os.makedirs(DEST_DIR, exist_ok=True)
    src_path = None
    for p in SRC_PATHS:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            src_path = p
            break

    if not src_path:
        print("No source reference image found.")
        return

    ref_dest = os.path.join(DEST_DIR, "davis_cup_reference.jpg")
    img = Image.open(src_path)
    if src_path != ref_dest:
        img.save(ref_dest)
        print(f"Saved reference image: {ref_dest} ({img.size})")

    W, H = img.size

    # 1. Left Player Crop (Sumit Nagal)
    box_p1 = (0, int(H * 0.14), int(W * 0.34), int(H * 0.88))
    p1_crop = img.crop(box_p1)
    p1_crop.save(os.path.join(DEST_DIR, "player_left_crop.png"))
    print("Saved player_left_crop.png")

    # 2. Right Player Crop (Soonwoo Kwon)
    box_p2 = (int(W * 0.68), int(H * 0.14), W, int(H * 0.88))
    p2_crop = img.crop(box_p2)
    p2_crop.save(os.path.join(DEST_DIR, "player_right_crop.png"))
    print("Saved player_right_crop.png")

    # 3. Davis Cup Complete Logo Crop (Emblem + Full "DAVIS CUP®" text)
    box_logo = (int(W * 0.28), int(H * 0.04), int(W * 0.72), int(H * 0.35))
    logo_crop = img.crop(box_logo)
    logo_crop.save(os.path.join(DEST_DIR, "davis_cup_logo_crop.png"))
    print("Saved davis_cup_logo_crop.png")


if __name__ == "__main__":
    extract()
