from __future__ import annotations
from dataclasses import dataclass, field, asdict

import json
import random
import traceback
from pathlib import Path
from timeit import default_timer
from typing import Callable, List, NamedTuple, Tuple

import PySide6.QtCore as qc
import PySide6.QtGui as qg
import PySide6.QtWidgets as qw
from PySide6.QtCore import Qt

from bomi.base_widgets import TaskEvent, TaskDisplay, TaskEvent, generate_edit_form
from bomi.datastructure import YostBuffer, get_savedir
from bomi.device_managers.yost_manager import YostDeviceManager
from bomi.scope_widget import ScopeConfig, ScopeWidget
from bomi.window_mixin import WindowMixin
from bomi.audio.player import TonePlayer, AudioCalibrationWidget
import bomi.colors as bcolors

from trigno_sdk.client import TrignoClient


def _print(*args):
    print("[Start React]", *args)


class SRState(NamedTuple):
    color: qg.QColor | Qt.GlobalColor
    text: str  # Must be different for different states

    def __hash__(self):
        return hash(self.text)


"""
TODO: Move SRConfig to StartReact widget, out of SRDisplay
Persist to disk
"""


@dataclass
class SRConfig:
    """
    Configuration for a StartReact task
    """

    HOLD_TIME: int = field(
        default=500, metadata=dict(range=(500, 5000), name="Hold Time (ms)")
    )  # msec
    PAUSE_MIN: int = field(
        default=2000, metadata=dict(range=(500, 5000), name="Pause Min (ms)")
    )  # msec
    PAUSE_RANDOM: int = field(
        default=1000, metadata=dict(range=(0, 5000), name="Pause Random (ms)")
    )  # msec
    N_TRIALS: int = field(
        default=10, metadata=dict(range=(1, 40), name="No. Trials per cue")
    )

    tone_frequency: int = field(
        default=500, metadata=dict(range=(1, 1000), name="Tone Frequency (Hz)")
    )
    tone_duration: int = field(
        default=50, metadata=dict(range=(10, 500), name="Tone Duration (ms) ")
    )
    auditory_volume: int = field(default=1, metadata=dict(range=(1, 100)))
    startle_volume: int = field(default=100, metadata=dict(range=(1, 100)))

    angle_type: str = field(
        default=YostBuffer.LABELS[1], metadata=dict(options=YostBuffer.LABELS)
    )

    AXIS_MIN: int = field(
        default=0, metadata=dict(range=(-180, 180), name="Axis Range Min (deg.)")
    )

    AXIS_MAX: int = field(
        default=90, metadata=dict(range=(-180, 180), name="Axis Range Max (deg.)")
    )

    def to_disk(self, savedir: Path):
        "Write metadata to `savedir`"
        with (savedir / "start_react_config.json").open("w") as fp:
            json.dump(asdict(self), fp, indent=2)

class SRDisplay(TaskDisplay, WindowMixin):
    """StartReact Display

    This is the small block of display inserted into the ScopeWidget when
    running a StartReact task. Handles real-time StartReact events.
    """

    # States
    IDLE = SRState(color=Qt.lightGray, text="Get ready!")
    GO = SRState(color=bcolors.LIGHT_BLUE, text="Reach the target!")
    SUCCESS = SRState(color=bcolors.GREEN, text="Success! Return to rest position.")
    WAIT = SRState(color=Qt.lightGray, text="Get ready!")
    TASK_DONE = SRState(color=Qt.lightGray, text="All done!")

    BTN_START_TXT = "Begin task"
    BTN_END_TXT = "End task"

    def __init__(self, task_name: str, savedir: Path, config: SRConfig):
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
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_animation = qc.QPropertyAnimation(self, b"pval")
        self.progress_animation.setDuration(self.config.HOLD_TIME)
        self.progress_animation.setStartValue(0)
        self.progress_animation.setEndValue(100)
        main_layout.addWidget(self.progress_bar, 5, 0)

        # Buttons
        self.start_stop_btn = qw.QPushButton(self.BTN_START_TXT)
        self.start_stop_btn.clicked.connect(self.toggle_start_stop)  # type: ignore
        main_layout.addWidget(self.start_stop_btn, 7, 0, 1, 2)

        ### Task states
        self._trials_left: List[Callable[..., None]] = []
        self.curr_state = self.IDLE
        self.state_bg_timer = qc.QTimer()  # timer to reset widget background
        self.state_bg_timer.setSingleShot(True)
        self.state_bg_timer.timeout.connect(lambda: self.setPalette(Qt.lightGray))  # type: ignore
        self.state_bg_timer.setInterval(500)

        self.set_state(self.IDLE)

        # Connect task signals and slots
        self.sigTaskEventIn.connect(self.handle_input_event)
        self.sigTargetMoved.connect(self.on_target_moved)

        # Timers to start and end one trial
        self.timer_one_trial_begin = qc.QTimer()
        self.timer_one_trial_begin.setSingleShot(True)
        self.timer_one_trial_begin.timeout.connect(self.one_trial_begin)  # type: ignore
        self.timer_one_trial_end = qc.QTimer()
        self.timer_one_trial_end.setSingleShot(True)
        self.timer_one_trial_end.timeout.connect(self.one_trial_end)  # type: ignore

        def _init_tone(tone_player: TonePlayer):
            tone_player.effect.setVolume(0)  # not sure why still hear this
            tone_player.play()

        # tone sound
        self.auditory_tone = TonePlayer(
            self.config.tone_frequency, self.config.tone_duration
        )
        _init_tone(self.auditory_tone)
        self.startle_tone = TonePlayer(
            self.config.tone_frequency, self.config.tone_duration
        )
        _init_tone(self.startle_tone)

        self.auditory_tone.effect.setVolume(self.config.auditory_volume / 100)
        self.startle_tone.effect.setVolume(self.config.startle_volume / 100)

    def closeEvent(self, event: qg.QCloseEvent) -> None:
        self.timer_one_trial_begin.stop()
        self.timer_one_trial_end.stop()
        self.state_bg_timer.stop()
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
        self.state_bg_timer.start()
        self.setPalette(s.color)
        self.center_label.setText(s.text)

    def get_random_wait_time(self) -> int:
        "Calculate random wait time in msec"
        return int(self.config.PAUSE_MIN + (self.config.PAUSE_RANDOM) * random.random())

    def send_visual_signal(self):
        self.emit_begin("visual")
        self.set_state(self.GO)

    def send_visual_auditory_signal(self):
        # self.auditory_tone.effect.setVolume(self.config.auditory_volume/100)
        self.auditory_tone.play()
        self.emit_begin("visual_auditory")
        self.set_state(self.GO)

    def send_visual_startling_signal(self):
        # self.startle_tone.effect.setVolume(self.config.startle_volume/100)
        self.startle_tone.play()
        self.emit_begin("visual_startling")
        self.set_state(self.GO)

    @qc.Slot()  # type: ignore
    def one_trial_begin(self):
        """Begin one trial
        Give user the signal to reach the target, and wait until the target
        is reached and held for an amount of time.

        Send a signal to the subject to begin doing the task
        Schedule the end of the trial
        """
        if self._trials_left:  # check if done
            self._trials_left.pop()()

    @qc.Slot()  # type: ignore
    def one_trial_end(self):
        """Execute clean up after a trial
        If there are more cycles remaining, schedule one more
        """
        self.emit_end()
        self.set_state(self.SUCCESS)
        if not self._trials_left:
            self.end_block()

    def begin_block(self):
        """Begin a block of the precision control task

        Begin sending random {visual, visual + auditory, visual + startling} to the subject per trial,
        each trial lasting 3 seconds.
        Wait a random amount of time before starting the next trial until we finish all `_trials_left`
        """
        _print("Begin block")
        self.task_history.write(f"begin_block t={default_timer()}\n")
        self.start_stop_btn.setText(self.BTN_END_TXT)
        self.progress_bar.setValue(0)

        self._trials_left = []
        self._trials_left += [self.send_visual_signal] * self.config.N_TRIALS
        self._trials_left += [self.send_visual_auditory_signal] * self.config.N_TRIALS
        self._trials_left += [self.send_visual_startling_signal] * self.config.N_TRIALS
        random.shuffle(self._trials_left)
        random.shuffle(self._trials_left)

        self.set_state(self.WAIT)
        self.timer_one_trial_begin.start(self.get_random_wait_time())

    def end_block(self):
        """Finish the task, reset widget to initial states"""
        self.task_history.write(f"end_block t={default_timer()}\n")
        self._task_stack.clear()

        self.start_stop_btn.setText(self.BTN_START_TXT)
        self._trials_left = []
        self.progress_animation.stop()
        self.progress_bar.setValue(0)
        self.set_state(self.TASK_DONE)

    def toggle_start_stop(self):
        if self.start_stop_btn.text() == self.BTN_START_TXT:
            self.begin_block()
        else:
            self.end_block()

    @qc.Slot(TaskEvent)  # type: ignore
    def handle_input_event(self, event: TaskEvent):
        """Receive task events from the ScopeWidget"""
        if event == TaskEvent.ENTER_TARGET:
            # start 3 sec timer
            if self.curr_state == self.GO and not self.timer_one_trial_end.isActive():
                self.timer_one_trial_end.start(self.config.HOLD_TIME)
                self.progress_animation.start()
            # _print("Enter target")

        elif event == TaskEvent.EXIT_TARGET:
            # stop timer
            self.timer_one_trial_end.stop()
            self.progress_animation.stop()
            self.progress_bar.setValue(0)
            # _print("Exit target")

        elif event == TaskEvent.ENTER_BASE:
            if self.curr_state == self.SUCCESS:
                self.set_state(self.WAIT)
                if self._trials_left:
                    self.timer_one_trial_begin.start(self.get_random_wait_time())
            # _print("Enter base")

        # elif event == TaskEvent.EXIT_BASE:
        # _print("Exit base")

    def emit_begin(self, event_name: str):
        self.sigTrialBegin.emit()
        self.task_history.write(f"begin_{event_name} t={default_timer()}\n")
        self._task_stack.append(event_name)

    def emit_end(self):
        """End the last begin signal"""
        if self._task_stack:
            self.sigTrialEnd.emit()
            self.task_history.write(
                f"end_{self._task_stack.pop()} t={default_timer()}\n"
            )


class StartReactWidget(qw.QWidget, WindowMixin):
    """GUI to manage StartReact tasks"""

    def __init__(self, device_manager: YostDeviceManager, trigno_client: TrignoClient):
        super().__init__()
        self.dm = device_manager
        self.trigno_client = trigno_client

        self.config = SRConfig()

        ### Init UI
        main_layout = qw.QVBoxLayout(self)

        btn1 = qw.QPushButton(text="Precision")
        btn1.clicked.connect(self.s_precision_task)  # type: ignore
        main_layout.addWidget(btn1)

        btn1 = qw.QPushButton(text="MaxROM")
        btn1.clicked.connect(self.s_max_rom)  # type: ignore
        main_layout.addWidget(btn1)

        self.config_widget = generate_edit_form(
            self.config,
            name="Task config",
            dialog_box=True,
        )
        self.config_btn = qw.QPushButton("Configure")
        self.config_btn.clicked.connect(self.config_widget.show)  # type: ignore
        main_layout.addWidget(self.config_btn)

        self.audio_calib = AudioCalibrationWidget()
        main_layout.addWidget(self.audio_calib)

    def check_sensors(self) -> bool:
        if not self.dm.has_sensors():
            self.no_yost_sensors_error()
            return False

        if not self.trigno_client.connected:
            return self.msg_dialog(
                "Trigno Client not connected to Base Station. Continue StartReact without EMG recording?"
            )

        if not self.trigno_client.n_sensors:
            return self.msg_dialog(
                "Trigno Client didn't find any sensors. Continue StartReact without EMG recording?"
            )

        return True

    def s_precision_task(self):
        "Run the ScopeWidget with the precision task view"
        if not self.check_sensors():
            return

        # refer to YostBuffer.LABELS for these
        show_roll = self.config.angle_type == "Roll"
        show_pitch = self.config.angle_type == "Pitch"
        show_yaw = self.config.angle_type == "Yaw"
        show_rollpitch = self.config.angle_type == "abs(roll) + abs(pitch)"
        assert (
            sum([show_roll, show_pitch, show_yaw, show_rollpitch]) == 1
        ), f"SRConfig: Unknown angle_type: {self.config.angle_type}"

        scope_config = ScopeConfig(
            window_title="Precision",
            show_scope_params=True,
            target_show=True,
            target_range=(35, 40),
            base_show=True,
            yrange=(self.config.AXIS_MIN, self.config.AXIS_MAX),
            show_roll=show_roll,
            show_pitch=show_pitch,
            show_yaw=show_yaw,
            show_rollpitch=show_rollpitch,
        )

        savedir = get_savedir("Precision")  # savedir to write all data

        try:
            self._precision = ScopeWidget(
                self.dm,
                savedir=savedir,
                task_widget=SRDisplay("Precision Control", savedir, self.config),
                config=scope_config,
                trigno_client=self.trigno_client,
            )

            self._precision.showMaximized()
        except Exception:
            _print(traceback.format_exc())
            self.dm.stop_stream()

    def s_max_rom(self):
        "Run the ScopeWidget with the MaxROM task view"
        if not self.check_sensors():
            return

        # refer to YostBuffer.LABELS for these
        show_roll = self.config.angle_type == "Roll"
        show_pitch = self.config.angle_type == "Pitch"
        show_yaw = self.config.angle_type == "Yaw"
        show_rollpitch = self.config.angle_type == "abs(roll) + abs(pitch)"
        assert (
            sum([show_roll, show_pitch, show_yaw, show_rollpitch]) == 1
        ), f"SRConfig: Unknown angle_type: {self.config.angle_type}"

        scope_config = ScopeConfig(
            window_title="MaxROM",
            show_scope_params=True,
            target_show=True,
            target_range=(70,120),
            base_show=True,
            yrange=(self.config.AXIS_MIN, self.config.AXIS_MAX), 
            show_roll=show_roll,
            show_pitch=show_pitch,
            show_yaw=show_yaw,
            show_rollpitch=show_rollpitch,
        )

        savedir = get_savedir("MaxROM")  # savedir to write all data

        try:
            self._precision = ScopeWidget(
                self.dm,
                savedir=savedir,
                task_widget=SRDisplay("Max Range of Motion", savedir, self.config),
                config=scope_config,
                trigno_client=self.trigno_client,
            )
            self._precision.showMaximized()
        except Exception:
            _print(traceback.format_exc())
            self.dm.stop_stream()
