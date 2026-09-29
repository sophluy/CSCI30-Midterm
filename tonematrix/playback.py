"""Audio output for the GUIs. Provided, do not modify.

Output is picked automatically, best available first:

  1. A real-time device, via `sounddevice` (recommended) or `pyaudio`. Both
     wrap PortAudio and ship wheels for Windows, macOS, and Linux, so this is
     the path that works everywhere:  pip install sounddevice
  2. Raw PCM piped to a command-line player: pacat, aplay, sox, ffplay.
  3. Failing both, a rendered WAV file played on repeat.

The first two stream: a background thread calls your next_sample() a couple
of thousand samples at a time and hands the results straight to the output,
so nothing is pre-rendered, there is no loop seam, and edits are audible on
the playhead's next pass. The third has to re-render on every edit.
"""

import importlib.util
import math
import os
import shutil
import subprocess
import sys
import threading
import time

from tonematrix.audio import SAMPLE_RATE, clip

# Samples handed to the output per write. About 46ms.
CHUNK = 2048

# How far ahead of the speakers a self-paced producer stays.
PREBUFFER_SECONDS = 0.3
PREBUFFER = int(PREBUFFER_SECONDS * SAMPLE_RATE)


# ---------------------------------------------------------------------------
# Sinks: somewhere to put raw 16-bit mono PCM, a block at a time.
# ---------------------------------------------------------------------------

class Sink:
    """`blocking` says whether write() returns only once the device has room.

    That is what paces the producer. A sound device blocks; a pipe to another
    process does not, so with a pipe the producer has to pace itself.
    """

    name = "?"
    blocking = True

    # How many samples sit between what we have written and what the listener
    # is hearing: the device or player's own buffer. position() subtracts it.
    lead_samples = 0

    def write(self, block):
        raise NotImplementedError

    def close(self):
        pass


class DeviceSink(Sink):
    """A real-time output stream, via sounddevice or PyAudio.

    Both wrap PortAudio and both accept raw int16 bytes, which means no NumPy
    dependency.
    """

    blocking = True

    def __init__(self, name, write, close, lead_samples=0):
        self.name = name
        self._write = write
        self._close = close
        self.lead_samples = lead_samples

    def write(self, block):
        self._write(block)

    def close(self):
        try:
            self._close()
        except Exception:
            pass


class PipeSink(Sink):
    """Raw PCM on the stdin of a command-line player."""

    blocking = False
    lead_samples = PREBUFFER

    def __init__(self, command):
        self.name = os.path.basename(command[0])
        self._proc = subprocess.Popen(command, stdin=subprocess.PIPE,
                                      stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL)

    def write(self, block):
        self._proc.stdin.write(block)
        self._proc.stdin.flush()

    def close(self):
        try:
            self._proc.stdin.close()
        except OSError:
            pass
        if self._proc.poll() is None:
            self._proc.terminate()


def _open_sounddevice():
    if importlib.util.find_spec("sounddevice") is None:
        return None
    import sounddevice

    stream = sounddevice.RawOutputStream(samplerate=SAMPLE_RATE, channels=1,
                                         dtype="int16", blocksize=CHUNK,
                                         latency="low")
    stream.start()
    return DeviceSink("sounddevice", stream.write,
                      lambda: (stream.stop(), stream.close()),
                      lead_samples=int(stream.latency * SAMPLE_RATE))


def _open_pyaudio():
    if importlib.util.find_spec("pyaudio") is None:
        return None
    import pyaudio

    engine = pyaudio.PyAudio()
    stream = engine.open(format=pyaudio.paInt16, channels=1, rate=SAMPLE_RATE,
                         output=True, frames_per_buffer=CHUNK)

    def close():
        stream.stop_stream()
        stream.close()
        engine.terminate()

    return DeviceSink("pyaudio", stream.write, close,
                      lead_samples=int(stream.get_output_latency() * SAMPLE_RATE))


def stream_command():
    """A command that plays raw 16-bit mono PCM read from stdin, or None."""
    rate = str(SAMPLE_RATE)
    for name in ("pacat", "paplay", "aplay", "play", "ffplay"):
        exe = shutil.which(name)
        if not exe:
            continue
        if name in ("pacat", "paplay"):
            return [exe, "--playback", "--raw", "--format=s16le",
                    "--channels=1", f"--rate={rate}", "--latency-msec=80"]
        if name == "aplay":
            return [exe, "-q", "-f", "S16_LE", "-c", "1", "-r", rate,
                    "--buffer-time=100000", "-"]
        if name == "play":
            return [exe, "-q", "-t", "raw", "-b", "16", "-e", "signed",
                    "-c", "1", "-r", rate, "-"]
        if name == "ffplay":
            return [exe, "-nodisp", "-autoexit", "-loglevel", "quiet",
                    "-fflags", "nobuffer", "-f", "s16le", "-ac", "1",
                    "-ar", rate, "-i", "pipe:0"]
    return None


def _open_pipe():
    command = stream_command()
    return PipeSink(command) if command else None


def open_sink():
    """First sink that actually opens, or None.

    Opening is where things fail in practice -- the package imports fine but
    there is no output device, or the device is busy -- so each candidate is
    tried for real rather than merely detected.
    """
    for factory in (_open_sounddevice, _open_pyaudio, _open_pipe):
        try:
            sink = factory()
        except Exception:
            continue
        if sink is not None:
            return sink
    return None


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------

class AudioStream:
    """Pulls samples from the matrix forever and feeds them to a sink.

    With a pipe sink the producer paces itself against a wall clock instead
    of writing as fast as the pipe will take it. That keeps the operating
    system's pipe buffer nearly empty, which is what lets position() report
    what is coming out of the speakers rather than what has been rendered.
    A device sink paces us on its own, by blocking in write().
    """

    def __init__(self, matrix, lock, on_error=None):
        self.matrix = matrix
        self.lock = lock
        self.on_error = on_error
        self.sink = None
        self.samples_written = 0
        self.started_at = None
        self._stop = threading.Event()
        self._thread = None

    @staticmethod
    def available():
        """Cheap check -- does not open a device."""
        return (importlib.util.find_spec("sounddevice") is not None
                or importlib.util.find_spec("pyaudio") is not None
                or stream_command() is not None)

    def start(self):
        """Open a sink and begin. Returns the sink's name, or None on failure.

        The playhead is rewound first. position() counts from zero at every
        start, so sample zero of the stream has to be column zero of the
        matrix -- otherwise a stream that begins where the last one stopped
        plucks column 5 while the highlight says column 0, and every note
        looks displaced by a fixed number of columns in one direction or the
        other for as long as the stream runs.
        """
        self.sink = open_sink()
        if self.sink is None:
            return None
        with self.lock:
            rewind(self.matrix)
        self.samples_written = 0
        self.started_at = time.perf_counter()
        self._stop.clear()
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()
        return self.sink.name

    def _render_chunk(self):
        block = bytearray()
        with self.lock:
            for _ in range(CHUNK):
                value = int(clip(self.matrix.next_sample()) * 32767)
                block += value.to_bytes(2, "little", signed=True)
        return bytes(block)

    def _pump(self):
        try:
            while not self._stop.is_set():
                if not self.sink.blocking:
                    elapsed = time.perf_counter() - self.started_at
                    if self.samples_written >= elapsed * SAMPLE_RATE + PREBUFFER:
                        time.sleep(CHUNK / SAMPLE_RATE / 2)
                        continue
                self.sink.write(self._render_chunk())
                self.samples_written += CHUNK
        except Exception:
            if self.on_error and not self._stop.is_set():
                self.on_error()

    def position(self):
        """Index of the sample the listener is hearing, roughly.

        Counted from samples actually handed to the output, minus whatever is
        still sitting in its buffer -- not from a wall clock. The difference
        matters when the producer cannot keep up: an underrunning device
        inserts silence, so the audio falls behind real time and a clock-based
        playhead drifts ahead of what you hear. This one stalls with the
        audio and stays put.
        """
        if self.sink is None or self.started_at is None:
            return 0
        return max(0, self.samples_written - self.sink.lead_samples)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self.sink:
            self.sink.close()
            self.sink = None
        self.started_at = None


# ---------------------------------------------------------------------------
# Fallback: repeat a rendered file
# ---------------------------------------------------------------------------

def file_command(path):
    if sys.platform == "darwin" and shutil.which("afplay"):
        return ["afplay", path]
    for name in ("paplay", "aplay", "play"):
        exe = shutil.which(name)
        if exe:
            return [exe, path]
    return None


class LoopPlayer:
    """Plays a WAV file on repeat in a background thread."""

    def __init__(self):
        self._stop = threading.Event()
        self._thread = None
        self._proc = None
        self.started_at = None

    @staticmethod
    def available():
        return sys.platform == "win32" or file_command("x") is not None

    def play(self, path):
        self.stop()
        self._stop.clear()
        self.started_at = time.perf_counter()
        self._thread = threading.Thread(target=self._loop, args=(path,), daemon=True)
        self._thread.start()

    def _loop(self, path):
        if sys.platform == "win32":
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC
                               | winsound.SND_LOOP)
            self._stop.wait()
            winsound.PlaySound(None, winsound.SND_PURGE)
            return

        command = file_command(path)
        while not self._stop.is_set():
            self._proc = subprocess.Popen(command, stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL)
            self._proc.wait()

    def position(self):
        if self.started_at is None:
            return 0
        return max(0, (time.perf_counter() - self.started_at) * SAMPLE_RATE)

    def stop(self):
        self._stop.set()
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
        if self._thread:
            self._thread.join(timeout=1.0)
        self._thread = None
        self.started_at = None


# ---------------------------------------------------------------------------
# Offline rendering, for the file backend and for Export
# ---------------------------------------------------------------------------

def rewind(matrix):
    """Put the playhead back on column 0 so a render starts on the beat.

    resize() to the current size does exactly this and leaves the pattern
    alone, which is convenient but means the file backend and Export need
    Milestone 8.
    """
    try:
        matrix.resize(matrix.grid_size)
    except NotImplementedError:
        pass


def render_pass(matrix, lock, count):
    """Render `count` samples from a standing start. Worker thread only."""
    with lock:
        rewind(matrix)
        return [matrix.next_sample() for _ in range(count)]


def render_loop(matrix, lock, count):
    """Render one pass that repeats without a seam. Worker thread only.

    A file loops cleanly only if its opening samples already contain the
    ring-out of the pass before it -- otherwise every repeat cuts the
    decaying strings off mid-ring, which is the click you hear. So run the
    matrix for a pass or two first and throw those samples away. By the time
    we keep a pass, the strings are in the state they would be in had the
    pattern been playing all along.

    Short loops need more warm-up passes than long ones, since a string rings
    for a second or so regardless of how fast the playhead moves.
    """
    warmups = min(3, max(1, math.ceil(2.0 * SAMPLE_RATE / count)))
    with lock:
        rewind(matrix)
        for _ in range(warmups * count):
            matrix.next_sample()
        return [matrix.next_sample() for _ in range(count)]
