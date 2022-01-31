from __future__ import annotations

import traceback
import random
from typing import NamedTuple

import PySide6.QtCore as qc
import PySide6.QtGui as qg
import PySide6.QtWidgets as qw
from PySide6.QtCore import Qt

from bomi.base_widgets import TaskDisplay, set_spinbox
from bomi.device_manager import YostDeviceManager
from bomi.scope_widget import ScopeConfig, ScopeWidget
from bomi.window_mixin import WindowMixin


def _print(*args):
    print("[Start React]", *args)


class SRState(NamedTuple):
    color: qg.QColor
    text: str
    duration: float = -1  # duration in seconds


class SRDisplay(TaskDisplay):
    """StartReact Display"""

    # States
    IDLE = SRState(color=Qt.lightGray, text="Get ready!")
    GO = SRState(color=Qt.green, text="Reach the target and hold!")
    WAIT = SRState(color=Qt.yellow, text="Wait...")
    TASK_DONE = SRState(color=Qt.lightGray, text="All done!")

    HOLD_TIME = 3000  # msec
    PAUSE_MIN = 2000
    PAUSE_RANDOM = 2000

    BTN_START_TXT = "Begin task"
    BTN_END_TXT = "End task"

    def __init__(self, task_name: str = ""):
        "task_name will be displayed at the top of the widget"
        super().__init__()

        ### Init UI
        main_layout = qw.QGridLayout()
        self.setLayout(main_layout)
        self.setAutoFillBackground(True)

        # Top label
        self.top_label = qw.QLabel(task_name)
        self.top_label.setFont(qg.QFont("Arial", 18))
        main_layout.addWidget(
            self.top_label, 0, 0, alignment=Qt.AlignTop | Qt.AlignLeft
        )

        # Center label
        self.center_label = qw.QLabel("Get ready!")
        self.center_label.setFont(qg.QFont("Arial", 24))
        main_layout.addWidget(self.center_label, 0, 0, alignment=Qt.AlignCenter)

        self.progress_bar = qw.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.setTextVisible(False)
        self.progress_animation = qc.QPropertyAnimation(self, b"pval")
        self.progress_animation.setDuration(self.HOLD_TIME)
        self.progress_animation.setStartValue(0)
        self.progress_animation.setEndValue(100)
        main_layout.addWidget(self.progress_bar, 5, 0)

        # Config + Controls
        gb = qw.QGroupBox("Task Config")
        form_layout = qw.QFormLayout()
        gb.setLayout(form_layout)
        self.n_trials = set_spinbox(qw.QSpinBox(), 5, 1, (1, 20))
        form_layout.addRow(qw.QLabel("No. Trials"), self.n_trials)
        main_layout.addWidget(gb, 6, 0, 1, 2)

        # Buttons
        self.start_stop_btn = qw.QPushButton(self.BTN_START_TXT)
        self.start_stop_btn.clicked.connect(self.toggle_start_stop)
        main_layout.addWidget(self.start_stop_btn, 7, 0, 1, 2)

        ### Task states
        self.n_trials_left = 0

        self.set_state(self.IDLE)

    @qc.Property(int)
    def pval(self):
        return self.progress_bar.value()

    @pval.setter
    def pval(self, val):
        self.progress_bar.setValue(val)

    def set_state(self, s: SRState):
        self.setPalette(s.color)
        if s == self.WAIT and self.n_trials_left:
            if self.n_trials_left == 1:
                txt = f" {self.n_trials_left} cycle left"
            else:
                txt = f" {self.n_trials_left} cycles left"
            self.center_label.setText(s.text + txt)
        else:
            self.center_label.setText(s.text)

    @classmethod
    def get_random_wait_time(cls):
        "Calculate random wait time"
        return cls.PAUSE_MIN + (cls.PAUSE_RANDOM) * random.random()

    def send_visual_signal(self):
        self.signal_task.emit("visual")
        self.set_state(self.GO)

    def send_visual_auditory_signal(self):
        "TODO: IMPLEMENT AUD"
        self.signal_task.emit("visual_auditory")
        self.set_state(self.GO)

    def send_visual_startling_signal(self):
        "TODO: IMPLEMENT AUD"
        self.signal_task.emit("visual_startling")
        self.set_state(self.GO)

    def one_trial(self):
        """Send a visual signal to the subject to begin doing the task
        If there are more cycles remaining, schedule one more
        """
        if self.n_trials_left <= 0:  # check if done
            return
        random.choice(
            (
                self.send_visual_signal,
                self.send_visual_auditory_signal,
                self.send_visual_startling_signal,
            )
        )()
        self.progress_animation.start()

        if self.n_trials_left > 1:  # check if schedule next trial
            qc.QTimer.singleShot(self.HOLD_TIME, self.end_one_trial)
            qc.QTimer.singleShot(
                self.HOLD_TIME + self.get_random_wait_time(), self.one_trial
            )
        else:
            qc.QTimer.singleShot(self.HOLD_TIME, self.end_task)

        self.n_trials_left -= 1

    def end_one_trial(self):
        """Execute clean up after a trial"""
        self.set_state(self.WAIT)

    def begin_task(self):
        """Begin the precision control task

        Begin sending random {visual, visual + auditory, visual + startling} to the subject per trial,
        each trial lasting 3 seconds.
        Wait a random amount of time before starting the next trial until we finish `n_trials_left`
        """
        self.start_stop_btn.setText(self.BTN_END_TXT)
        self.progress_bar.setValue(0)
        self.n_trials_left = self.n_trials.value()
        self.set_state(self.WAIT)
        qc.QTimer.singleShot(self.get_random_wait_time(), self.one_trial)

    def end_task(self):
        """Finish the task, reset widget to initial states"""
        self.start_stop_btn.setText(self.BTN_START_TXT)
        self.n_trials_left = 0
        self.progress_animation.stop()
        self.progress_bar.setValue(0)
        self.set_state(self.TASK_DONE)

    def toggle_start_stop(self):
        if self.start_stop_btn.text() == self.BTN_START_TXT:
            self.begin_task()

        else:
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

        btn1 = qw.QPushButton(text="MaxROM")
        btn1.clicked.connect(self.s_max_rom)
        main_layout.addWidget(btn1)

    def s_precision_task(self):
        "Run the ScopeWidget with the precision task view"
        if not self.dm.has_sensors():
            return self.no_sensors_error()

        scope_config = ScopeConfig(
            window_title="Precision",
            task_widget=SRDisplay("Precision Control"),
            show_scope_params=True,
            target_show=True,
            target_range=(45, 50),
            yrange=(0, 90),
            show_roll=False,
            show_pitch=False,
            show_yaw=False,
        )

        try:
            self._precision = ScopeWidget(self.dm, config=scope_config)
            self._precision.showMaximized()
        except Exception as e:
            _print(traceback.format_exc())
            self.dm.stop_stream()

    def s_max_rom(self):
        "Run the ScopeWidget with the MaxROM task view"
        if not self.dm.has_sensors():
            return self.no_sensors_error()

        scope_config = ScopeConfig(
            window_title="MaxROM",
            task_widget=SRDisplay("Max Range of Motion"),
            show_scope_params=True,
            target_show=True,
            target_range=(70, 120),
            yrange=(0, 110),
            show_roll=False,
            show_pitch=False,
            show_yaw=False,
        )

        try:
            self._precision = ScopeWidget(self.dm, config=scope_config)
            self._precision.showMaximized()
        except Exception as e:
            _print(traceback.format_exc())
            self.dm.stop_stream()
