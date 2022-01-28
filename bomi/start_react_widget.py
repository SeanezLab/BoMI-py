from __future__ import annotations
from enum import Enum
import traceback
import PySide6.QtGui as qg
import PySide6.QtWidgets as qw
import PySide6.QtCore as qc
from PySide6.QtCore import Qt
import pyqtgraph as pg
import numpy as np
from bomi.datastructure import StartReactEvent

from bomi.device_manager import YostDeviceManager
from bomi.scope_widget import ScopeConfig, ScopeWidget
from bomi.window_mixin import WindowMixin


def _print(*args):
    print("[Start React]", *args)


COLOR_IDLE = Qt.lightGray
COLOR_GO = Qt.green


class PrecisionDisplay(qw.QWidget):
    class States(Enum):
        STOPPED = 1
        RUNNING = 2

    def __init__(self):
        super().__init__()

        ### Init UI
        main_layout = qw.QGridLayout()
        self.setLayout(main_layout)

        self.label = qw.QLabel("Get ready!")
        self.label.setFont(qg.QFont("Arial", 18))
        main_layout.addWidget(self.label, 0, 0, alignment=Qt.AlignCenter)

        self.setAutoFillBackground(True)
        self.setPalette(COLOR_IDLE)

        self.start_stop_btn = qw.QPushButton("Start")
        self.start_stop_btn.clicked.connect(self.toggle_start_stop)
        main_layout.addWidget(self.start_stop_btn, 5, 0)

        ### Task states
        self.n_trials_left = 10

        self.timer = qc.QTimer()

    def flash(self):
        self.color_go()

        qc.QTimer.singleShot(100, self.color_idle)

    def color_go(self):
        self.setPalette(COLOR_GO)

    def color_idle(self):
        self.setPalette(COLOR_IDLE)

    def toggle_start_stop(self):
        if self.start_stop_btn.text() == "Start":
            self.start_stop_btn.setText("Stop")
            self.flash()
        else:
            self.start_stop_btn.setText("Start")


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

        tmp = PrecisionDisplay()
        main_layout.addWidget(tmp)

    def s_precision_task(self):
        dm = self.dm
        if not dm.has_sensors():
            return self.no_sensors_error()

        precision_config = ScopeConfig(
            window_title="Precision",
            task_widget=PrecisionDisplay(),
            target_show=True,
            yrange=(0, 120),
            show_roll=False,
            show_pitch=False,
            show_yaw=False,
        )

        try:
            self._precision = ScopeWidget(dm, config=precision_config)
            self._precision.showMaximized()
        except Exception as e:
            _print(traceback.format_exc())
            self.dm.stop_stream()
