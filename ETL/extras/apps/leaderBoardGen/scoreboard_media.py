"""Local-file video decoding for the scoreboard's existing video-only SDI output."""
import subprocess
import threading
import time


VIDEO_EXTENSIONS = {'.mp4','.mov','.mkv','.webm','.avi','.m4v','.mpg','.mpeg','.ts','.gif'}
IMAGE_EXTENSIONS = {'.png','.jpg','.jpeg','.webp','.bmp','.avif'}
MAX_MEDIA_BYTES = 512 * 1024 * 1024


def decoder_command(ffmpeg, path, width, height, fps, loop=True):
    command = [ffmpeg,'-hide_banner','-loglevel','error','-nostdin','-re']
    if loop:
        command += ['-stream_loop','-1']
    return command + ['-protocol_whitelist','file,pipe','-i',str(path),'-map','0:v:0','-an',
        '-vf',f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}',
        '-pix_fmt','rgb24','-f','rawvideo','pipe:1']


class VideoPlayback:
    def __init__(self, core, output, path, preset, loop=True, config=None):
        ffmpeg = core.locate_ffmpeg()
        if not ffmpeg:
            raise ValueError('FFmpeg is required for video playback.')
        mode = core.VIDEO_EXPORT_PRESETS[preset]
        self.size = (mode['width'],mode['height'])
        self.frame_interval = 1.0 / mode['fps']
        self.core, self.output = core, output
        self.overlay = core.render_custom_text_overlay(config or {},self.size)
        self.has_overlay = self.overlay.getbbox() is not None
        self.error = None
        self.finished = False
        self.stopping = threading.Event()
        self.process = subprocess.Popen(decoder_command(ffmpeg,path,*self.size,mode['fps'],loop),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.thread = threading.Thread(target=self._run,name='scoreboard-media',daemon=True)

    def start(self):
        self.thread.start()

    def _run(self):
        count = self.size[0]*self.size[1]*3
        frames = 0
        deadline = None
        try:
            while not self.stopping.is_set():
                data = bytearray()
                while len(data) < count and not self.stopping.is_set():
                    part = self.process.stdout.read(count-len(data))
                    if not part:
                        break
                    data.extend(part)
                if len(data) != count:
                    code = self.process.wait(timeout=5)
                    if not self.stopping.is_set() and (code or not frames):
                        self.error = 'Video decoding failed. The last valid frame is held.'
                    break
                if not self.stopping.is_set():
                    # Demuxers can release a whole GOP at once, even with -re.
                    # Pace presentation so the SDI latest-frame buffer sees each frame.
                    if deadline is not None and self.stopping.wait(max(0,deadline-time.monotonic())):
                        break
                    image = self.core.Image.frombytes('RGB',self.size,bytes(data))
                    if self.has_overlay:
                        image.paste(self.overlay,(0,0),self.overlay)
                    self.output.update(image)
                    deadline = time.monotonic() + self.frame_interval
                    frames += 1
        except Exception as exc:
            if not self.stopping.is_set():
                self.error = 'Video playback failed: ' + str(exc)
        finally:
            if self.process.poll() is None:
                self.process.terminate()
            self.finished = True

    def stop(self):
        self.stopping.set()
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        if self.thread.is_alive():
            self.thread.join(timeout=5)
        self.process.stdout.close()
