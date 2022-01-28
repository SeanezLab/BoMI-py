from __future__ import annotations

import traceback
from random import random
from typing import NamedTuple

import numpy as np
import pyqtgraph as pg
import PySide6.QtCore as qc
import PySide6.QtGui as qg
import PySide6.QtWidgets as qw
from PySide6.QtCore import Qt

from bomi.base_widgets import TaskDisplay
from bomi.device_manager import YostDeviceManager
from bomi.scope_widget import ScopeConfig, ScopeWidget
from bomi.window_mixin import WindowMixin


def _print(*args):
    print("[Start React]", *args)


class SRState(NamedTuple):
    color: qg.QColor
    text: str
    duration: float = -1  # duration in seconds


class PrecisionDisplay(TaskDisplay):
    IDLE = SRState(color=Qt.lightGray, text="Get ready!")
    GO = SRState(color=Qt.green, text="Go!")
    TASK_DONE = SRState(color=Qt.lightGray, text="All done!")

    HOLD_TIME = 3000  # msec
    PAUSE_MIN = 2000
    PAUSE_RANDOM = 2000
    
    BTN_START_TXT = "Begin task"
    BTN_END_TXT = "End task"

    def __init__(self):
        super().__init__()

        ### Init UI
        main_layout = qw.QGridLayout()
        self.setLayout(main_layout)

        self.label = qw.QLabel("Get ready!")
        self.label.setFont(qg.QFont("Arial", 18))
        main_layout.addWidget(self.label, 0, 0, alignment=Qt.AlignCenter)

        self.setAutoFillBackground(True)

        self.start_stop_btn = qw.QPushButton(self.BTN_START_TXT)
        self.start_stop_btn.clicked.connect(self.toggle_start_stop)
        main_layout.addWidget(self.start_stop_btn, 5, 0)

        ### Task states
        self.n_cycles_left = 0

        self.set_state(self.IDLE)

    def set_state(self, s: SRState):
        self.setPalette(s.color)
        if s == self.IDLE and self.n_cycles_left:
            if self.n_cycles_left == 1:
                txt = f" {self.n_cycles_left} cycle left"
            else:
                txt = f" {self.n_cycles_left} cycles left"
            self.label.setText(s.text + txt)
        else:
            self.label.setText(s.text)

    @classmethod
    def get_wait_time(cls):
        return cls.HOLD_TIME + cls.PAUSE_MIN + (cls.PAUSE_RANDOM) * random()

    def one_cycle(self):
        """Send a visual signal to the subject to begin doing the task
        If there are more cycles remaining, schedule one more
        """
        self.signal_task.emit("GO")
        self.set_state(self.GO)

        if self.n_cycles_left > 1:
            qc.QTimer.singleShot(self.HOLD_TIME, lambda: self.set_state(self.IDLE))
            qc.QTimer.singleShot(self.get_wait_time(), self.one_cycle)
        else:
            qc.QTimer.singleShot(self.HOLD_TIME, self.end_task)

        self.n_cycles_left -= 1

    def begin_task(self, n_cycles: int = 2):
        """Begin the precision control task

        Begin sending random {visual, visual + auditory, visual + startling} to the subject per cycle,
        each cycle lasting 3 seconds.
        Wait a random amount of time before starting the next cycle until we finish `n_cycles`
        """
        self.n_cycles_left = n_cycles
        self.set_state(self.IDLE)
        qc.QTimer.singleShot(2000 + random() * 1000, self.one_cycle)

    def end_task(self):
        self.start_stop_btn.setText("Start")
        self.n_cycles_left = 0
        self.set_state(self.TASK_DONE)

    def toggle_start_stop(self):
        if self.start_stop_btn.text() == self.BTN_START_TXT:
            self.start_stop_btn.setText(self.BTN_END_TXT)
            self.begin_task()

        else:
            self.start_stop_btn.setText(self.BTN_START_TXT)
            self.end_task()


class StartReactWidget(qw.QWidget, WindowMixin):
    """GUI to manage StartReact tasks"""

    def __init__(self, device_manager: YostDeviceManager):
        super().__init__()
        self.dm = device_manager

        ### Init UI
        main_layout = qw.QVBoxLayout()
        self.setLayout(main_layout)

        btn1 = qw.QPushButton(text="Precision")
        btn1.clicked.connect(self.s_precision_task)
        main_layout.addWidget(btn1)

    def s_precision_task(self):
        dm = self.dm
        if not dm.has_sensors():
            return self.no_sensors_error()

        scope_config = ScopeConfig(
            window_title="Precision",
            task_widget=PrecisionDisplay(),
            show_scope_params=True,
            target_show=True,
            yrange=(0, 120),
            show_roll=False,
            show_pitch=False,
            show_yaw=False,
        )

        try:
            self._precision = ScopeWidget(dm, config=scope_config)
            self._precision.showMaximized()
        except Exception as e:
            _print(traceback.format_exc())
            self.dm.stop_stream()
