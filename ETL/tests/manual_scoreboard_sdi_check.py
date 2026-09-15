"""Explicit, interrupting hardware check; never collected by pytest."""
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'extras/apps/leaderBoardGen'))
import scoreboard_app as core


def main():
    if '--confirm-output-1' not in sys.argv:
        raise SystemExit('This sends test colors to SDI output 1. Pass --confirm-output-1.')
    with urllib.request.urlopen('http://127.0.0.1:8080/api/live/status', timeout=3) as response:
        if json.load(response)['active']:
            raise SystemExit('Existing scoreboard SDI is active; test refused.')
    preset = next(iter(core.VIDEO_EXPORT_PRESETS))
    output = None
    try:
        output = core.DeckLinkLiveOutput(preset, 0)
        output.start(core.Image.new('RGB', (1920, 1080), 'black'))
        for color in ('red', 'green', 'blue', 'black'):
            output.update(core.Image.new('RGB', (1920, 1080), color))
            time.sleep(2)
            error = output.poll_error()
            if error:
                raise RuntimeError(error)
            assert output.snapshot_frame().getpixel((0, 0)) == core.Image.new('RGB', (1, 1), color).getpixel((0, 0))
            print(color, 'OK')
        print('Hardware pipeline passed:', preset, '(physical return feed not measured)')
    finally:
        if output is not None:
            output.stop()


if __name__ == '__main__':
    main()
