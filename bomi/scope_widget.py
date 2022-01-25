from __future__ import annotations

import traceback
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from timeit import default_timer
from typing import ClassVar, Dict, List, Tuple

import numpy as np
import pyqtgraph as pg
import pyqtgraph.parametertree as ptree
import PySide6.QtCore as qc
import PySide6.QtGui as qg
import PySide6.QtWidgets as qw
from pyqtgraph.parametertree.parameterTypes import ActionParameter

from bomi.datastructure import Buffer, Packet
from bomi.device_manager import DeviceManager


def _print(*args):
    print("[ScopeWidget]", *args)


@dataclass
class PlotHandle:
    "Holds a PlotItem and its curves"
    plot: pg.PlotItem | pg.ViewBox
    curves: List[pg.PlotCurveItem]
    target: pg.LinearRegionItem | None

    pens: ClassVar = ("r", "g", "b", "w")

    @classmethod
    def init(
        cls, plot: pg.PlotItem, target_range: Tuple[float, float] = None
    ) -> PlotHandle:
        "Create curves on the given plot object"
        # init curves
        curves = [
            plot.plot(pen=pen, name=name) for pen, name in zip(cls.pens, Buffer.labels)
        ]

        target = cls.init_target(plot, target_range) if target_range else None

        return PlotHandle(plot=plot, curves=curves, target=target)

    @classmethod
    def init_curve(cls, plot: pg.PlotItem, i: int):
        assert i < len(Buffer.labels)
        return plot.plot(pen=cls.pens[i], name=Buffer.labels[i])

    @staticmethod
    def init_target(
        plot: pg.PlotItem, target_range: Tuple[float, float]
    ) -> pg.LinearRegionItem:
        # Target region
        target = pg.LinearRegionItem(
            values=target_range, orientation="horizontal", movable=False
        )
        pg.InfLineLabel(target.lines[0], "Target", position=0.05, anchor=(1, 1))
        plot.addItem(target)
        return target

    def update_target(self, target_range: Tuple[float, float]):
        if self.target is None:
            self.target = self.init_target(self.plot, target_range)
        self.target.lines[0].setValue(target_range[0])
        self.target.lines[1].setValue(target_range[1])

    def clear_target(self):
        self.plot.removeItem(self.target)
        self.target = None


@dataclass
class ScopeConfig:
    window_title = "Scope"

    target_show: bool = False
    target_range: Tuple[float, float] = (0.8, 0.9)

    show_roll: bool = True
    show_pitch: bool = True
    show_yaw: bool = True
    show_rollpitch: bool = True


class ScopeWidget(qw.QWidget):
    def __init__(
        self, device_manager: DeviceManager, config: ScopeConfig = ScopeConfig()
    ):
        super().__init__()
        self.dm: DeviceManager = device_manager
        self.setWindowTitle(config.window_title)

        self.show_labels = list(Buffer.labels)
        self.queue: Queue[Packet] = Queue()

        children = [
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
        ]

        self.params: ptree.Parameter = ptree.Parameter.create(
            name="Controls", type="group", children=children
        )

        key2label = {  # map from a config name to the corresponding Buffer.labels
            "show_roll": "Roll",
            "show_pitch": "Pitch",
            "show_yaw": "Yaw",
            "show_rollpitch": "abs(roll) + abs(pitch)",
        }

        def onPTChange(_, changes):
            for param, change, data in changes:
                name = param.name()

                if name == "streaming":
                    self.toggle_stream(data)
                elif name in ("tmax", "tmin"):
                    self.update_targets()
                elif name == "tshow":
                    if data == False:
                        self.clear_targets()
                    else:
                        self.update_targets()

                elif name in key2label:
                    handleShowHideCurves(key2label[name], data)

        def handleShowHideCurves(name: str, show: bool):
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

        self.params.sigTreeStateChanged.connect(onPTChange)

        def tare():
            with pg.BusyCursor():
                self.stop_stream()
                self.start_stream()

        self.params.child("tare").sigActivated.connect(tare)

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

    def get_target_show(self) -> bool:
        return self.params.child("target").child("tshow").value()

    def get_target_range(self) -> Tuple[float, float]:
        targ_param = self.params.child("target")
        target_range = (
            targ_param.child("tmax").value(),
            targ_param.child("tmin").value(),
        )
        return target_range

    def showEvent(self, event: qg.QShowEvent) -> None:
        self.init_data()
        self.init_ui()
        return super().showEvent(event)

    def init_data(self):
        ### data
        while self.queue.qsize():
            self.queue.get()
            self.queue.task_done()
        self.dev_names: List[str] = self.dm.get_all_sensor_names()
        self.dev_sn: List[str] = self.dm.get_all_sensor_serial()
        self.init_bufsize = 2000
        self.buffers = Buffer.init_buffers(self.dev_names, self.init_bufsize)

    def init_ui(self):
        ### Init UI
        main_layout = qw.QHBoxLayout()
        self.setLayout(main_layout)
        splitter = qw.QSplitter()
        main_layout.addWidget(splitter)

        pt = ptree.ParameterTree(showHeader=False)
        pt.setParameters(self.params)
        splitter.addWidget(pt)

        self.glw = glw = pg.GraphicsLayoutWidget()
        splitter.addWidget(glw)

        ### Init Plots
        self.plot_handles: Dict[str, PlotHandle] = {}
        for i, (name, sn) in enumerate(zip(self.dev_names, self.dev_sn)):
            title = f"{sn}" if name == sn else f"{sn} ({name})"
            plot: pg.PlotItem = glw.addPlot(row=i + 1, col=0, title=title)
            plot.addLegend(offset=(1, 1))
            plot.setXRange(-6, 0)
            plot.setYRange(-np.pi, np.pi)
            plot.setLabel("bottom", "Time", units="s")
            plot.setLabel("left", "Euler Angle", units="rad")
            plot.setDownsampling(mode="peak")
            self.plot_handles[name] = PlotHandle.init(plot)

        # init timer
        self.timer = qc.QTimer()
        self.timer.setInterval(20)
        self.timer.timeout.connect(self.update)

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
        self.timer.stop()

    def toggle_stream(self, on: bool):
        self.start_stream() if on else self.stop_stream()

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
                self.buffers[packet.name].add(packet)

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
