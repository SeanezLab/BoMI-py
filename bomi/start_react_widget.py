from __future__ import annotations
from dataclasses import dataclass, field, asdict

import json
import random
import traceback
from pathlib import Path
from timeit import default_timer
from typing import Callable, List, NamedTuple, Tuple, Protocol

import pyqtgraph as pg
import PySide6.QtCore as qc
import PySide6.QtGui as qg
import PySide6.QtWidgets as qw
from PySide6.QtCore import Qt
from PySide6.QtCore import Signal

from bomi.base_widgets import TaskDisplay, TaskEvent, generate_edit_form, wrap_gb
from bomi.datastructure import MultichannelBuffer, get_savedir
from bomi.device_managers.protocols import SupportsHasSensors, HasDiscoverDevicesSignal, SupportsGetChannelMetadata
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
TODO: Persist to disk
"""

@dataclass
class SRConfig:
    """
    Configuration for a StartReact task
    """
    HOLD_TIME: int = field(
        default=250, metadata=dict(range=(50, 5000), name="Hold Time (ms)")
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

    tone_duration: int = field(
        default=50, metadata=dict(range=(10, 500), name="Tone Duration (ms) ")
    )

    tone_frequency: int = field(
        default=500, metadata=dict(range=(1, 1000), name="Tone Frequency (Hz)")
    )
    auditory_volume: int = field(default=1, metadata=dict(range=(1, 100)))
    startle_volume: int = field(default=100, metadata=dict(range=(1, 100)))

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
    PREP = SRState(color=bcolors.CYAN, text="Prepare!")
    GO = SRState(color=bcolors.LIGHT_BLUE, text="Reach the target!")
    SUCCESS = SRState(color=bcolors.GREEN, text="Success! Return to rest.")
    WAIT = SRState(color=Qt.lightGray, text="Get ready!")
    TASK_DONE = SRState(color=Qt.lightGray, text="All done!")

    BTN_START_TXT = "Begin task"
    BTN_END_TXT = "End task"


    def __init__(self, task_name: str, savedir: Path, selected_channel: str, config: SRConfig, is_rest: bool):
        "task_name will be displayed at the top of the widget"
        super().__init__(selected_channel)
        self.config = config
        self.savedir = savedir

        # Bool used to determine task set up (rest vs. active task)
        self.is_rest = is_rest

        # filepointer to write task history
        self.task_history = open(savedir / "task_history.txt", "w")
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
        self.flex_timer = qc.QTimer()
        self.flex_timer.setSingleShot(True)
        self.flex_timer.timeout.connect(self.flex_timeout)  # type: ignore

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
        self.task_history.flush()

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
        
        # if not self.is_rest:
            # self.sigColorRegion.emit("target", True)
            # self.sigFlash.emit(None)

    @qc.Slot()  # type: ignore
    def one_trial_end(self):
        """Execute clean up after a trial
        If there are more cycles remaining, schedule one more
        """

        self.emit_end()
        self.set_state(self.SUCCESS)
        self.sigColorRegion.emit("target", False)
        self.sigColorRegion.emit("base", True)
        self.sigFlash.emit(None)

        if not self._trials_left:
            self.end_block()
    
    @qc.Slot() # type: ignore
    def flex_timeout(self):
        self.set_state(self.GO)

    def begin_block(self):
        """Begin a block of the precision control task

        Begin sending random {visual, visual + auditory, visual + startling} to the subject per trial,
        each trial lasting 3 seconds.
        Wait a random amount of time before starting the next trial until we finish all `_trials_left`
        """
        _print("Begin block")
        self.task_history.write(f"begin_block t={default_timer()}\n")
        self.task_history.flush()

        self.start_stop_btn.setText(self.BTN_END_TXT)
        self.progress_bar.setValue(0)

        self._trials_left = []
        self._trials_left += [self.send_visual_signal] * self.config.N_TRIALS
        self._trials_left += [self.send_visual_auditory_signal] * self.config.N_TRIALS
        self._trials_left += [self.send_visual_startling_signal] * self.config.N_TRIALS
        random.shuffle(self._trials_left)
        random.shuffle(self._trials_left)

        if self.is_rest:
            self.set_state(self.WAIT)
            # Rest trial begins in rest zone, so it's okay to start timer at start of trial
            self.timer_one_trial_begin.start(self.get_random_wait_time())
        else:
            self.set_state(self.PREP)
            self.sigColorRegion.emit("prep", True)
            self.sigFlash.emit(None)

    def end_block(self):
        """Finish the task, reset widget to initial states"""
        print("end_block", default_timer())
        self.task_history.write(f"end_block t={default_timer()}\n")
        self.task_history.flush()
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
        ### TaskEvent indicates what event has occured most recently
        """Receive task events from the ScopeWidget"""
        if self.is_rest:
            if event == TaskEvent.ENTER_TARGET:
                # start 3 sec timer
                if self.curr_state == self.GO and not self.timer_one_trial_end.isActive():
                    self.timer_one_trial_end.start(self.config.HOLD_TIME)
                    self.progress_animation.start()
                    self.sigFlash.emit(None)

            elif event == TaskEvent.EXIT_TARGET:
                # stop timer
                self.timer_one_trial_end.stop()
                self.progress_animation.stop()
                self.progress_bar.setValue(0)

            elif event == TaskEvent.ENTER_BASE and self.curr_state == self.SUCCESS:
                    self.set_state(self.WAIT)
                    self.sigColorRegion.emit("base", False)
                    self.sigFlash.emit(None)
                    if self._trials_left:
                        self.timer_one_trial_begin.start(self.get_random_wait_time())
                    
        else:
            if event == TaskEvent.ENTER_PREP and not self.curr_state == self.SUCCESS:
                if self._trials_left:
                    self.timer_one_trial_begin.start(self.get_random_wait_time())
                    self.progress_animation.start()
                    self.sigColorRegion.emit("base", False)
            
            elif event == TaskEvent.ENTER_TARGET and self.curr_state == self.GO:
                self.one_trial_end()
                self.sigColorRegion.emit("base", True)
                self.sigColorRegion.emit("target", False)
                self.sigColorRegion.emit("prep", False)
                self.sigFlash.emit(None)

            elif event == TaskEvent.ENTER_BASE and self.curr_state == self.SUCCESS:
                self.set_state(self.PREP)
                self.sigColorRegion.emit("prep", True)
                self.sigColorRegion.emit("base", False)
                self.sigFlash.emit(None)

    def emit_begin(self, event_name: str):
        self.sigTrialBegin.emit()
        print("emit_begin", default_timer())
        self.task_history.write(f"begin_{event_name} t={default_timer()}\n")
        self.task_history.flush()
        self._task_stack.append(event_name)

    def emit_end(self):
        """End the last begin signal"""
        if self._task_stack:
            self.sigTrialEnd.emit()
            self.task_history.write(
                f"end_{self._task_stack.pop()} t={default_timer()}\n"
            )
            self.task_history.flush()


class StartReactWidget(qw.QWidget, WindowMixin):
    """GUI to manage StartReact tasks"""
    class StartReactDeviceManager(
        ScopeWidget.ScopeWidgetDeviceManager,
        SupportsHasSensors,
        HasDiscoverDevicesSignal,
        Protocol
    ):
        """
        A device manager for the StartReact widget must
        be a valid ScopeWidgetDeviceManager,
        support checking if it has sensors,
        and support the discover_devices signal.
        """

    def __init__(self, device_managers: list[StartReactDeviceManager], trigno_client: TrignoClient):
        """
        @param device_managers A list of compatible device managers
        @param trigno_client A Trigno (EMG) client.
        """
        super().__init__()
        self.available_device_managers = device_managers
        self.dm = device_managers[0]
        self.selected_sensor_name = None
        self.selected_channel_name = self.dm.CHANNEL_LABELS[0]
        self.y_min, self.y_max = self.dm.get_channel_default_range(self.selected_channel_name)
        self.trigno_client = trigno_client

        self.config = SRConfig()

        ### Init UI
        main_layout = qw.QVBoxLayout(self)
        self.setLayout(main_layout)

        setup_layout = qw.QFormLayout()
        setup_group_box = qw.QGroupBox("Setup")
        setup_group_box.setLayout(setup_layout)
        main_layout.addWidget(setup_group_box)

        # Widget to select input to use
        input_button_group = qw.QButtonGroup(self)
        for i, dm in enumerate(self.available_device_managers):
            input_button_group.addButton(qw.QRadioButton(dm.INPUT_KIND), id=i)
        input_button_group.buttons()[0].click()  # Set the default choice as the first

        def update_selected_dm(dm_button):
            self.set_device_manager(
                self.available_device_managers[input_button_group.id(dm_button)]
            )
            self.fill_select_sensor_combo_box()
            self.fill_select_channel_combo_box()

        input_button_group.buttonClicked.connect(update_selected_dm)

        buttons_box = qw.QVBoxLayout()
        # We cannot add a group directly https://stackoverflow.com/a/69687211
        for button in input_button_group.buttons():
            buttons_box.addWidget(button)
        setup_layout.addRow(qw.QLabel("Input to use:"), buttons_box)

        # Select sensor UI
        self.select_sensor_combo_box = qw.QComboBox()
        setup_layout.addRow(qw.QLabel("Sensor to use:"), self.select_sensor_combo_box)
        self.fill_select_sensor_combo_box()
        self.dm.discover_devices_signal.connect(self.fill_select_sensor_combo_box)

        def update_selected_sensor(sensor):
            if sensor == "":
                # Ignore when the combo box is cleared
                return

            self.selected_sensor_name = sensor
            _print(f"Selected sensor changed to {sensor}")

        self.select_sensor_combo_box.currentTextChanged.connect(update_selected_sensor)

        # Select channel UI
        self.select_channel_combo_box = qw.QComboBox()
        setup_layout.addRow(qw.QLabel("Channel to use:"), self.select_channel_combo_box)
        self.fill_select_channel_combo_box()

        def update_selected_channel(channel):
            if channel == "":
                # ignore when the combo box is cleared
                return

            self.selected_channel_name = channel
            _print(f"Selected channel changed to {channel}")
            y_min, y_max = self.dm.get_channel_default_range(channel)
            self.y_min_box.setValue(y_min)
            self.y_max_box.setValue(y_max)

        self.select_channel_combo_box.currentTextChanged.connect(update_selected_channel)

        # Select range UI
        self.y_min_box = qw.QSpinBox()
        setup_layout.addRow(qw.QLabel("Y-min:"), self.y_min_box)
        self.y_min_box.setRange(-999, 999)
        self.y_min_box.setValue(self.y_min)

        def update_y_min(value):
            self.y_min = value
            _print(f"Y-min changed to {self.y_min}")

        self.y_min_box.valueChanged.connect(update_y_min)

        self.y_max_box = qw.QSpinBox()
        setup_layout.addRow(qw.QLabel("Y-max:"), self.y_max_box)
        self.y_max_box.setRange(-999, 999)
        self.y_max_box.setValue(self.y_max)

        def update_y_max(value):
            self.y_max = value
            _print(f"Y-max changed to {self.y_max}")

        self.y_max_box.valueChanged.connect(update_y_max)

        self.config_widget = generate_edit_form(
            self.config,
            name="Task config",
            dialog_box=True,
        )
        self.config_btn = qw.QPushButton("Set config...")
        self.config_btn.clicked.connect(self.config_widget.show)  # type: ignore
        setup_layout.addWidget(self.config_btn)

        self.audio_calib = AudioCalibrationWidget()
        main_layout.addWidget(wrap_gb("Audio calibration", self.audio_calib))

        actions_layout = qw.QVBoxLayout()
        main_layout.addLayout(actions_layout)

        btn1 = qw.QPushButton(text="Rest")
        btn1.clicked.connect(self.s_rest_task)  # type: ignore
        actions_layout.addWidget(btn1)

        btn1 = qw.QPushButton(text="Active")
        btn1.clicked.connect(self.s_active_task)  # type: ignore
        actions_layout.addWidget(btn1)

        self._scope_widget = None

    def fill_select_sensor_combo_box(self):
        sensor_names = self.dm.get_all_sensor_names()
        self.select_sensor_combo_box.clear()
        self.select_sensor_combo_box.addItems(
            sensor_names
        )

    def fill_select_channel_combo_box(self):
        channel_names = self.dm.CHANNEL_LABELS
        self.select_channel_combo_box.clear()
        self.select_channel_combo_box.addItems(
            channel_names
        )

    def set_device_manager(self, device_manager: StartReactDeviceManager) -> None:
        """
        Set the device manager to use for StartReact.
        """
        _print(f"Selected device manager: {device_manager}")
        self.dm = device_manager

    def check_sensors(self) -> bool: 
        if not self.dm.has_sensors():
            self.no_sensors_error(self.dm)
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

    def run_startreact(self, task_name: str, file_suffix: str, target_range: tuple[int, int], is_rest: bool):
        """
        Common code for the precision and max ROM tasks
        """
        if not self.check_sensors():
            return

        input_channels_visibility = {
            k: False
            for k in self.dm.CHANNEL_LABELS
        }
        input_channels_visibility[self.selected_channel_name] = True

        scope_config = ScopeConfig(
            input_channels_visibility=input_channels_visibility,
            window_title=task_name,
            show_scope_params=True,
            target_show=True,
            target_range=target_range,
            prepared_show= not is_rest,
            prepared_range=(-1, 1),
            base_show=True,
            yrange=(self.y_min, self.y_max),
        )

        savedir = get_savedir(file_suffix)  # savedir to write all data

        try:
            self._scope_widget = ScopeWidget(
                self.dm,
                selected_sensor_name=self.selected_sensor_name,
                savedir=savedir,
                task_widget=SRDisplay(task_name, savedir, self.selected_channel_name, self.config, is_rest=is_rest),
                config=scope_config,
                trigno_client=self.trigno_client,
            )
            self._scope_widget.showMaximized()
        except Exception:
            _print(traceback.format_exc())
            self.dm.stop_stream()

    def s_rest_task(self):
        """
        Run the ScopeWidget with the precision task view
        """

        self.run_startreact(
            "Rest Task",
            "Rest",
            (5, 15), #target range set for torque dorsiflexion
            is_rest=True
        )

    def s_active_task(self):
        """
        Run the ScopeWidget with the MaxROM task view
        """

        self.run_startreact(
            "Active Task",
            "Active",
            (5, 15), #target range set for torque dorsiflexion
            is_rest=False
        )
