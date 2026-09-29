"""The GUI. Provided, not graded, not required.

    python -m tonematrix.gui

Built on PySide6, which `requirements.txt` installs. Qt ships as a
self-contained wheel on all three platforms, so there is no system package
behind it.

There is a second front-end, `tonematrix.gui_tk`, built on tkinter. It looks
and sounds the same and is there as a fallback: use it if PySide6 will not
install on your machine. Do not expect tkinter itself to be a safe bet (for one,
it is missing from a good number of macOS Pythons) which is why the Qt
version is the default one.
"""

import os
import shutil
import sys
import tempfile
import threading

from tonematrix.audio import SAMPLE_RATE, SAMPLES_PER_COLUMN, write_wav
from tonematrix.gui_common import (BG, BORDER, CELL_ON, GRID_LINE, MUTED,
                                   PANEL, TEXT, TICK_MS, Highlighter)
from tonematrix.matrix import ToneMatrix
from tonematrix.playback import AudioStream, LoopPlayer, render_loop, render_pass

try:
    from PySide6.QtCore import QRect, Qt, QTimer, Signal
    from PySide6.QtGui import QColor, QPainter, QRegion
    from PySide6.QtWidgets import (QApplication, QComboBox, QHBoxLayout,
                                   QLabel, QPushButton, QVBoxLayout, QWidget)
except ImportError:                                         # pragma: no cover
    sys.exit("The GUI needs PySide6:  pip install PySide6\n"
             "(it is in requirements.txt), or fall back to the tkinter\n"
             "front-end with:  python -m tonematrix.gui_tk")

CELL = 30
PAD = 8
SIZES = ["4", "8", "12", "16", "24", "32"]

# Every color is stated explicitly. Setting only background-color leaves the
# text color to the system palette, which under a dark desktop theme means
# white labels on a near-white panel.
STYLESHEET = f"""
QWidget {{ background-color: {BG}; color: {TEXT}; }}
QLabel {{ background: transparent; color: {TEXT}; }}
QPushButton {{
    background-color: {PANEL}; color: {TEXT};
    border: 1px solid {BORDER}; border-radius: 4px; padding: 6px 14px;
}}
QPushButton:hover {{ background-color: #eef1ff; }}
QPushButton:pressed {{ background-color: #dfe4ff; }}
QPushButton:disabled {{ background-color: #ececf1; color: {MUTED}; }}
QComboBox {{
    background-color: {PANEL}; color: {TEXT};
    border: 1px solid {BORDER}; border-radius: 4px; padding: 4px 10px;
}}
QComboBox QAbstractItemView {{
    background-color: {PANEL}; color: {TEXT};
    selection-background-color: {CELL_ON}; selection-color: #ffffff;
}}
"""


class GridView(QWidget):
    """The matrix itself: a grid of cells you can click and drag across."""

    pressed = Signal(int, int)
    dragged = Signal(int, int)

    def __init__(self, matrix, highlighter):
        super().__init__()
        self.matrix = matrix
        self.highlighter = highlighter
        self.setMouseTracking(False)
        self.resize_to_grid()

    def resize_to_grid(self):
        side = self.matrix.grid_size * CELL
        self.setFixedSize(side, side)

    def cell_rect(self, index):
        row, col = divmod(index, self.matrix.grid_size)
        return QRect(col * CELL, row * CELL, CELL, CELL)

    def refresh_cells(self, indices):
        """Queue a repaint covering just these cells."""
        if not indices:
            return
        region = QRegion()
        for index in indices:
            region += self.cell_rect(index)
        self.update(region)

    def cell_at(self, point):
        """Pixel coordinates to (row, col). The only geometry in the app."""
        n = self.matrix.grid_size
        row = min(max(int(point.y()) // CELL, 0), n - 1)
        col = min(max(int(point.x()) // CELL, 0), n - 1)
        return row, col

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.pressed.emit(*self.cell_at(event.position()))

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self.dragged.emit(*self.cell_at(event.position()))

    def paintEvent(self, event):
        painter = QPainter(self)
        clip = event.rect()
        painter.fillRect(clip, QColor(GRID_LINE))
        n = self.matrix.grid_size
        for row in range(n):
            for col in range(n):
                cell = QRect(col * CELL + 1, row * CELL + 1, CELL - 2, CELL - 2)
                if not clip.intersects(cell):
                    continue
                painter.fillRect(cell, QColor(
                    self.highlighter.color_for(n * row + col)))


class ToneMatrixWindow(QWidget):
    # Worker threads emit these; Qt delivers them on the GUI thread.
    renderFinished = Signal(str)
    exportFinished = Signal()
    audioFailed = Signal()

    def __init__(self, size=16):
        super().__init__()
        self.matrix = ToneMatrix(size)
        self.lock = threading.Lock()
        self.highlighter = Highlighter(self.matrix)
        self.tempdir = tempfile.mkdtemp(prefix="tonematrix-")

        self.streaming = AudioStream.available()
        if self.streaming:
            self.player = AudioStream(self.matrix, self.lock,
                                      on_error=self.audioFailed.emit)
        else:
            self.player = LoopPlayer()

        self.playing = False
        self.busy = False
        self.pending = False

        self.setWindowTitle("Tone Matrix")
        self.setStyleSheet(STYLESHEET)

        self.grid = GridView(self.matrix, self.highlighter)
        self.grid.pressed.connect(self.on_press)
        self.grid.dragged.connect(self.on_drag)

        self.play_button = QPushButton("Play")
        self.play_button.clicked.connect(self.toggle_play)
        clear_button = QPushButton("Clear")
        clear_button.clicked.connect(self.on_clear)
        self.export_button = QPushButton("Export WAV")
        self.export_button.clicked.connect(self.on_export)

        self.size_box = QComboBox()
        self.size_box.addItems(SIZES)
        self.size_box.setCurrentText(str(size))
        self.size_box.currentTextChanged.connect(self.on_resize)

        bar = QHBoxLayout()
        for widget in (self.play_button, clear_button, self.export_button):
            bar.addWidget(widget)
        bar.addSpacing(12)
        bar.addWidget(QLabel("size"))
        bar.addWidget(self.size_box)
        bar.addStretch(1)

        self.status = QLabel("")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(PAD, PAD, PAD, PAD)
        layout.addWidget(self.grid, alignment=Qt.AlignCenter)
        layout.addLayout(bar)
        layout.addWidget(self.status)

        self.timer = QTimer(self)
        self.timer.setInterval(TICK_MS)
        self.timer.timeout.connect(self.tick)

        self.renderFinished.connect(self.render_done)
        self.exportFinished.connect(self.export_done)
        self.audioFailed.connect(self.on_audio_failed)

        if not (self.streaming or LoopPlayer.available()):
            self.play_button.setEnabled(False)
            self.say("No audio output found -- use Export WAV.")
        else:
            self.say("Click and drag to draw. Press Play.")

    def say(self, text):
        self.status.setText(text)

    ### animation

    def tick(self):
        self.grid.refresh_cells(self.highlighter.advance(self.player.position()))

    def stop_animation(self):
        self.timer.stop()
        self.highlighter.reset()
        self.grid.update()

    ### events

    def on_press(self, row, col):
        self.matrix.press(row, col)
        self.after_edit()

    def on_drag(self, row, col):
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
        self.highlighter.reset()
        self.grid.resize_to_grid()
        self.adjustSize()
        if was_playing:
            self.start_playback()
        else:
            self.grid.update()

    def after_edit(self):
        """A single cell changed.

        Streaming picks the change up on the playhead's next pass with no
        work here at all. The file backend has to re-render, which we push
        onto a worker thread so that dragging stays smooth.
        """
        self.grid.update()
        if self.playing and not self.streaming:
            self.schedule_render()

    def on_audio_failed(self):
        self.stop_playback()
        self.say("audio output stopped unexpectedly -- try Export WAV.")

    ### audio 

    def schedule_render(self):
        """Re-render the loop off the GUI thread, then hand it to the player."""
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
            self.renderFinished.emit(path)

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
        self.play_button.setText("Stop")

        if self.streaming:
            name = self.player.start()
            if name is not None:
                self.say(f"playing ({name})")
                self.timer.start()
                return
            self.fall_back_to_file()

        if self.playing:
            self.schedule_render()
            self.timer.start()

    def fall_back_to_file(self):
        """No real-time sink would open. Repeat a rendered file instead."""
        self.streaming = False
        self.player = LoopPlayer()
        if not LoopPlayer.available():
            self.playing = False
            self.play_button.setText("Play")
            self.play_button.setEnabled(False)
            self.stop_animation()
            self.say("No audio output available -- use Export WAV.")

    def stop_playback(self):
        self.player.stop()
        self.playing = False
        self.play_button.setText("Play")
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
        self.export_button.setEnabled(False)
        self.say("rendering...")

        def work():
            samples = render_pass(self.matrix, self.lock, SAMPLE_RATE * 8)
            write_wav("tonematrix.wav", samples, SAMPLE_RATE)
            self.exportFinished.emit()

        threading.Thread(target=work, daemon=True).start()

    def export_done(self):
        self.busy = False
        self.export_button.setEnabled(True)
        self.say("wrote tonematrix.wav (8 seconds)")

    def closeEvent(self, event):
        self.timer.stop()
        self.player.stop()
        shutil.rmtree(self.tempdir, ignore_errors=True)
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    # Fusion honors stylesheet colors identically on all three platforms; the
    # native macOS and Windows styles ignore some of them on buttons.
    app.setStyle("Fusion")
    window = ToneMatrixWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
