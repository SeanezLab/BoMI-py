from __future__ import annotations
from typing import Callable, Dict, List
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
    dict(name="sigopts", title="Signal Options", type="group", children=[]),
    dict(name="antialias", type="bool", value=pg.getConfigOption("antialias")),
    dict(
        name="connect",
        type="list",
        limits=["all", "pairs", "finite", "array"],
        value="all",
    ),
    dict(name="skipFiniteCheck", type="bool", value=False),
]

params = ptree.Parameter.create(name="Parameters", type="group", children=children)


def _print(*args):
    print("[ScopeWidget]", *args)


@dataclass
class Buffer:
    timestamp: np.array
    data: np.array
    ptr: int

    @classmethod
    def init(cls, initial_buf_size: int, dims: int) -> Buffer:
        timestamp = np.zeros(initial_buf_size)
        buf = np.zeros((initial_buf_size, dims))
        ptr = 0
        return Buffer(timestamp, buf, ptr)

    def add(self, packet: Packet):
        data, ts = self.data, self.timestamp
        data[self.ptr, :2] = (packet.roll, packet.pitch)
        ts[self.ptr] = packet.t
        self.ptr += 1

        # Double buffer size if full
        l, dims = data.shape
        if self.ptr >= l:
            self.data = np.empty((l * 2, dims))
            self.data[:l] = data
            self.timestamp = np.empty(l * 2)
            self.timestamp[:l] = ts


def init_buffers(names: List[str], bufsize: int, dims: int) -> Dict[str, Buffer]:
    return {dev: Buffer.init(initial_buf_size=bufsize, dims=dims) for dev in names}


class ScopeWidget(qw.QWidget):
    def __init__(self, device_manager: DeviceManager):
        super().__init__()
        self.dm: DeviceManager = device_manager

    def show(self) -> None:
        self.init_data()
        self.init_ui()
        return super().show()

    def init_data(self):
        ### data
        self.dims = 2
        self.queue: Queue[Packet] = Queue()
        self.dev_names: List[str] = self.dm.get_all_sensor_names()
        self.dev_sn: List[str] = self.dm.get_all_sensor_serial()
        self.init_bufsize = 2000
        self.buffers = init_buffers(self.dev_names, self.init_bufsize, self.dims)

    def init_ui(self):
        ### Init UI
        main_layout = qw.QHBoxLayout()
        self.setLayout(main_layout)
        splitter = qw.QSplitter()
        main_layout.addWidget(splitter)

        pt = ptree.ParameterTree(showHeader=False)
        pt.setParameters(params)

        def change(_, changes):
            for param, change, data in changes:
                if param.name() == "streaming":
                    if data == False:
                        self.stop_stream()
                    else:
                        self.start_stream()

        params.sigTreeStateChanged.connect(change)

        splitter.addWidget(pt)

        self.glw = glw = pg.GraphicsLayoutWidget(title="Plot title")
        splitter.addWidget(glw)

        ### Init Plots
        pens = ["r", "g", "b", "w"]

        def _init_curves(plot: pg.PlotItem):
            "Create `dims` curves on the given plot object"
            return [plot.plot(pen=pen) for pen in pens[: self.dims]]

        self.plots: Dict[str, pg.PlotItem | pg.ViewBox] = {}
        self.curves: Dict[str, List[pg.PlotCurveItem]] = {}
        for i, (name, sn) in enumerate(zip(self.dev_names, self.dev_sn)):
            self.plots[name] = plot = glw.addPlot(row=i + 1, col=0)
            plot.setXRange(-5, 0)
            plot.setYRange(-np.pi, np.pi)
            plot.setLabel("bottom", "Time", units="s")
            plot.setLabel("left", "Euler Angle", units="rad")
            if name == sn:
                plot.setTitle(f"{sn}")
            else:
                plot.setTitle(f"{sn} ({name})")
            plot.setDownsampling(mode="peak")

            self.curves[name] = _init_curves(plot)

        # init timer
        self.timer = qc.QTimer()
        self.timer.setInterval(20)
        self.timer.timeout.connect(self.updatePlot)

        self.start_stream()

    def start_stream(self):
        """Start the stream and show in the scope
        Recreate the queue and buffers
        """
        self.init_data()
        # self.queue = Queue()
        # self.buffers = init_buffers(self.dev_names, self.init_bufsize, self.dims)
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
                curves = self.curves[name]
                buf = self.buffers[name]
                x = -(now - buf.timestamp[: buf.ptr])
                for i in range(self.dims):
                    curves[i].setData(x=x, y=buf.data[: buf.ptr, i])

    def closeEvent(self, event: qg.QCloseEvent) -> None:
        with pg.BusyCursor():
            _print("Close event called")
            self.stop_stream()
            _print("Close event done")
        return super().closeEvent(event)
