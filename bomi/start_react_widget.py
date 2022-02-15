from __future__ import annotations
from dataclasses import dataclass, field, asdict

import json
import random
import traceback
from pathlib import Path
from timeit import default_timer
from typing import List, NamedTuple, Tuple

import PySide6.QtCore as qc
import PySide6.QtGui as qg
import PySide6.QtWidgets as qw
from PySide6.QtCore import Qt
import winsound

from bomi.base_widgets import TEvent, TaskDisplay, set_spinbox, generate_edit_form
from bomi.datastructure import get_savedir
from bomi.device_manager import YostDeviceManager
from bomi.scope_widget import ScopeConfig, ScopeWidget
from bomi.window_mixin import WindowMixin


def _print(*args):
    print("[Start React]", *args)


class SRState(NamedTuple):
    color: qg.QColor
    text: str
    duration: float = -1  # duration in seconds


@dataclass
class SRConfig:
    HOLD_TIME: int = field(default=500, metadata=dict(range=(500, 5000)))  # msec
    PAUSE_MIN: int = field(default=2000, metadata=dict(range=(500, 5000)))  # msec
    PAUSE_RANDOM: int = field(default=0000, metadata=dict(range=(0, 5000)))  # msec
    N_TRIALS: int = field(default=10, metadata=dict(range=(1, 40)))

    def to_disk(self, savedir: Path):
        "Write metadata to `savedir`"
        with (savedir / "start_react_config.json").open("w") as fp:
            json.dump(asdict(self), fp)


class _SoundWorker(qc.QObject):
    def play_sound(self, val: int):
        print("Play sound", val)
        winsound.Beep(500, 200)
        with open("test.txt", "w+") as fp:
            fp.write(f"wtf {val}")



class SRDisplay(TaskDisplay, WindowMixin):
    """StartReact Display"""

    # Take param (dB: int)
    sigPlaySound: qc.SignalInstance = qc.Signal(int) # type: ignore

    # States
    IDLE = SRState(color=Qt.lightGray, text="Get ready!")
    GO = SRState(color=Qt.green, text="Reach the target and hold!")
    WAIT = SRState(color=qg.QColor(254, 219, 65), text="Wait...")
    TASK_DONE = SRState(color=Qt.lightGray, text="All done!")

    BTN_START_TXT = "Begin task"
    BTN_END_TXT = "End task"

    def __init__(self, task_name: str, savedir: Path, config: SRConfig = SRConfig()):
        "task_name will be displayed at the top of the widget"
        super().__init__()
        self.config = config
        self.savedir = savedir

        # filepointer to write task history
        self.task_history = open(savedir / f"task_history.txt", "w")
        self._task_stack: List[str] = []

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
        self.progress_animation.setDuration(self.config.HOLD_TIME)
        self.progress_animation.setStartValue(0)
        self.progress_animation.setEndValue(100)
        main_layout.addWidget(self.progress_bar, 5, 0)

        # Config + Controls
        self.config_widget = generate_edit_form(
            self.config,
            name="Task config",
            dialog_box=True,
            callback=lambda: self.config.to_disk(savedir),
        )

        gb = qw.QGroupBox("Task Config")
        form_layout = qw.QFormLayout()
        gb.setLayout(form_layout)
        self.n_trials = set_spinbox(qw.QSpinBox(), self.config.N_TRIALS, 1, (1, 20))
        form_layout.addRow(qw.QLabel("No. Trials"), self.n_trials)

        btn = qw.QPushButton("Config")
        btn.clicked.connect(lambda: self.start_widget(self.config_widget))  # type: ignore
        form_layout.addWidget(btn)
        main_layout.addWidget(gb, 6, 0, 1, 2)

        # Buttons
        self.start_stop_btn = qw.QPushButton(self.BTN_START_TXT)
        self.start_stop_btn.clicked.connect(self.toggle_start_stop)  # type: ignore
        main_layout.addWidget(self.start_stop_btn, 7, 0, 1, 2)

        ### Task states
        self.n_trials_left = 0
        self.curr_state = self.IDLE

        self.set_state(self.IDLE)

        # Connect task signals and slots
        self.sigTaskEventIn.connect(self.handle_input_event)
        self.sigTargetMoved.connect(self.on_target_moved)

        # Timers to start and end one trial
        self.timer_one = qc.QTimer()
        self.timer_one.setSingleShot(True)
        self.timer_one.timeout.connect(self.one_trial)  # type: ignore
        self.timer_end_one = qc.QTimer()
        self.timer_end_one.setSingleShot(True)
        self.timer_end_one.timeout.connect(self.end_one_trial)  # type: ignore

        # Thread to play sound
        self.sound_thread = qc.QThread()
        self.sound_worker = _SoundWorker()
        self.sound_worker.moveToThread(self.sound_thread)
        self.sigPlaySound.connect(self.sound_worker.play_sound)
        self.sound_thread.start()

    def closeEvent(self, event: qg.QCloseEvent) -> None:
        self.sound_thread.quit()
        self.sound_thread.wait()
        self.task_history.close()
        return super().closeEvent(event)

    def on_target_moved(self, trange: Tuple[int, int]):
        self.task_history.write(
            f"target_moved t={default_timer()} tmin={trange[0]} tmax={trange[1]}\n"
        )


    @qc.Property(int)  # type: ignore
    def pval(self):  # type: ignore
        return self.progress_bar.value()

    @pval.setter
    def pval(self, val):
        self.progress_bar.setValue(val)

    def set_state(self, s: SRState):
        self.curr_state = s
        self.setPalette(s.color)
        if s == self.WAIT and self.n_trials_left:
            if self.n_trials_left == 1:
                txt = f" {self.n_trials_left} cycle left"
            else:
                txt = f" {self.n_trials_left} cycles left"
            self.center_label.setText(s.text + txt)
        else:
            self.center_label.setText(s.text)

    def get_random_wait_time(self) -> int:
        "Calculate random wait time in msec"
        return int(self.config.PAUSE_MIN + (self.config.PAUSE_RANDOM) * random.random())

    def send_visual_signal(self):
        self.emit_begin("visual")
        self.set_state(self.GO)

    def send_visual_auditory_signal(self):
        "TODO: IMPLEMENT AUD"
        self.sigPlaySound.emit(100)
        self.emit_begin("visual_auditory")
        self.set_state(self.GO)

    def send_visual_startling_signal(self):
        "TODO: IMPLEMENT AUD"
        self.sigPlaySound.emit(100)
        self.emit_begin("visual_startling")
        self.set_state(self.GO)

    def one_trial(self):
        """Begin one trial
        Give user the signal to reach the target, and wait until the target
        is reached and held for an amount of time.

        Send a signal to the subject to begin doing the task
        Schedule the end of the trial
        """
        if self.n_trials_left > 0:  # check if done
            self.n_trials_left -= 1
            task = random.choice(
                (
                    self.send_visual_signal,
                    self.send_visual_auditory_signal,
                    self.send_visual_startling_signal,
                )
            )
            task()

    def end_one_trial(self):
        """Execute clean up after a trial
        If there are more cycles remaining, schedule one more
        """
        self.emit_end()
        self.set_state(self.WAIT)
        if self.n_trials_left > 0:
            qc.QTimer.singleShot(self.get_random_wait_time(), self.one_trial)
        else:
            self.end_block()

    def begin_block(self):
        """Begin a block of the precision control task

        Begin sending random {visual, visual + auditory, visual + startling} to the subject per trial,
        each trial lasting 3 seconds.
        Wait a random amount of time before starting the next trial until we finish `n_trials_left`
        """
        self.task_history.write(f"begin_block t={default_timer()}\n")
        self.start_stop_btn.setText(self.BTN_END_TXT)
        self.progress_bar.setValue(0)
        self.n_trials_left = self.n_trials.value()
        self.set_state(self.WAIT)
        self.timer_one.start(self.get_random_wait_time())

    def end_block(self):
        """Finish the task, reset widget to initial states"""
        self.task_history.write(f"end_block t={default_timer()}\n")
        self._task_stack.clear()

        self.start_stop_btn.setText(self.BTN_START_TXT)
        self.n_trials_left = 0
        self.progress_animation.stop()
        self.progress_bar.setValue(0)
        self.set_state(self.TASK_DONE)

    def toggle_start_stop(self):
        if self.start_stop_btn.text() == self.BTN_START_TXT:
            self.begin_block()
        else:
            self.end_block()

    @qc.Slot(TEvent)  # type: ignore
    def handle_input_event(self, event: TEvent):
        if event == TEvent.ENTER_TARGET:
            # start 3 sec timer
            if self.curr_state == self.GO and not self.timer_end_one.isActive():
                self.timer_end_one.start(self.config.HOLD_TIME)
                self.progress_animation.start()

        elif event == TEvent.EXIT_TARGET:
            # stop timer
            self.timer_end_one.stop()
            self.progress_animation.stop()
            self.progress_bar.setValue(0)
        else:
            _print("handle_input_event: Unknown event:", event)

    def emit_begin(self, event_name: str):
        self.sigTrialBegin.emit()
        self.task_history.write(f"begin_{event_name} t={default_timer()}\n")
        self._task_stack.append(event_name)

    def emit_end(self):
        """End the last begin signal"""
        if self._task_stack:
            self.sigTrialEnd.emit()
            self.task_history.write(f"begin_{self._task_stack.pop()} t={default_timer()}\n")


class StartReactWidget(qw.QWidget, WindowMixin):
    """GUI to manage StartReact tasks"""

    def __init__(self, device_manager: YostDeviceManager):
        super().__init__()
        self.dm = device_manager

        ### Init UI
        main_layout = qw.QVBoxLayout()
        self.setLayout(main_layout)

        btn1 = qw.QPushButton(text="Precision")
        btn1.clicked.connect(self.s_precision_task)  # type: ignore
        main_layout.addWidget(btn1)

        btn1 = qw.QPushButton(text="MaxROM")
        btn1.clicked.connect(self.s_max_rom)  # type: ignore
        main_layout.addWidget(btn1)

        btn = qw.QPushButton(text="Test audio")
        btn.clicked.connect(self.s_test_audio)  # type: ignore
        main_layout.addWidget(btn)

    def s_test_audio(self):
        winsound.Beep(500, 5000)

    def s_precision_task(self):
        "Run the ScopeWidget with the precision task view"
        if not self.dm.has_sensors():
            return self.no_sensors_error()

        scope_config = ScopeConfig(
            window_title="Precision",
            show_scope_params=True,
            target_show=True,
            target_range=(35, 40),
            yrange=(0, 90),
            show_roll=False,
            show_pitch=False,
            show_yaw=False,
        )

        savedir = get_savedir("Precision")  # savedir to write all data

        try:
            self._precision = ScopeWidget(
                self.dm,
                savedir=savedir,
                task_widget=SRDisplay("Precision Control", savedir),
                config=scope_config,
            )

            self._precision.showMaximized()
        except Exception:
            _print(traceback.format_exc())
            self.dm.stop_stream()

    def s_max_rom(self):
        "Run the ScopeWidget with the MaxROM task view"
        if not self.dm.has_sensors():
            return self.no_sensors_error()

        scope_config = ScopeConfig(
            window_title="MaxROM",
            show_scope_params=True,
            target_show=True,
            target_range=(70, 120),
            yrange=(0, 110),
            show_roll=False,
            show_pitch=False,
            show_yaw=False,
        )

        savedir = get_savedir("MaxROM")  # savedir to write all data

        try:
            self._precision = ScopeWidget(
                self.dm,
                savedir=savedir,
                task_widget=SRDisplay("Max Range of Motion", savedir=savedir),
                config=scope_config,
            )
            self._precision.showMaximized()
        except Exception:
            _print(traceback.format_exc())
            self.dm.stop_stream()
