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
        self._publish_lock = threading.Lock()
        self._cleanup_lock = threading.Lock()
        self._cleanup_thread = None
        self.process = subprocess.Popen(decoder_command(ffmpeg,path,*self.size,mode['fps'],loop),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.thread = threading.Thread(target=self._run,name='scoreboard-media',daemon=True)

    def start(self):
        try:
            with self._publish_lock:
                if not self.stopping.is_set():
                    self.thread.start()
        except Exception:
            self.request_stop()
            raise

    def _run(self):
        count = self.size[0]*self.size[1]*3
        frames = 0
        deadline = None
        prepare = getattr(self.output,'prepare_frame',None)
        publish = getattr(self.output,'update_prepared',None)
        prepared_output = callable(prepare) and callable(publish)
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
                    image = self.core.Image.frombytes('RGB',self.size,bytes(data))
                    if self.has_overlay:
                        image.paste(self.overlay,(0,0),self.overlay)
                    prepared = prepare(image) if prepared_output else None
                    # Demuxers can release a whole GOP at once, even with -re.
                    # Keep a fixed presentation cadence without adding conversion
                    # and output preparation time to every frame's duration.
                    if deadline is None:
                        deadline = time.monotonic()
                    if self.stopping.wait(max(0,deadline-time.monotonic())):
                        break
                    with self._publish_lock:
                        if self.stopping.is_set():
                            break
                        presented_at = time.monotonic()
                        if prepared_output:
                            publish(prepared)
                        else:
                            self.output.update(image)
                    deadline = presented_at + self.frame_interval
                    frames += 1
        except Exception as exc:
            if not self.stopping.is_set():
                self.error = 'Video playback failed: ' + str(exc)
        finally:
            self.finished = True
            self.request_stop()

    def request_stop(self):
        """Retire this source before returning; reap its decoder off the take path."""
        with self._publish_lock:
            self.stopping.set()
        with self._cleanup_lock:
            if self._cleanup_thread is None:
                self._cleanup_thread = threading.Thread(
                    target=self._cleanup,name='scoreboard-media-cleanup',daemon=True)
                self._cleanup_thread.start()

    def _cleanup(self):
        try:
            if self.process.poll() is None:
                self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        except (OSError,subprocess.TimeoutExpired):
            pass
        if self.thread.is_alive():
            self.thread.join(timeout=5)
        if not self.thread.is_alive():
            self.process.stdout.close()

    def stop(self):
        self.request_stop()
        self._cleanup_thread.join(timeout=16)
