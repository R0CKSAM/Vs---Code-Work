"""Local-only South Korea photo cutouts and Players Stats review gallery.

Run with rembg[cpu] installed in a separate environment. No server writes.
"""
import argparse
import copy
import hashlib
import html
import json
import os
from pathlib import Path

import scoreboard_app as core
from import_davis_players import atomic_json


ASSETS = {
    '709e01c5-fd17-42ab-86da-65c795d51cde': ('Soonwoo Kwon', 'KWO1297775'),
    '6a1bb4f0-2d94-4aa5-a7bf-577d3311c862': ('Hyeon Chung', 'CHU1266248'),
    '68d88188-7fd6-4c4a-83d6-9bb40fcd3fcf': ('Uisung Park', 'PAR1360915'),
    'd4277f5f-fc25-44f7-bcb3-8aaba8120eb5': ('Jisung Nam', 'JIS1221948'),
    'eb063d7c-0bf8-4bb9-bffa-a884af327aa7': ('Seongchan Hong', 'HON1279814'),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model', choices=['u2net_human_seg', 'isnet-general-use'], default='isnet-general-use')
    parser.add_argument('--assets', type=Path, help='Optional JSON mapping profile IDs to [name, official asset ID]')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    os.environ.setdefault('U2NET_HOME', str(out.parent / 'models'))
    os.environ.setdefault('OMP_NUM_THREADS', '2')
    from rembg import new_session, remove
    from PIL import Image, ImageChops, ImageDraw
    session = new_session(args.model, providers=['CPUExecutionProvider'])
    report = json.loads(args.review.read_text(encoding='utf-8'))
    rows = {row['profile_id']: row for row in report['players']}
    results = []
    assets = json.loads(args.assets.read_text(encoding='utf-8')) if args.assets else ASSETS
    for identifier, (name, asset) in assets.items():
        row = copy.deepcopy(rows[identifier])
        if row['name'] != name:
            raise ValueError('Roster/photo identity mismatch: ' + name)
        source = args.source / (asset + '.png')
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        slug = name.lower().replace(' ', '-')
        with Image.open(source) as photo:
            original = photo.convert('RGB')
            # Use only the model's mask; retain the original RGB pixels exactly.
            mask = remove(original, session=session, only_mask=True).convert('L')
            # White cap on a white wall: restore its traced interior only for this
            # exact source photo, so future headshots cannot inherit this mask.
            cap_refined = source_hash == 'c4aa8f77615688da4661b927ca17a268ff613f67e78699de12edf65690733b05'
            if cap_refined:
                cap = Image.new('L', (original.width * 4, original.height * 4))
                outline = [(307,43),(326,34),(345,27),(360,25),(380,26),
                           (401,31),(418,40),(433,52),(446,66),(457,82),
                           (466,101),(472,119),(475,137),(476,155),
                           (475,174),(472,192),(455,165),(430,140),
                           (400,126),(386,86),(369,61),(331,53),(307,74)]
                ImageDraw.Draw(cap).polygon([(x*4,y*4) for x,y in outline], fill=255)
                mask = ImageChops.lighter(mask, cap.resize(original.size, Image.Resampling.LANCZOS))
            if mask.size != original.size or mask.getextrema() != (0, 255):
                raise ValueError('Invalid/nontransparent segmentation mask: ' + name)
            cutout = original.convert('RGBA')
            cutout.putalpha(mask)
            if ImageChops.difference(original, cutout.convert('RGB')).getbbox():
                raise ValueError('Source RGB pixels changed: ' + name)
            cutout_path = out / (slug + '-cutout.png')
            cutout.save(cutout_path)
        config = row['config']
        config['player_path'] = str(cutout_path)
        row.update(approved=False, image_file=cutout_path.name)
        row['field_sources']['player_path'] = {
            'profile': row['profile_url'],
            'image': 'https://assetbank.itf-production.sports-data.stadion.io/' + asset,
            'source_sha256': source_hash,
            'method': 'Local ' + args.model + ' alpha mask; source RGB unchanged',
            'manual_cap_mask_refinement': cap_refined,
        }
        row['missing_fields'] = [field for field in row['missing_fields'] if field != 'player_path']
        row['preview_file'] = slug + '-1920x1080.png'
        core.render_t6(config).save(out / row['preview_file'])
        results.append(row)
        # Checkpoint completed cards; never mark them approved automatically.
        atomic_json(out / 'review.json', {**report, 'players': results})
        print(name + ': transparent PNG and 1920x1080 card ready', flush=True)
    cards = ''.join(
        '<article><h2>' + html.escape(row['name']) + '</h2><a href="' + row['preview_file'] +
        '"><img src="' + row['preview_file'] + '" width="1920" height="1080"></a>' +
        '<p><a href="' + row['image_file'] + '">Transparent cutout</a> | <a href="' +
        html.escape(row['profile_url'], quote=True) + '">Official photo source</a></p></article>'
        for row in results)
    (out / 'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Players Stats</title><style>'
        'body{margin:24px;font:16px Arial;background:#eef2f4;color:#15242d}'
        'h1{font-size:24px}h2{font-size:18px}main{display:grid;gap:24px;'
        'grid-template-columns:repeat(auto-fit,minmax(min(100%,560px),1fr))}'
        'article{min-width:0}img{width:100%;height:auto;display:block}a{color:#08604a}'
        '</style><h1>Players Stats</h1>'
        '<p>Review only. Stats from your CSV; original official portraits with local background removal. '
        'Nothing published or put on air. Confirm image-use rights before broadcasting.</p>'
        '<main>' + cards + '</main></html>', encoding='utf-8')
    print('Gallery: ' + str(out / 'index.html'), flush=True)


if __name__ == '__main__':
    main()
