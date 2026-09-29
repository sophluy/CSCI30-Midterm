"""Fallback tkinter front-end. Provided, not graded, not required.

    python -m tonematrix.gui_tk

The main GUI is `tonematrix.gui`, built on PySide6. This one exists for
machines where PySide6 will not install. It looks and sounds the same; it is
the fallback rather than the default because tkinter is missing from a good
number of Python installations, macOS ones especially, whereas PySide6 ships
as a self-contained wheel.
"""

import os
import queue
import shutil
import tempfile
import threading
import time
import tkinter as tk

from tonematrix.audio import SAMPLE_RATE, SAMPLES_PER_COLUMN, write_wav
from tonematrix.gui_common import (BG, CELL_OFF, GRID_LINE, TICK_MS,
                                   Highlighter)
from tonematrix.matrix import ToneMatrix
from tonematrix.playback import AudioStream, LoopPlayer, render_loop, render_pass

CELL = 30
PAD = 8


class ToneMatrixApp:
    def __init__(self, root, size=16):
        self.root = root
        self.matrix = ToneMatrix(size)
        self.lock = threading.Lock()
        self.highlighter = Highlighter(self.matrix)
        self.tempdir = tempfile.mkdtemp(prefix="tonematrix-")

        self.streaming = AudioStream.available()
        if self.streaming:
            self.player = AudioStream(self.matrix, self.lock,
                                      on_error=self.on_audio_error)
        else:
            self.player = LoopPlayer()

        self.playing = False
        self.busy = False           # a render is in flight on a worker thread
        self.pending = False        # an edit arrived while that render ran
        self.painted = {}           # flat index -> color on screen right now
        self.tick_job = None
        self.results = queue.Queue()   # worker threads report back through this
        self.poll_job = None

        root.title("Tone Matrix")
        root.configure(bg=BG)

        self.canvas = tk.Canvas(root, highlightthickness=0, bg=GRID_LINE)
        self.canvas.pack(padx=PAD, pady=PAD)
        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)

        bar = tk.Frame(root, bg=BG)
        bar.pack(fill="x", padx=PAD, pady=(0, PAD))

        self.play_button = tk.Button(bar, text="Play", width=8,
                                     command=self.toggle_play)
        self.play_button.pack(side="left")
        tk.Button(bar, text="Clear", width=8,
                  command=self.on_clear).pack(side="left", padx=4)
        self.export_button = tk.Button(bar, text="Export WAV", width=10,
                                       command=self.on_export)
        self.export_button.pack(side="left")

        tk.Label(bar, text="size", bg=BG).pack(side="left", padx=(12, 4))
        self.size_var = tk.StringVar(value=str(size))
        tk.OptionMenu(bar, self.size_var, "4", "8", "12", "16", "24", "32",
                      command=self.on_resize).pack(side="left")

        self.status = tk.Label(root, text="", bg=BG, anchor="w")
        self.status.pack(fill="x", padx=PAD, pady=(0, PAD))

        if not (self.streaming or LoopPlayer.available()):
            self.play_button.configure(state="disabled")
            self.say("No audio output found -- use Export WAV.")
        else:
            self.say("Click and drag to draw. Press Play.")

        self.rebuild_canvas()
        self.poll_results()

    ### worker results

    def poll_results(self):
        """Drain messages from worker threads on the UI thread.

        Tkinter is not thread-safe: a worker must never touch a widget or
        call root.after() itself. It posts here instead and we pick it up.
        """
        try:
            while True:
                kind, payload = self.results.get_nowait()
                if kind == "loop":
                    self.render_done(payload)
                elif kind == "export":
                    self.export_done()
                elif kind == "audio-error":
                    self.audio_failed()
        except queue.Empty:
            pass
        self.poll_job = self.root.after(80, self.poll_results)

    ### drawing

    def rebuild_canvas(self):
        n = self.matrix.grid_size
        self.canvas.configure(width=n * CELL, height=n * CELL)
        self.canvas.delete("all")
        self.rects = []
        self.painted = {}
        for row in range(n):
            for col in range(n):
                x, y = col * CELL, row * CELL
                self.rects.append(self.canvas.create_rectangle(
                    x + 1, y + 1, x + CELL - 1, y + CELL - 1,
                    fill=CELL_OFF, outline=""))
        self.refresh()

    def paint(self, indices, now=None):
        """Recolor just the cells that changed."""
        now = now or time.perf_counter()
        for index in indices:
            color = self.highlighter.color_for(index, now)
            if self.painted.get(index) != color:
                self.canvas.itemconfigure(self.rects[index], fill=color)
                self.painted[index] = color

    def refresh(self):
        self.paint(range(len(self.rects)))

    def say(self, text):
        self.status.configure(text=text)

    ### animation

    def tick(self):
        self.paint(self.highlighter.advance(self.player.position()))
        self.tick_job = self.root.after(TICK_MS, self.tick)

    def stop_animation(self):
        if self.tick_job is not None:
            self.root.after_cancel(self.tick_job)
            self.tick_job = None
        self.highlighter.reset()
        self.refresh()

    ### events

    def cell_at(self, event):
        """Pixel coordinates to (row, col). The only geometry in the app."""
        n = self.matrix.grid_size
        row = min(max(event.y // CELL, 0), n - 1)
        col = min(max(event.x // CELL, 0), n - 1)
        return int(row), int(col)

    def on_press(self, event):
        row, col = self.cell_at(event)
        self.matrix.press(row, col)
        self.after_edit()

    def on_drag(self, event):
        row, col = self.cell_at(event)
        self.matrix.drag(row, col)
        self.after_edit()

    def on_clear(self):
        """Wipe the grid, without interrupting playback.

        The playhead carries on over an empty grid, plucking nothing, and any
        string still ringing from before the wipe decays away on its own
        rather than being cut off. Draw something and it is audible on the
        next pass, exactly as any other edit would be.
        """
        with self.lock:
            self.matrix.clear()
        self.after_edit()
        self.say("cleared")

    def on_resize(self, value):
        was_playing = self.playing
        if was_playing:
            self.stop_playback()
        with self.lock:
            self.matrix.resize(int(value))
        self.rebuild_canvas()
        if was_playing:
            self.start_playback()

    def after_edit(self):
        """A single cell changed.

        Streaming picks the change up on the playhead's next pass with no
        work here at all. The file backend has to re-render, which we push
        onto a worker thread so that dragging stays smooth.
        """
        self.refresh()
        if self.playing and not self.streaming:
            self.schedule_render()

    def on_audio_error(self):
        self.results.put(("audio-error", None))

    def audio_failed(self):
        self.stop_playback()
        self.say("audio output stopped unexpectedly -- try Export WAV.")

    ### audio

    def schedule_render(self):
        """Re-render the loop off the UI thread, then hand it to the player."""
        if self.busy:
            self.pending = True
            return
        self.busy = True
        self.pending = False
        self.say("rendering...")

        def work():
            n = self.matrix.grid_size
            samples = render_loop(self.matrix, self.lock, n * SAMPLES_PER_COLUMN)
            path = os.path.join(self.tempdir, "loop.wav")
            write_wav(path, samples, SAMPLE_RATE)
            self.results.put(("loop", path))

        threading.Thread(target=work, daemon=True).start()

    def render_done(self, path):
        self.busy = False
        if self.pending:                # edits arrived while we were rendering
            self.schedule_render()
            return
        if self.playing:
            self.player.play(path)
            self.say("playing")

    def start_playback(self):
        self.stop_animation()
        self.playing = True
        self.play_button.configure(text="Stop")

        if self.streaming:
            name = self.player.start()
            if name is not None:
                self.say(f"playing ({name})")
                self.tick()
                return
            self.fall_back_to_file()

        if self.playing:
            self.schedule_render()
            self.tick()

    def fall_back_to_file(self):
        """No real-time sink would open. Repeat a rendered file instead."""
        self.streaming = False
        self.player = LoopPlayer()
        if not LoopPlayer.available():
            self.playing = False
            self.play_button.configure(text="Play", state="disabled")
            self.stop_animation()
            self.say("No audio output available -- use Export WAV.")

    def stop_playback(self):
        self.player.stop()
        self.playing = False
        self.play_button.configure(text="Play")
        self.stop_animation()

    def toggle_play(self):
        if self.playing:
            self.stop_playback()
            self.say("stopped")
        else:
            self.start_playback()

    def on_export(self):
        if self.busy:
            return
        self.busy = True
        self.pending = False
        self.export_button.configure(state="disabled")
        self.say("rendering...")

        def work():
            samples = render_pass(self.matrix, self.lock, SAMPLE_RATE * 8)
            write_wav("tonematrix.wav", samples, SAMPLE_RATE)
            self.results.put(("export", None))

        threading.Thread(target=work, daemon=True).start()

    def export_done(self):
        self.busy = False
        self.export_button.configure(state="normal")
        self.say("wrote tonematrix.wav (8 seconds)")

    def close(self):
        if self.poll_job is not None:
            self.root.after_cancel(self.poll_job)
            self.poll_job = None
        self.player.stop()
        shutil.rmtree(self.tempdir, ignore_errors=True)
        self.root.destroy()


def main():
    root = tk.Tk()
    app = ToneMatrixApp(root)
    root.protocol("WM_DELETE_WINDOW", app.close)
    root.mainloop()


if __name__ == "__main__":
    main()
