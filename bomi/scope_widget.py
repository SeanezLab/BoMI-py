from __future__ import annotations

from dataclasses import dataclass
from collections import deque
from pathlib import Path
from timeit import default_timer
from typing import Dict, List, Tuple, Deque

import pyqtgraph as pg
import pyqtgraph.parametertree as ptree
import PySide6.QtCore as qc
import PySide6.QtGui as qg
import PySide6.QtWidgets as qw
from pyqtgraph.parametertree.parameterTypes import ActionParameter
from pyqtgraph.parametertree.parameterTypes.basetypes import Parameter

from bomi.base_widgets import TEvent, TaskDisplay, generate_edit_form
from bomi.datastructure import YostBuffer, SubjectMetadata, Packet
from bomi.device_managers import YostDeviceManager
from trigno_sdk.client import TrignoClient


def _print(*args):
    print("[ScopeWidget]", *args)


# Seanez lab colors
COLORS = [
    qg.QColor(253, 0, 58),  # red
    qg.QColor(25, 222, 193),  # green/cyan
    qg.QColor(19, 10, 241),  # dark blue
    qg.QColor(254, 136, 33),  # orange
    qg.QColor(177, 57, 255),  # purple
]


PENS = [pg.mkPen(clr, width=2) for clr in COLORS]

TARGET_BRUSH_BG = pg.mkBrush(qg.QColor(25, 222, 193, 15))
TARGET_BRUSH_FG = pg.mkBrush(qg.QColor(254, 136, 33, 50))


@dataclass
class ScopeConfig:
    "Configuration parameters for ScopeWidget"
    window_title: str = "Scope"
    show_scope_params: bool = True

    target_show: bool = False
    target_range: Tuple[float, float] = (70, 80)

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
    curves: List[pg.PlotCurveItem]
    target: pg.LinearRegionItem | None
    rest_target: pg.LinearRegionItem | None

    @classmethod
    def init(
        cls, plot: pg.PlotItem, target_range: Tuple[float, float] = None
    ) -> PlotHandle:
        "Create curves on the given plot object"
        # init curves
        curves = []
        for pen, name in zip(PENS, YostBuffer.LABELS):
            curves.append(plot.plot(pen=pen, name=name))

        target = cls.init_target(plot, target_range) if target_range else None
        rest_target = cls.init_target(plot, (0, 5), label="Rest position", movable=True)
        # TODO: implement logging of this position

        return PlotHandle(
            plot=plot, curves=curves, target=target, rest_target=rest_target
        )

    @classmethod
    def init_curve(cls, plot: pg.PlotItem, i: int):
        assert i < len(YostBuffer.LABELS)
        return plot.plot(pen=PENS[i], name=YostBuffer.LABELS[i])

    @staticmethod
    def init_target(
        plot: pg.PlotItem,
        target_range: Tuple[float, float],
        label="Target",
        movable=False,
    ) -> pg.LinearRegionItem:
        # Target region
        target = pg.LinearRegionItem(
            values=target_range,
            orientation="horizontal",
            movable=movable,
            brush=TARGET_BRUSH_BG,
        )
        pg.InfLineLabel(target.lines[0], label, position=0.05, anchor=(1, 1), color="k")
        plot.addItem(target)
        return target

    def update_target(self, target_range: Tuple[float, float]):
        if self.target is None:
            self.target = self.init_target(self.plot, target_range)
        self.target.lines[0].setValue(target_range[0])
        self.target.lines[1].setValue(target_range[1])

    def update_target_color(self, *args, **argv):
        if self.target:
            self.target.setBrush(*args, **argv)

    def clear_target(self):
        self.plot.removeItem(self.target)
        self.target = None


class ScopeWidget(qw.QWidget):
    def __init__(
        self,
        dm: YostDeviceManager,
        savedir: Path,
        task_widget: TaskDisplay = None,
        config: ScopeConfig = ScopeConfig(),
        trigno_client: TrignoClient = None,
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
        self.queue: Deque[Packet] = deque()

        self.dev_names: List[str] = []  # device name/nicknames
        self.dev_sn: List[str] = []  # device serial numbers (hex str)
        self.init_bufsize = 2500  # buffer size
        self.buffers: Dict[str, YostBuffer] = {}
        self.meta = SubjectMetadata()

        def write_meta():
            print("write_meta", self.meta.dict())
            self.meta.to_disk(self.savedir)

        write_meta()
        self.meta_gb = generate_edit_form(
            self.meta, name="Edit Metadata", callback=write_meta
        )

        ### Parameter tree
        self.params: ptree.Parameter = ptree.Parameter.create(
            name="Scope Controls",
            type="group",
            children=[
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
            ],
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

        def updateTarget(_, val):
            # for "tshow", val is bool, for ("tmax", "tmin"), probably a value, but doesn't matter
            if val:
                self.update_targets()
            else:
                self.clear_targets()

        def toggle_stream(_, on: bool):
            self.start_stream() if on else self.stop_stream()

        self.params.child("streaming").sigValueChanged.connect(toggle_stream)
        self.params.child("target", "tshow").sigValueChanged.connect(updateTarget)
        self.params.child("target", "tmax").sigValueChanged.connect(updateTarget)
        self.params.child("target", "tmin").sigValueChanged.connect(updateTarget)
        self.params.child("show").sigTreeStateChanged.connect(onShowHideChange)

        # keep references of these params for more efficient query
        self.param_tshow: Parameter = self.params.child("target", "tshow")
        self.param_tmax: Parameter = self.params.child("target", "tmax")
        self.param_tmin: Parameter = self.params.child("target", "tmin")
        self.target_changed: bool = True
        self.target_range: Tuple[float, float] = self.get_target_range()

        def tare():
            with pg.BusyCursor():
                self.stop_stream()
                self.start_stream()

        self.params.child("tare").sigActivated.connect(tare)

        # init timer
        self.timer = qc.QTimer()
        self.timer.setInterval(1)
        self.timer.timeout.connect(self.update)  # type: ignore
        self.fps_counter = 0
        self.fps_last_time = default_timer()

    def show_hide_curve(self, name: str, show: bool):
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

    def clear_targets(self):
        for name in self.dev_names:
            plot_handle = self.plot_handles[name]
            plot_handle.clear_target()

    def update_targets(self):
        if self.get_target_show():
            target_range = self.get_target_range()
            self.target_range = target_range

            if self.task_widget:
                self.task_widget.sigTargetMoved.emit(target_range)

            for name in self.dev_names:
                self.plot_handles[name].update_target(target_range)

    def update_target_color(self, *args, **kwargs):
        for name in self.dev_names:
            self.plot_handles[name].update_target_color(*args, **kwargs)

    def get_target_show(self) -> bool:
        return self.param_tshow.value()

    def get_target_range(self) -> Tuple[float, float]:
        return (
            self.param_tmin.value(),
            self.param_tmax.value(),
        )

    def showEvent(self, event: qg.QShowEvent) -> None:
        """Override showEvent to initialise data params and UI after the window is shown.
        This is because we need to know the number of sensors available to create the
        same number of plots
        """
        self.init_data()
        self.init_ui()
        return super().showEvent(event)

    def init_data(self):
        ### data
        self.queue.clear()
        self.dev_names = self.dm.get_all_sensor_names()
        self.dev_sn = self.dm.get_all_sensor_serial()

        for dev in self.dev_names:
            if dev in self.buffers:  # buffer already initialized
                continue
            self.buffers[dev] = YostBuffer(
                bufsize=self.init_bufsize, savedir=self.savedir, name=dev
            )

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
            plot.addLegend(offset=(1, 1), **plot_style)
            plot.setXRange(*self.config.xrange)
            plot.setYRange(*self.config.yrange)
            if self.config.autoscale_y:
                plot.enableAutoRange(axis="y")
            plot.setLabel("bottom", "Time", units="s", **plot_style)
            plot.setLabel("left", "Euler Angle", units="deg", **plot_style)
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

            # TODO
            # def begin_trial_color():
            # self.update_target_color(TARGET_BRUSH_FG)

            # def end_trial_color():
            # self.update_target_color(TARGET_BRUSH_BG)

            # self.task_widget.sigTrialBegin.connect(begin_trial_color)
            # self.task_widget.sigTrialEnd.connect(end_trial_color)

        ### apply other config
        config = self.config
        config.target_show and self.update_targets()
        config.show_roll or self.show_hide_curve("Roll", False)
        config.show_pitch or self.show_hide_curve("Pitch", False)
        config.show_yaw or self.show_hide_curve("Yaw", False)
        config.show_rollpitch or self.show_hide_curve("abs(roll) + abs(pitch)", False)

        self.start_stream()

    def start_stream(self):
        """Start the stream and show in the scope
        Clear the queue and buffers
        """
        self.init_data()

        dummy_queue = _DummyQueue()
        if self.trigno_client:
            self.trigno_client.handle_stream(dummy_queue, self.savedir)
        self.dm.start_stream(self.queue)
        self.timer.start()

    def stop_stream(self):
        """Stop the data stream and update timer"""
        self.dm.stop_stream()
        hasattr(self, "timer") and self.timer.stop()
        self.trigno_client and self.trigno_client.stop_stream()

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
        qsize = len(q)
        if not qsize:
            return

        for _ in range(qsize):  # process current items in queue
            packet: Packet = q.popleft()
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
        # 2. If true, start the 3 second timer
        if self.task_widget:
            tmin, tmax = self.target_range
            for name in self.dev_names:
                buf = self.buffers[name]
                if tmin <= buf.data[-1, -1] <= tmax:
                    self.task_widget.sigTaskEventIn.emit(TEvent.ENTER_TARGET)
                else:
                    self.task_widget.sigTaskEventIn.emit(TEvent.EXIT_TARGET)

    def closeEvent(self, event: qg.QCloseEvent) -> None:
        with pg.BusyCursor():
            self.stop_stream()

        self.task_widget and self.task_widget.close()
        return super().closeEvent(event)


class _DummyQueue:
    def append(self, _):
        ...
