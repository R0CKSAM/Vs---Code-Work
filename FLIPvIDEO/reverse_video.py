"""Reverse decoded video and audio losslessly, in bounded-memory chunks."""
import argparse
import math
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import tempfile
import threading

ROOT = Path(__file__).resolve().parent
FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def ffmpeg():
    local = ROOT / 'tools' / 'ffmpeg.exe'
    if local.exists():
        return str(local)
    binary = shutil.which('ffmpeg')
    if binary:
        return binary
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise RuntimeError('FFmpeg missing. Install: python -m pip install imageio-ffmpeg')


def run(args):
    result = subprocess.run([ffmpeg(), '-hide_banner', '-nostdin', *args],
                            capture_output=True, text=True, errors='replace', creationflags=FLAGS)
    if result.returncode:
        raise RuntimeError(result.stderr[-5000:])
    return result


def reverse(source, output_folder=None, log=print, mode='mp4-lossless'):
    source = Path(source).resolve()
    if not source.is_file():
        raise ValueError(f'File not found: {source}')
    probe = subprocess.run([ffmpeg(), '-hide_banner', '-i', str(source)],
                           capture_output=True, text=True, errors='replace', creationflags=FLAGS).stderr
    duration = re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)', probe)
    if not duration or not re.search(r'Stream .*Video:', probe):
        raise ValueError(f'Cannot read video duration: {source.name}')
    h, m, s = map(float, duration.groups())
    seconds = h * 3600 + m * 60 + s
    audio = bool(re.search(r'Stream .*Audio:', probe))
    folder = Path(output_folder or source.parent)
    folder.mkdir(parents=True, exist_ok=True)
    # Reserve a unique filename; never replace existing output.
    n = 0
    while True:
        extension = '.mkv' if mode == 'mkv-lossless' else '.mp4'
        target = folder / f'{source.stem}_BACKWARDS{f"_{n}" if n else ""}{extension}'
        try:
            reservation = target.open('xb')
            reservation.close()
            break
        except FileExistsError:
            n += 1
    log(f'{source.name}: {seconds:.2f}s; video + audio' if audio else f'{source.name}: {seconds:.2f}s; silent video')
    try:
        with tempfile.TemporaryDirectory(prefix='flip_reverse_') as temp:
            temp = Path(temp)
            chunks = math.ceil(seconds / 2)
            parts = []
            for step, i in enumerate(reversed(range(chunks)), 1):
                start = i * 2
                length = min(2, seconds - start)
                part = temp / f'part_{step:06d}.mkv'
                args = ['-v', 'error', '-ss', str(start), '-t', f'{length:.9f}', '-i', str(source),
                        '-map', '0:v:0', '-vf', 'reverse,setpts=PTS-STARTPTS',
                        '-c:v', 'ffv1', '-level', '3', '-coder', '0', '-g', '1', '-threads', '2',
                        '-fps_mode', 'passthrough']
                if audio:
                    args += ['-map', '0:a:0', '-af', 'areverse,asetpts=PTS-STARTPTS', '-c:a', 'pcm_f64le']
                args += ['-map_metadata', '-1', '-y', str(part)]
                run(args)
                parts.append(part)
                log(f'{source.name}: chunk {step}/{chunks} ({step / chunks:.0%})')
            listing = temp / 'parts.txt'
            listing.write_text(''.join(f"file '{p.name}'\n" for p in parts), encoding='utf-8')
            log('Writing final ' + mode + ' output...')
            finished = temp / ('finished' + extension)
            encoding = ['-c', 'copy'] if mode == 'mkv-lossless' else [
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '0' if mode == 'mp4-lossless' else '16',
                '-fps_mode', 'passthrough', '-movflags', '+faststart']
            if mode == 'mp4-compatible':
                encoding += ['-pix_fmt', 'yuv420p']
            if audio and mode != 'mkv-lossless':
                encoding += ['-c:a', 'alac'] if mode == 'mp4-lossless' else ['-c:a', 'aac', '-b:a', '256k']
            run(['-v', 'error', '-f', 'concat', '-safe', '0', '-i', str(listing), *encoding, '-y', str(finished)])
            # Scratch is local even for network inputs. Copy to the reserved destination.
            shutil.copyfile(finished, target)
        log(f'SAVED: {target}')
        return target
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    root = tk.Tk()
    root.title('Flip Video — Lossless Reverse')
    root.geometry('730x480')
    root.minsize(620, 380)
    root.configure(padx=20, pady=16)
    ttk.Label(root, text='Play your videos backwards', font=('Segoe UI', 18, 'bold')).pack(anchor='w')
    ttk.Label(root, text='Choose videos → reverse → find *_BACKWARDS.mp4 beside each original.').pack(anchor='w', pady=(8, 4))
    ttk.Label(root, text='Originals preserved. Resolution and frame rate retained.\nLossless MP4 needs a supporting player (such as VLC). Choose compatible MP4 for editors.').pack(anchor='w', pady=(0, 8))
    modes = {'MP4 — lossless (exact frames)': 'mp4-lossless',
             'MP4 — compatible (high quality, not lossless)': 'mp4-compatible',
             'MKV — lossless FFV1': 'mkv-lossless'}
    choice = ttk.Combobox(root, values=list(modes), state='readonly', width=57)
    choice.current(0)
    choice.pack(anchor='w', pady=(0, 8))
    messages = queue.Queue()
    output = tk.Text(root, height=15, wrap='word', font=('Consolas', 10), state='disabled')
    button = ttk.Button(root, text='Choose videos and reverse')
    button.pack(anchor='w', pady=(0, 12))
    output.pack(fill='both', expand=True)
    active = [False]

    def work(files, mode):
        failures = 0
        for file in files:
            try:
                reverse(file, log=lambda line: messages.put(('log', line)), mode=mode)
            except Exception as error:
                failures += 1
                messages.put(('log', f'ERROR: {file}\n{error}'))
        messages.put(('done', failures))

    def choose():
        files = filedialog.askopenfilenames(title='Choose videos', filetypes=[('Video files', '*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.mts *.m2ts *.wmv *.gif'), ('All files', '*.*')])
        if files:
            active[0] = True
            button.config(state='disabled')
            threading.Thread(target=work, args=(files, modes[choice.get()]), daemon=True).start()

    def poll():
        while not messages.empty():
            kind, value = messages.get_nowait()
            if kind == 'done':
                active[0] = False
                button.config(state='normal')
                if value:
                    messagebox.showerror('Finished with errors', 'Some videos failed. See the log below.')
                else:
                    messagebox.showinfo('Videos ready', 'Reversed videos saved beside the originals.')
            else:
                output.config(state='normal')
                output.insert('end', str(value) + '\n')
                output.see('end')
                output.config(state='disabled')
        root.after(150, poll)

    button.config(command=choose)
    root.protocol('WM_DELETE_WINDOW', lambda: messagebox.showinfo('Processing', 'Please wait for processing to finish.') if active[0] else root.destroy())
    poll()
    root.mainloop()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('videos', nargs='*')
    parser.add_argument('--out-dir', type=Path)
    parser.add_argument('--mode', choices=['mp4-lossless', 'mp4-compatible', 'mkv-lossless'], default='mp4-lossless')
    args = parser.parse_args()
    if not args.videos:
        gui()
    else:
        for video in args.videos:
            reverse(video, args.out_dir, mode=args.mode)
