"""Import user-supplied logos without modifying the originals."""
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
MAPPINGS = {
    'Aakash Vani.jpg': ['Aakash Vani'],
    'Bollywood Masala.png': ['Bollywood Masala'],
    'Digital Commentary.jpg': ['Digital Commentary'],
    'Epic Bharat.jpg': ['Epic Bharat'],
    'Epic Bhojpuri.jpg': ['Epic Bhojpuri'],
    'Epic Kids.png': ['Epic Kids'],
    'Epic_Music.jpg': ['Epic Music'],
    'Khabargaon.png': ['Khabargaon'],
    'News Nation State Bihar-JH.jpg': ['News Nation State Bihar/JH'],
    'News Nation State MP-CG.jpg': ['News Nation State MP/CG'],
    'News Nation State Punjab-HR.jpg': ['News Nation State Punjab/HR'],
    # User confirmed this intentionally uses the uploaded National State artwork.
    'News Nation State UPUK.png': ['News Nation State UP/UK'],
    'Ssoftoons.jpg': ['Ssoftoons'],
}


def main():
    destination = ROOT / 'static/channel-logos'
    manifest_path = destination / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    for filename, names in MAPPINGS.items():
        source = ROOT / 'Logo' / filename
        with Image.open(source) as original:
            original.load()
            picture = ImageOps.exif_transpose(original).convert('RGBA')
            picture.thumbnail((240, 160))
            target = ''.join(char for char in names[0].lower() if char.isalnum()) + '.png'
            picture.save(destination / target)
        item = {'file': target, 'background': '#ffffff', 'source': 'Logo/' + filename,
                'user_supplied': True,
                'sha256': hashlib.sha256((destination / target).read_bytes()).hexdigest()}
        for name in names:
            manifest[name.casefold()] = item
        print(filename, '->', target)
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
