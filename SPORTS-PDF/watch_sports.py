"""Watch all InduPaper editions and extract Sports from completed PDFs."""
import argparse
import ctypes
from datetime import datetime
import json
import msvcrt
import os
from pathlib import Path
import time
import traceback
from extract_sports import extract

BASE = Path(__file__).resolve().parent
STATE = BASE / 'watch_state.json'
STATUS = BASE / 'watch_status.json'
STOP = BASE / 'STOP_WATCHER.txt'


def save(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2), encoding='utf-8')
    os.replace(temp, path)


def signature(path):
    stat = path.stat()
    return f'{stat.st_size}:{stat.st_mtime_ns}'


def candidates(root):
    return sorted((p for p in root.rglob('*.pdf')
                   if not {'SPORTS_ONLY', 'MERGED', 'AI_OCR'}.intersection(part.upper() for part in p.parts)
                   and not p.stem.upper().startswith('MERGED_') and not p.stem.endswith('_SPORTS')),
                  key=lambda p: (p.name, str(p)))


def complete(path):
    if path.stat().st_size < 1024 or path.with_suffix(path.suffix + '.crdownload').exists():
        return False
    with path.open('rb') as handle:
        if not handle.read(8).startswith(b'%PDF-'):
            return False
        handle.seek(max(0, path.stat().st_size - 2048))
        return b'%%EOF' in handle.read()


def prior_output(path):
    for report in (path.parent / 'SPORTS_ONLY').glob(path.stem + '_SPORTS*.json'):
        try:
            data = json.loads(report.read_text(encoding='utf-8'))
            output = Path(data['output'])
            if (Path(data['source']).resolve() == path.resolve() and output.is_file()
                    and output.stat().st_mtime_ns >= path.stat().st_mtime_ns):
                return str(output)
        except (OSError, ValueError, KeyError):
            pass
    return None


def watch(root, poll=10, settle=20):
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f'Folder unavailable: {root}')
    # Windows file locking prevents two watchers from processing the same files.
    lock = (BASE / 'watcher.lock').open('a+b')
    lock.seek(0)
    if lock.read(1) == b'':
        lock.write(b'0')
        lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        raise RuntimeError('A Sports watcher is already running.')
    ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)
    STOP.unlink(missing_ok=True)
    try:
        state = json.loads(STATE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        state = {}
    observed = {}
    engine = None
    print(f'WATCHING: {root}\nOutputs: SPORTS_ONLY beside each source.\nCreate {STOP} to stop after the current file.', flush=True)

    def status(phase, current='', error=''):
        counts = {key: sum(v.get('result') == key for v in state.values())
                  for key in ['saved', 'needs_review']}
        counts['failed'] = sum(v.get('result') == 'error' for v in state.values())
        save(STATUS, {'phase': phase, 'current_file': current, 'updated': datetime.now().astimezone().isoformat(),
                      'watch_folder': str(root), **counts, 'error': error, 'pid': os.getpid()})

    try:
        while not STOP.exists():
            files = candidates(root)
            for path in files:
                if STOP.exists():
                    break
                key = str(path)
                try:
                    sig = signature(path)
                    old = state.get(key, {})
                    if old.get('signature') == sig and (old.get('result') != 'saved' or Path(old.get('output') or '').is_file()):
                        continue
                    prior = prior_output(path)
                    if prior:
                        state[key] = {'signature': sig, 'result': 'saved', 'output': prior}
                        save(STATE, state)
                        continue
                    seen = observed.get(key)
                    if not seen or seen[0] != sig:
                        observed[key] = (sig, time.monotonic())
                        continue
                    if time.monotonic() - seen[1] < settle or not complete(path):
                        continue
                    if engine is None:
                        from rapidocr_onnxruntime import RapidOCR
                        engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)
                    print(f'\nSTART: {path}', flush=True)
                    status('processing', key)
                    output = extract(path, engine)
                    # A source changed during processing: scan its new version next time.
                    if signature(path) != sig:
                        print('Source changed; will recheck its new version.', flush=True)
                        continue
                    state[key] = {'signature': sig, 'result': 'saved' if output else 'needs_review',
                                  'output': str(output) if output else None}
                    save(STATE, state)
                    status('watching')
                except Exception as error:
                    print(f'ERROR: {path}: {error}\n{traceback.format_exc()}', flush=True)
                    try:
                        failed_signature = signature(path)
                    except OSError:
                        failed_signature = ''
                    state[key] = {'signature': failed_signature, 'result': 'error', 'error': str(error)}
                    save(STATE, state)
                    status('watching', error=str(error))
            status('watching')
            time.sleep(poll)
    except KeyboardInterrupt:
        print('Stop requested.', flush=True)
    finally:
        status('stopped')
        lock.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', nargs='?', default=r'C:\Users\Intern\Downloads\Storyboard Studio\InduPaper')
    parser.add_argument('--auto-start', action='store_true', help='Sign-in startup mode; respects STOP_WATCHER.txt.')
    args = parser.parse_args()
    if args.auto_start and STOP.exists():
        raise SystemExit(0)
    # A persistent log remains readable without opening the process window.
    import sys
    class Tee:
        def __init__(self, stream, log):
            self.stream, self.log = stream, log
        def write(self, text):
            if self.stream:
                self.stream.write(text)
            self.log.write(text)
            self.log.flush()
        def flush(self):
            if self.stream:
                self.stream.flush()
            self.log.flush()
    with (BASE / 'watcher.log').open('a', encoding='utf-8', buffering=1) as log:
        sys.stdout = Tee(sys.stdout, log)
        sys.stderr = Tee(sys.stderr, log)
        watch(args.folder)
