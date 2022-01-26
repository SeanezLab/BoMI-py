from __future__ import annotations
from pickle import NONE

import traceback
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from timeit import default_timer
from typing import Dict, List, Tuple

import pyqtgraph as pg
import pyqtgraph.parametertree as ptree
import PySide6.QtCore as qc
import PySide6.QtGui as qg
import PySide6.QtWidgets as qw
from PySide6.QtCore import Qt
from pyqtgraph.parametertree.parameterTypes import ActionParameter
from pyqtgraph.parametertree.parameterTypes.basetypes import Parameter

from bomi.datastructure import Buffer, Packet
from bomi.device_manager import YostDeviceManager


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

TARGET_PEN = NONE
TARGET_BRUSH = pg.mkBrush(qg.QColor(25, 222, 193, 15))


@dataclass
class PlotHandle:
    "Holds a PlotItem and its curves"
    plot: pg.PlotItem | pg.ViewBox
    curves: List[pg.PlotCurveItem]
    target: pg.LinearRegionItem | None

    @classmethod
    def init(
        cls, plot: pg.PlotItem, target_range: Tuple[float, float] = None
    ) -> PlotHandle:
        "Create curves on the given plot object"
        # init curves
        curves = []
        for pen, name in zip(PENS, Buffer.labels):
            curves.append(plot.plot(pen=pen, name=name))

        target = cls.init_target(plot, target_range) if target_range else None

        return PlotHandle(plot=plot, curves=curves, target=target)

    @classmethod
    def init_curve(cls, plot: pg.PlotItem, i: int):
        assert i < len(Buffer.labels)
        return plot.plot(pen=PENS[i], name=Buffer.labels[i])

    @staticmethod
    def init_target(
        plot: pg.PlotItem, target_range: Tuple[float, float]
    ) -> pg.LinearRegionItem:
        # Target region
        target = pg.LinearRegionItem(
            values=target_range,
            orientation="horizontal",
            movable=False,
            brush=TARGET_BRUSH,
        )
        pg.InfLineLabel(
            target.lines[0], "Target", position=0.05, anchor=(1, 1), color="k"
        )
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


@dataclass
class ScopeConfig:
    window_title: str = "Scope"

    target_show: bool = False
    target_range: Tuple[float, float] = (70, 80)

    xrange: Tuple[float, float] = (-6, 0)
    yrange: Tuple[float, float] = (-180, 180)

    show_roll: bool = True
    show_pitch: bool = True
    show_yaw: bool = True
    show_rollpitch: bool = True


class ScopeWidget(qw.QWidget):
    def __init__(
        self, device_manager: YostDeviceManager, config: ScopeConfig = ScopeConfig()
    ):
        super().__init__()
        self.dm: YostDeviceManager = device_manager
        self.setWindowTitle(config.window_title)
        self.config = config

        self.show_labels = list(Buffer.labels)
        self.queue: Queue[Packet] = Queue()

        self.dev_names: List[str] = []
        self.dev_sn: List[str] = []
        self.init_bufsize = 2500
        self.buffers: Dict[str, Buffer] = {}

        ### Parameter tree
        self.params: ptree.Parameter = ptree.Parameter.create(
            name="Controls",
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
            for param, change, data in changes:
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

        # self.params.sigTreeStateChanged.connect(onPTChange)
        self.params.child("streaming").sigValueChanged.connect(toggle_stream)
        self.params.child("target", "tshow").sigValueChanged.connect(updateTarget)
        self.params.child("target", "tmax").sigValueChanged.connect(updateTarget)
        self.params.child("target", "tmin").sigValueChanged.connect(updateTarget)
        self.params.child("show").sigTreeStateChanged.connect(onShowHideChange)

        # keep references of these params for more efficient query
        self.param_tshow: Parameter = self.params.child("target", "tshow")
        self.param_tmax: Parameter = self.params.child("target", "tmax")
        self.param_tmin: Parameter = self.params.child("target", "tmin")

        def tare():
            with pg.BusyCursor():
                self.stop_stream()
                self.start_stream()

        self.params.child("tare").sigActivated.connect(tare)

        # init timer
        self.timer = qc.QTimer()
        self.timer.setInterval(20)
        self.timer.timeout.connect(self.update)

    def show_hide_curve(self, name: str, show: bool):
        i = Buffer.labels.index(name)
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
        if not self.get_target_show():
            return
        target_range = self.get_target_range()
        for name in self.dev_names:
            plot_handle = self.plot_handles[name]
            plot_handle.update_target(target_range)
            self.buffers[name].move_target(default_timer(), *target_range)

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
        while self.queue.qsize():
            self.queue.get()
            self.queue.task_done()
        self.dev_names = self.dm.get_all_sensor_names()
        self.dev_sn = self.dm.get_all_sensor_serial()
        self.buffers = Buffer.init_buffers(
            self.dev_names, self.init_bufsize, task_name=self.config.window_title
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

        ### Init Plots
        self.plot_handles: Dict[str, PlotHandle] = {}
        plot_style = {"color": "k"}
        for i, (name, sn) in enumerate(zip(self.dev_names, self.dev_sn)):
            plot: pg.PlotItem = glw.addPlot(row=i + 1, col=0)
            plot.addLegend(offset=(1, 1), **plot_style)
            plot.setXRange(*self.config.xrange)
            plot.setYRange(*self.config.yrange)
            plot.setLabel("bottom", "Time", units="s", **plot_style)
            plot.setLabel("left", "Euler Angle", units="deg", **plot_style)
            plot.setDownsampling(mode="peak")
            title = f"{sn}" if name == sn else f"{sn} ({name})"
            plot.setTitle(title, **plot_style)
            self.plot_handles[name] = PlotHandle.init(plot)

        # Create param tree
        pt = ptree.ParameterTree(showHeader=False)
        pt.setParameters(self.params)
        splitter.addWidget(pt)

        # apply current config
        config = self.config
        config.target_show and self.update_targets()
        config.show_roll or self.show_hide_curve("Roll", False)
        config.show_pitch or self.show_hide_curve("Pitch", False)
        config.show_yaw or self.show_hide_curve("Yaw", False)
        config.show_rollpitch or self.show_hide_curve("abs(roll) + abs(pitch)", False)

        self.start_stream()

    def start_stream(self):
        """Start the stream and show in the scope
        Recreate the queue and buffers
        """
        self.init_data()
        self.dm.start_stream(self.queue)
        self.timer.start(0)

    def stop_stream(self):
        """Stop the data stream and update timer"""
        self.dm.stop_stream()
        hasattr(self, "timer") and self.timer.stop()

    def update(self):
        """Update function connected to the timer
        1. Consume all data currently in the queue
        2. If successful, update all plots
        """
        q = self.queue
        qsize = q.qsize()
        if not qsize:
            return
        try:
            for _ in range(qsize):  # process current items in queue
                packet: Packet = q.get()
                q.task_done()  # not using queue.join() anywhere so this doesn't matter
                self.buffers[packet.name].add_packet(packet)

        except Exception as e:
            _print("[Update Exception]", traceback.format_exc())

        else:  # On successful read from queue, update curves
            self.update_plots()

    def update_plots(self):
        now = default_timer()
        for name in self.dev_names:
            curves = self.plot_handles[name].curves
            buf = self.buffers[name]
            x = -(now - buf.timestamp[: buf.ptr])

            for i, name in enumerate(buf.labels):
                if name in self.show_labels:
                    curves[i].setData(x=x, y=buf.data[: buf.ptr, i])

    def closeEvent(self, event: qg.QCloseEvent) -> None:
        with pg.BusyCursor():
            # _print("Close event called")
            self.stop_stream()
            # _print("Close event done")
        return super().closeEvent(event)
