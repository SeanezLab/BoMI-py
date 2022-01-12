import math
import time
import random
from typing import List, Tuple
import PySide6.QtGui as qg
import PySide6.QtWidgets as qw
import PySide6.QtCore as qc
from PySide6.QtCore import Qt
import numpy as np


def _print(*args):
    print("[Reaching]", *args)


class ReachingWidget(qw.QWidget):
    GREEN = qg.QColor(0, 255, 0)
    RED = qg.QColor(255, 0, 0)

    INF = np.inf

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Reaching Exercise")
        layout = qw.QGridLayout(self)
        self.setLayout(layout)

        # change background color
        p = self.palette()
        p.setColor(self.backgroundRole(), Qt.black)
        self.setPalette(p)

        # init top label
        self.top_label = l1 = qw.QLabel("Reaching", self)
        l1.setStyleSheet("QLabel { background-color: black; color: white; }")
        l1.setFont(qg.QFont('Arial', 18))
        layout.addWidget(l1, 0, 0, alignment=Qt.AlignTop | Qt.AlignLeft)
        

        # Reaching params
        self._hold_time = 0.5
        self._time_limit = 1.0

        ### Cursor states
        # This is updated only by `mouseMoveEvent`,
        # read-only for `_update_reaching_state`
        self._cursor_pos = qc.QPoint(0, 0)
        self._last_cursor_inside = False
        self._target_acquired_time = self.INF
        self._target_created_time = time.time()
        self.setMouseTracking(True)

        ### Generate targets
        center, targets = self.generate_targets()
        self._target_base: qc.QPoint = center
        self._targets: List[qc.QPoint] = targets
        self._target_radius: int = 40

        ### Current target states
        # updated only by `_update_reaching_state` and `_move_target`
        self._target_center: qc.QPoint = qc.QPoint(0, 0)
        self._target_color = self.GREEN
        self._move_target()

        ### Setup update timer
        self.timer = qc.QTimer()
        self.timer.timeout.connect(self._update_reaching_state)
        self.timer.start(1000 / 50)  # 50 Hz update rate

        _print("Initialized")
    
    def __del__(self):
        _print("Bye bye")

    @staticmethod
    def generate_targets(n_targets=8, n_reps=3) -> Tuple[qc.QPoint, List[qc.QPoint]]:
        # Init targets
        geo = qw.QApplication.primaryScreen().geometry()
        dist = geo.height() / 2 * 0.8
        center = qc.QPoint(geo.width() // 2, geo.height() // 2)
        targets: List[qc.QPoint] = []
        for i in range(n_targets):
            alpha = 2 * np.pi * i / n_targets
            c = center + qc.QPoint(dist * np.cos(alpha), dist * np.sin(alpha))
            targets.extend([c] * n_reps)
        random.shuffle(targets)
        return center, targets

    def _move_target(self, random_target=False):
        if random_target:
            # Generate random target
            geo = self.geometry()
            r = self._target_radius
            y = np.random.randint(r, geo.height() - r)
            x = np.random.randint(r, geo.width() - r)
            self._target_center = qc.QPoint(x, y)
        else:
            if self._target_center == self._target_base:
                self._target_center = self._targets.pop()
            else:
                self._target_center = self._target_base
            _print(len(self._targets), "targets left")

    def paintEvent(self, event: qg.QPaintEvent):
        painter = qg.QPainter(self)
        painter.setRenderHint(qg.QPainter.Antialiasing)
        # Paint target
        painter.setBrush(self._target_color)
        painter.drawEllipse(
            self._target_center, self._target_radius, self._target_radius
        )
        return super().paintEvent(event)

    def _update_reaching_state(self):
        """Check cursor states and decide whether to update the target"""
        now = time.time()
        if now - self._target_acquired_time > self._hold_time:
            _print(f"Held for long enough ({self._hold_time}s). Moving target")
            self._target_color = self.GREEN
            self._last_cursor_inside = False
            self._target_created_time = now
            self._target_acquired_time = self.INF
            self._move_target()
            self.update()
        elif now - self._target_created_time > self._time_limit:
            if self._target_color != self.RED and not self._last_cursor_inside:
                _print(
                    f"Failed to reach target within time limit ({self._time_limit}s)"
                )
                self._target_color = self.RED
                self.update()

    def _update_cursor_state(self):
        # update cursor states
        now = time.time()
        d = self._target_center - self._cursor_pos
        cursor_inside = math.hypot(d.x(), d.y()) < self._target_radius
        if cursor_inside:
            if not self._last_cursor_inside:
                self._target_acquired_time = now
                self._target_moved = False
        else:
            self._target_acquired_time = self.INF

        self._last_cursor_inside = cursor_inside
    
    def _update_top_msg(self):
        _print("Updating message")
        self.top_label.setText(f"Reaching. Targets to reach: {len(self._targets)}")

    def update(self):
        self._update_cursor_state()
        self._update_top_msg()
        return super().update()
        

    def mouseMoveEvent(self, event: qg.QMouseEvent) -> None:
        "Callback for any cursor movement inside the widget"
        self._cursor_pos = event.pos()
        self.update()
        return super().mouseMoveEvent(event)
