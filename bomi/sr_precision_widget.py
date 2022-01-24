from __future__ import annotations
from typing import Dict, List, Optional
from queue import Queue
from dataclasses import dataclass
from pathlib import Path
from timeit import default_timer
import traceback
import pyqtgraph.parametertree as ptree
import PySide6.QtGui as qg
import PySide6.QtWidgets as qw
import PySide6.QtCore as qc
import pyqtgraph as pg
import numpy as np

from bomi.device_manager import DeviceManager, Packet


children = [
    dict(name="streaming", title="Streaming", type="bool", value=True),
    dict(
        name="target",
        title="Target",
        type="group",
        children=[
            dict(name="tmax", title="Max", type="float", value=1.2),
            dict(name="tmin", title="Min", type="float", value=1.0),
        ],
    ),
]

params = ptree.Parameter.create(name="Parameters", type="group", children=children)


def _print(*args):
    print("[ScopeWidget]", *args)


@dataclass
class Buffer:
    timestamp: np.array  # 1D array of timestamps
    data: np.array  # 2D array of (roll, pitch, yaw)
    mag: np.array  # 1D array of magnitude
    ptr: int

    @classmethod
    def init(cls, initial_buf_size: int) -> Buffer:
        timestamp = np.zeros(initial_buf_size)
        buf = np.zeros((initial_buf_size, 3))
        mag = np.zeros(initial_buf_size)
        return Buffer(timestamp, buf, mag, 0)

    def add(self, packet: Packet):
        data, mag, ts = self.data, self.mag, self.timestamp
        data[self.ptr, :3] = (packet.roll, packet.pitch, packet.yaw)
        mag[self.ptr] = abs(packet.roll) + abs(packet.pitch)
        ts[self.ptr] = packet.t
        self.ptr += 1

        # Double buffer size if full
        l, dims = data.shape
        if self.ptr >= l:
            new_l = l * 2
            self.data = np.empty((new_l, dims))
            self.data[:l] = data

            self.mag = np.empty(new_l)
            self.mag[:l] = mag

            self.timestamp = np.empty(new_l)
            self.timestamp[:l] = ts


def init_buffers(names: List[str], bufsize: int) -> Dict[str, Buffer]:
    return {dev: Buffer.init(initial_buf_size=bufsize) for dev in names}


class SRPrecisionWidget(qw.QWidget):
    def __init__(self, device_manager: DeviceManager):
        super().__init__()
        self.dm: DeviceManager = device_manager

        # init timer
        self.timer = qc.QTimer()
        self.timer.setInterval(20)
        self.timer.timeout.connect(self.updatePlot)

    def show(self) -> None:
        self.init_data()
        self.init_ui()
        self.start_stream()

        return super().show()

    def init_data(self):
        ### data
        self.queue: Queue[Packet] = Queue()
        self.dev_names: List[str] = self.dm.get_all_sensor_names()
        self.dev_sn: List[str] = self.dm.get_all_sensor_serial()
        self.init_bufsize = 2000
        self.buffers = init_buffers(self.dev_names, self.init_bufsize)

    def init_ui(self):
        ### Init UI
        main_layout = qw.QHBoxLayout()
        self.setLayout(main_layout)
        splitter = qw.QSplitter()
        main_layout.addWidget(splitter)

        pt = ptree.ParameterTree(showHeader=False)
        pt.setParameters(params)

        def onChange(_, changes):
            for param, change, data in changes:
                if param.name() == "streaming":
                    if data == False:
                        self.stop_stream()
                    else:
                        self.start_stream()
                elif param.name() == "tmax":
                    self.update_target(tmax=data)
                elif param.name() == "tmin":
                    self.update_target(tmin=data)

        params.sigTreeStateChanged.connect(onChange)
        targ_param = params.child("target")
        target_range = (
            targ_param.child("tmax").value(),
            targ_param.child("tmin").value(),
        )

        splitter.addWidget(pt)

        self.glw = glw = pg.GraphicsLayoutWidget()
        splitter.addWidget(glw)

        ### Init Plots
        @dataclass
        class PlotHandle:
            plot: pg.PlotItem | pg.ViewBox
            curves: List[pg.PlotCurveItem]
            target: pg.LinearRegionItem

            @classmethod
            def init(cls, plot: pg.PlotItem) -> PlotHandle:
                "Create curves and target on the given plot object"
                # init curves
                curves = [plot.plot(pen="g", name="Magnitude")]

                # Target region
                target = pg.LinearRegionItem(
                    values=target_range, orientation="horizontal", movable=False
                )
                pg.InfLineLabel(target.lines[0], "Target", position=0.05, anchor=(1, 1))
                plot.addItem(target)

                return PlotHandle(plot, curves, target)

        self.plot_handles: Dict[str, PlotHandle] = {}
        for i, (name, sn) in enumerate(zip(self.dev_names, self.dev_sn)):
            title = f"{sn}" if name == sn else f"{sn} ({name})"
            plot: pg.PlotItem = glw.addPlot(row=i + 1, col=0, title=title)
            plot.addLegend()
            plot.setXRange(-5, 0)
            plot.setYRange(0, np.pi)
            plot.setLabel("bottom", "Time", units="s")
            plot.setLabel("left", "Magnitude (abs(roll) + abs(yew))", units="rad")
            plot.setDownsampling(mode="peak")
            self.plot_handles[name] = PlotHandle.init(plot)

    def update_target(self, tmax: float = None, tmin: float = None):
        for name in self.dev_names:
            plot_handle = self.plot_handles[name]
            if tmin is not None:
                plot_handle.target.lines[0].setValue(tmin)
            if tmax is not None:
                plot_handle.target.lines[1].setValue(tmax)

    def start_stream(self):
        """Start the stream and show in the scope
        Recreate the queue and buffers
        """
        self.init_data()
        self.dm.start_stream(self.queue)
        self.timer.start(0)

    def stop_stream(self):
        self.dm.stop_stream()
        self.timer.stop()

    def updatePlot(self):
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
            now = default_timer()
            for name in self.dev_names:
                curves = self.plot_handles[name].curves
                buf = self.buffers[name]
                x = -(now - buf.timestamp[: buf.ptr])
                # for i in range(3):
                curves[0].setData(x=x, y=buf.mag[: buf.ptr])

    def closeEvent(self, event: qg.QCloseEvent) -> None:
        with pg.BusyCursor():
            _print("Close event called")
            self.stop_stream()
            _print("Close event done")
        return super().closeEvent(event)
