from __future__ import annotations

from dataclasses import dataclass
from queue import Queue
from enum import Enum
from pathlib import Path
from timeit import default_timer
from typing import Dict, List, Tuple, Protocol

import pyqtgraph as pg
import pyqtgraph.parametertree as ptree
import PySide6.QtCore as qc
import PySide6.QtGui as qg
import PySide6.QtWidgets as qw
from pyqtgraph.parametertree.parameterTypes import ActionParameter
from pyqtgraph.parametertree.parameterTypes.basetypes import Parameter

from bomi.base_widgets import TaskEvent, TaskDisplay, generate_edit_form
from bomi.datastructure import YostBuffer, SubjectMetadata, Packet
from bomi.device_managers.protocols import SupportsStreaming, SupportsGetSensorMetadata
import bomi.colors as bcolors
from trigno_sdk.client import TrignoClient


def _print(*args):
    print("[ScopeWidget]", *args)


PENS = [pg.mkPen(clr, width=2) for clr in bcolors.COLORS]

TARGET_BRUSH_BG = pg.mkBrush(qg.QColor(25, 222, 193, 15))
TARGET_BRUSH_FG = pg.mkBrush(qg.QColor(254, 136, 33, 50))


@dataclass
class ScopeConfig:
    "Configuration parameters for ScopeWidget"
    window_title: str = "Scope"
    show_scope_params: bool = True

    target_show: bool = False
    target_range: Tuple[float, float] = (70, 80)

    base_show: bool = False
    base_range: Tuple[float, float] = (0, 5)

    xrange: Tuple[float, float] = (-6, 0)
    yrange: Tuple[float, float] = (-180, 180)

    autoscale_y: bool = False

    show_roll: bool = True
    show_pitch: bool = True
    show_yaw: bool = True
    show_rollpitch: bool = True


@dataclass
class PlotHandle:
    "Holds a PlotItem and its curves"
    plot: pg.PlotItem | pg.ViewBox
    curves: List[pg.PlotCurveItem | pg.PlotDataItem]
    target: pg.LinearRegionItem | None
    base: pg.LinearRegionItem | None

    TARGET_NAME = "Target"
    BASE_NAME = "Rest position"

    @classmethod
    def init(
        cls,
        plot: pg.PlotItem,
        target_range: Tuple[float, float] = None,
        base_range: Tuple[float, float] = None,
    ) -> PlotHandle:
        "Create curves on the given plot object"
        curves = [
            plot.plot(pen=pen, name=name) for pen, name in zip(PENS, YostBuffer.LABELS)
        ]

        target = (
            cls.init_line_region(plot, target_range, label=cls.TARGET_NAME)
            if target_range
            else None
        )

        base = (
            cls.init_line_region(plot, base_range, label=cls.BASE_NAME)
            if base_range
            else None
        )

        return PlotHandle(plot=plot, curves=curves, target=target, base=base)

    @classmethod
    def init_curve(cls, plot: pg.PlotItem, i: int):
        assert i < len(YostBuffer.LABELS)
        #YostBuffer holds data from one IMU sensor
        #TODO init QTM here
        return plot.plot(pen=PENS[i], name=YostBuffer.LABELS[i])

    @staticmethod
    def init_line_region(
        plot: pg.PlotItem,
        target_range: Tuple[float, float],
        label="Target",
        movable=False,
    ) -> pg.LinearRegionItem:
        "Create a Region on the plot (target or base)"
        region = pg.LinearRegionItem(
            values=target_range,
            orientation="horizontal",
            movable=movable,
            brush=TARGET_BRUSH_BG,
        )
        pg.InfLineLabel(region.lines[0], label, position=0.05, anchor=(1, 1), color="k")
        plot.addItem(region)
        return region

    ### [[[ Target methods
    def update_target(self, target_range: Tuple[float, float]):
        "Update the 'target' region's position"
        if self.target is None:
            self.target = self.init_line_region(
                self.plot, target_range, label=self.TARGET_NAME
            )
        else:
            self.target.lines[0].setValue(target_range[0])
            self.target.lines[1].setValue(target_range[1])

    def update_target_color(self, *args, **argv):
        if self.target:
            self.target.setBrush(*args, **argv)

    def clear_target(self):
        "Remove the 'target' line region"
        self.plot.removeItem(self.target)
        self.target = None

    ### Target methods]]]

    ### [[[ Base methods
    def update_base(self, base_range: Tuple[float, float]):
        "Update the 'base' region's position"
        if self.base is None:
            self.base = self.init_line_region(
                self.plot, base_range, label=self.BASE_NAME
            )
        else:
            self.base.lines[0].setValue(base_range[0])
            self.base.lines[1].setValue(base_range[1])

    def update_base_color(self, *args, **argv):
        if self.base:
            self.base.setBrush(*args, **argv)

    def clear_base(self):
        "Remove the 'base' line region"
        self.plot.removeItem(self.base)
        self.base = None

    ### Base methods]]]


class AngleState(Enum):
    OUTSIDE = 0
    IN_TARGET = 1
    IN_BASE = 2


class ScopeWidget(qw.QWidget):
    class ScopeWidgetDeviceManager(SupportsStreaming, SupportsGetSensorMetadata, Protocol):
        """
        The device manager of a scope widget must
        support streaming and support getting sensor metadata.
        """
        pass

    def __init__(
        self,
        dm: ScopeWidgetDeviceManager,
        savedir: Path,
        task_widget: TaskDisplay = None,
        config: ScopeConfig = ScopeConfig(),
        trigno_client: TrignoClient = None,
        #TODO, add init QTM stream
    ):
        super().__init__()
        self.setWindowTitle(config.window_title)
        self.dm = dm
        self.savedir = savedir
        self.task_widget = task_widget
        self.config = config
        if trigno_client and trigno_client.n_sensors:
            self.trigno_client = trigno_client
        else:
            self.trigno_client = None

        self.show_labels = list(YostBuffer.LABELS)
        self.queue: Queue[Packet] = Queue()
        #TODO add QTM

        self.dev_names: List[str] = []  # device name/nicknames
        self.dev_sn: List[str] = []  # device serial numbers (hex str)
        self.init_bufsize = 2500  # buffer size
        self.buffers: Dict[str, YostBuffer] = {}
        self.meta = SubjectMetadata()

        self.last_state: AngleState = (
            AngleState.OUTSIDE
        )  # keep track of last angle state

        def write_meta():
            print("write_meta", self.meta.dict())
            self.meta.to_disk(self.savedir)

        write_meta()
        self.meta_gb = generate_edit_form(
            self.meta, name="Edit Metadata", callback=write_meta
        )

        ### Parameter tree
        ptparams = [
            dict(name="streaming", title="Streaming", type="bool", value=True),
            ActionParameter(name="tare", title="Tare"),
            dict(
                name="target",
                title="Target",
                type="group",
                children=[
                    dict(
                        name="tshow",
                        title="Show",
                        type="bool",
                        value=config.target_show,
                    ),
                    dict(
                        name="tmax",
                        title="Max",
                        type="float",
                        value=config.target_range[1],
                    ),
                    dict(
                        name="tmin",
                        title="Min",
                        type="float",
                        value=config.target_range[0],
                    ),
                ],
            ),
            dict(
                name="base",
                title="Base",
                type="group",
                children=[
                    dict(
                        name="bshow",
                        title="Show",
                        type="bool",
                        value=config.base_show,
                    ),
                    dict(
                        name="bmax",
                        title="Max",
                        type="float",
                        value=config.base_range[1],
                    ),
                    dict(
                        name="bmin",
                        title="Min",
                        type="float",
                        value=config.base_range[0],
                    ),
                ],
            ),
            dict(
                name="show",
                title="Show",
                type="group",
                children=[
                    dict(
                        name="show_roll",
                        title="Show roll",
                        type="bool",
                        value=config.show_roll,
                    ),
                    dict(
                        name="show_pitch",
                        title="Show pitch",
                        type="bool",
                        value=config.show_pitch,
                    ),
                    dict(
                        name="show_yaw",
                        title="Show yaw",
                        type="bool",
                        value=config.show_yaw,
                    ),
                    dict(
                        name="show_rollpitch",
                        title="Show abs(roll) + abs(pitch)",
                        type="bool",
                        value=config.show_rollpitch,
                    ),
                ],
            ),
        ]

        self.params: ptree.Parameter = ptree.Parameter.create(
            name="Scope Controls",
            type="group",
            children=ptparams,
        )

        key2label = {  # map from config name to the corresponding Buffer.labels
            "show_roll": "Roll",
            "show_pitch": "Pitch",
            "show_yaw": "Yaw",
            "show_rollpitch": "abs(roll) + abs(pitch)",
        }

        def onShowHideChange(_, changes):
            for param, _, data in changes:
                name = param.name()
                if name in key2label:
                    name = key2label[name]
                    self.show_hide_curve(name, data)

        self.params.child("show").sigTreeStateChanged.connect(onShowHideChange)

        def toggle_stream(_, on: bool):
            self.start_stream() if on else self.stop_stream()

        self.params.child("streaming").sigValueChanged.connect(toggle_stream)

        def updateTarget(_, val):
            # for "tshow", val is bool, for ("tmax", "tmin"), probably a value, but doesn't matter
            if val:
                self.update_targets()
            else:
                self.clear_targets()

        self.params.child("target", "tshow").sigValueChanged.connect(updateTarget)
        self.params.child("target", "tmax").sigValueChanged.connect(updateTarget)
        self.params.child("target", "tmin").sigValueChanged.connect(updateTarget)

        def updateBase(_, val):
            if val:
                self.update_base()
            else:
                self.clear_base()

        self.params.child("base", "bshow").sigValueChanged.connect(updateBase)
        self.params.child("base", "bmax").sigValueChanged.connect(updateBase)
        self.params.child("base", "bmin").sigValueChanged.connect(updateBase)

        # keep references of these params for more efficient query
        self.param_tshow: Parameter = self.params.child("target", "tshow")
        self.param_tmax: Parameter = self.params.child("target", "tmax")
        self.param_tmin: Parameter = self.params.child("target", "tmin")
        self.target_range: Tuple[float, float] = (
            self.param_tmin.value(),
            self.param_tmax.value(),
        )

        self.param_bshow: Parameter = self.params.child("base", "bshow")
        self.param_bmax: Parameter = self.params.child("base", "bmax")
        self.param_bmin: Parameter = self.params.child("base", "bmin")
        self.base_range: Tuple[float, float] = (
            self.param_bmin.value(),
            self.param_bmax.value(),
        )

        def tare():
            with pg.BusyCursor():
                self.stop_stream()
                self.start_stream()

        self.params.child("tare").sigActivated.connect(tare)

        # init timer
        self.timer = qc.QTimer()
        self.timer.setInterval(0)
        self.timer.timeout.connect(self.update)  # type: ignore
        self.fps_counter = 0
        self.fps_last_time = default_timer()

    ### [[[ Targets methods
    def clear_targets(self):
        for name in self.dev_names:
            plot_handle = self.plot_handles[name]
            plot_handle.clear_target()

    def update_targets(self):
        "Handle updating target position (range)"
        if self.param_tshow.value():
            target_range = (
                self.param_tmin.value(),
                self.param_tmax.value(),
            )
            self.target_range = target_range

            if self.task_widget:
                self.task_widget.sigTargetMoved.emit(target_range)

            for name in self.dev_names:
                self.plot_handles[name].update_target(target_range)

    def update_target_color(self, *args, **kwargs):
        "Handle updating target color on plot"
        for name in self.dev_names:
            self.plot_handles[name].update_target_color(*args, **kwargs)

    ### Targets methods ]]]

    ### [[[ Base methods
    def clear_base(self):
        for name in self.dev_names:
            plot_handle = self.plot_handles[name]
            plot_handle.clear_base()

    def update_base(self):
        "Handle updating target position (range)"
        if self.param_bshow.value():
            self.base_range = base_range = (
                self.param_bmin.value(),
                self.param_bmax.value(),
            )

            if self.task_widget:
                self.task_widget.sigBaseMoved.emit(base_range)

            for name in self.dev_names:
                self.plot_handles[name].update_base(base_range)

    def update_base_color(self, *args, **kwargs):
        "Handle updating target color on plot"
        for name in self.dev_names:
            self.plot_handles[name].update_base_color(*args, **kwargs)

    ### Base methods ]]]

    def show_hide_curve(self, name: str, show: bool):  #TODO:
        i = YostBuffer.LABELS.index(name)
        if show and name not in self.show_labels:
            for dev in self.dev_names:
                handle = self.plot_handles[dev]
                handle.plot.addCurve(handle.curves[i])

            self.show_labels.append(name)

        if not show and name in self.show_labels:
            for dev in self.dev_names:
                handle = self.plot_handles[dev]
                handle.plot.removeItem(handle.curves[i])

            self.show_labels.remove(name)

    def showEvent(self, event: qg.QShowEvent) -> None:
        """Override showEvent to initialise data params and UI after the window is shown.
        This is because we need to know the number of sensors available to create the
        same number of plots
        """
        self.init_data()
        self.init_ui()
        return super().showEvent(event)

    def init_data(self): #TODO
        ### data
        while self.queue.qsize():
            self.queue.get()
        self.dev_names = self.dm.get_all_sensor_names()
        self.dev_sn = self.dm.get_all_sensor_serial()

        for dev in self.dev_names:
            if dev in self.buffers:  # buffer already initialized
                continue
            self.buffers[dev] = YostBuffer(
                bufsize=self.init_bufsize, savedir=self.savedir, name=dev
            )
            if self.task_widget:
                self.buffers[dev].set_angle_type(self.task_widget.config.angle_type)  # type: ignore

    def init_ui(self):
        ### Init UI
        main_layout = qw.QHBoxLayout()
        self.setLayout(main_layout)
        splitter = qw.QSplitter()
        main_layout.addWidget(splitter)

        self.glw = glw = pg.GraphicsLayoutWidget()
        self.glw.setBackground("white")
        splitter.addWidget(glw)

        row = 1

        ### Init Plots
        self.plot_handles: Dict[str, PlotHandle] = {}
        plot_style = {"color": "k"}  # label style
        for name, sn in zip(self.dev_names, self.dev_sn):
            plot: pg.PlotItem = glw.addPlot(row=row, col=0)
            row += 1
            plot.showAxis('right', show=True)
            plot.showGrid(y=True,alpha=0.15)
            plot.addLegend(offset=(1, 1), **plot_style)
            plot.setXRange(*self.config.xrange)
            plot.setYRange(*self.config.yrange)
            if self.config.autoscale_y:
                plot.enableAutoRange(axis="y")
            plot.setLabel("bottom", "Time", units="s", **plot_style)
            plot.setLabel("left", "Euler Angle", units="deg", **plot_style) #TODO: make yaxis variable
            plot.setDownsampling(mode="peak")
            title = f"{sn}" if name == sn else f"{sn} ({name})"
            plot.setTitle(title, **plot_style)
            self.plot_handles[name] = PlotHandle.init(plot)

        ### Init RHS of window
        RHS = qw.QWidget()
        layout = qw.QVBoxLayout()
        RHS.setLayout(layout)
        splitter.addWidget(RHS)

        # Create param tree
        pt = ptree.ParameterTree(showHeader=False)
        pt.setParameters(self.params)
        if self.config.show_scope_params:
            layout.addWidget(pt, 1)

        layout.addWidget(self.meta_gb)

        # Create task widget
        if self.task_widget is not None:
            layout.addWidget(self.task_widget, 1)

            def _trial_begin():
                self.flash(bcolors.LIGHT_BLUE)

            def _trial_end():
                self.flash(bcolors.GREEN)

            self.task_widget.sigTrialBegin.connect(_trial_begin)
            self.task_widget.sigTrialEnd.connect(_trial_end)
            self.task_widget.config.to_disk(self.savedir)  # type: ignore

        ### apply other config
        config = self.config
        config.target_show and self.update_targets()
        config.base_show and self.update_base()
        config.show_roll or self.show_hide_curve("Roll", False)
        config.show_pitch or self.show_hide_curve("Pitch", False)
        config.show_yaw or self.show_hide_curve("Yaw", False)
        config.show_rollpitch or self.show_hide_curve("abs(roll) + abs(pitch)", False)

        self.start_stream()

    def flash(self, color="green", duration_ms=500):
        self.glw.setBackground(color)
        qc.QTimer.singleShot(duration_ms, lambda: self.glw.setBackground("white"))

    def start_stream(self): #TODO
        """Start the stream and show in the scope
        Clear the queue and buffers
        """
        self.init_data()

        dummy_queue = _DummyQueue()
        if self.trigno_client:
            self.trigno_client.handle_stream(dummy_queue, self.savedir)
        self.dm.start_stream(self.queue)
        #start QTM stream
        self.timer.start()

    def stop_stream(self):
        """Stop the data stream and update timer"""
        self.dm.stop_stream()
        hasattr(self, "timer") and self.timer.stop()
        self.trigno_client and self.trigno_client.stop_stream()
        #stop QTM stream

    def update(self):
        """Update function connected to the timer
        1. Consume all data currently in the queue
        2. If successful, update all plots
        3. If applicable, update task states
        """
        self.fps_counter += 1
        if self.fps_counter > 2000:
            now = default_timer()
            interval = now - self.fps_last_time
            fps = self.fps_counter / interval
            self.fps_counter = 0
            self.fps_last_time = now
            _print("FPS: ", fps)

        q = self.queue
        qsize = q.qsize()
        # if not qsize:
        # return

        for _ in range(qsize):  # process current items in queue
            packet: Packet = q.get()
            self.buffers[packet.name].add_packet(packet)

        # On successful read from queue, update curves
        now = default_timer()
        for name in self.dev_names:
            buf = self.buffers[name]
            curves = self.plot_handles[name].curves

            x = -(now - buf.timestamp)
            for i, name in enumerate(buf.LABELS):
                if name in self.show_labels:
                    curves[i].setData(x=x, y=buf.data[:, i])

        ### Update task states if needed
        # 1. Check if angle is within target range
        # 2. Check if angle is within base range
        if self.task_widget:
            tmin, tmax = self.target_range
            bmin, bmax = self.base_range
            for name in self.dev_names:
                angle = self.buffers[name].last_angle

                if self.last_state == AngleState.IN_TARGET:
                    if not tmin <= angle <= tmax:
                        self.task_widget.sigTaskEventIn.emit(TaskEvent.EXIT_TARGET)
                        self.last_state = AngleState.OUTSIDE
                elif self.last_state == AngleState.IN_BASE:
                    if not bmin <= angle <= bmax:
                        self.task_widget.sigTaskEventIn.emit(TaskEvent.EXIT_BASE)
                        self.last_state = AngleState.OUTSIDE
                else:  # Outside base and target
                    if tmin <= angle <= tmax:
                        self.task_widget.sigTaskEventIn.emit(TaskEvent.ENTER_TARGET)
                        self.last_state = AngleState.IN_TARGET
                    elif bmin <= angle <= bmax:
                        self.task_widget.sigTaskEventIn.emit(TaskEvent.ENTER_BASE)
                        self.last_state = AngleState.IN_BASE

    def closeEvent(self, event: qg.QCloseEvent) -> None:
        with pg.BusyCursor():
            self.stop_stream()

        self.task_widget and self.task_widget.close()
        # Remove references to YostBuffer objects
        # The filepointers will be closed when GC runs
        self.buffers.clear()
        return super().closeEvent(event)


class _DummyQueue(Queue):
    def __init__(self):
        ...

    def put(self, _):
        ...

    def get(self) -> None:
        ...
