"""Download explicitly matched channel logos; no runtime third-party requests.

Run with a Python environment containing Pillow. Review downloaded artwork before
shipping: catalogs can retain logos from before a channel was renamed.
"""
import hashlib
import io
import json
from pathlib import Path
from urllib.request import Request, urlopen

from PIL import Image

ROOT = Path(__file__).resolve().parents[1] / 'static' / 'channel-logos'
MATCHES = {
    '9XM.in': ['9XM'], '9XJalwa.in': ['9X Jalwa'],
    '9XJhakaas.in': ['9X Jhakaas'], '9XTashan.in': ['9X Tashan'],
    'NDTV24x7.in': ['NDTV 24x7'], 'NDTVIndia.in': ['NDTV India'],
    'NDTVMarathi.in': ['NDTV Marathi'], 'NDTVProfit.in': ['NDTV Profit'],
    'NDTVRajasthan.in': ['NDTV Rajasthan'],
    'NDTVMadhyaPradeshChhattisgarh.in': ['NDTV Madhya Prades', 'NDTV Madhya Pradesh'],
    'NewsNation.in': ['News Nation National'], 'EpicTV.in': ['Epic TV'],
}


def fetch(url):
    with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=12) as response:
        data = response.read(8_000_001)
        if len(data) > 8_000_000:
            raise ValueError('Asset exceeds size limit')
        return data


def main():
    catalog = json.loads(fetch('https://iptv-org.github.io/api/logos.json'))
    ROOT.mkdir(parents=True, exist_ok=True)
    manifest_path = ROOT / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
    for channel, names in MATCHES.items():
        if any(manifest.get(name.casefold(), {}).get('user_supplied') for name in names):
            print(channel, 'keeping user-supplied artwork', flush=True)
            continue
        candidates = [entry['url'] for entry in catalog if entry['channel'] == channel]
        candidates.sort(key=lambda url: (0 if 'jiotvimages.cdn.jio.com' in url else 1 if 'streamready.in' in url else 2))
        if channel == '9XTashan.in':
            candidates.sort(key=lambda url: 0 if 'streamready.in' in url else 1)
        for url in candidates:
            try:
                data = fetch(url)
                with Image.open(io.BytesIO(data)) as picture:
                    if picture.width * picture.height > 16_000_000:
                        raise ValueError('Image dimensions exceed limit')
                    picture.load()
                    image = picture.convert('RGBA')
                    image.thumbnail((240, 160))
                    filename = channel.removesuffix('.in').lower() + '.png'
                    image.save(ROOT / filename)
                for name in names:
                    if manifest.get(name.casefold(), {}).get('user_supplied'):
                        continue
                    manifest[name.casefold()] = {'file': filename, 'channel_id': channel,
                        'background': '#18364d' if channel == '9XTashan.in' else '#ffffff',
                        'source': url, 'sha256': hashlib.sha256((ROOT / filename).read_bytes()).hexdigest()}
                print(channel, 'downloaded', flush=True)
                break
            except Exception as error:
                print(channel, type(error).__name__, flush=True)
        else:
            print(channel, 'NO LOGO: initials fallback', flush=True)
    (ROOT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
