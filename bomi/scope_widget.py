from __future__ import annotations
from typing import Callable, Dict, List
from queue import Queue
from dataclasses import dataclass
from pathlib import Path
import traceback
import pyqtgraph.parametertree as ptree
import PySide6.QtGui as qg
import PySide6.QtWidgets as qw
import PySide6.QtCore as qc
import pyqtgraph as pg
import numpy as np

from bomi.device_manager import Packet


children = [
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


class ScopeWidget(qw.QWidget):
    def __init__(
        self,
        queue: Queue[Packet],
        device_names: List[str],
        dims=2,
        close_callbacks: List[Callable] = [],
    ):
        super().__init__()
        assert all(
            callable(cb) for cb in close_callbacks
        ), "Some callbacks are not callable"

        ### data
        self.n_dims = dims
        self.queue = queue
        self.dev_names: List[str] = device_names  # List[serial_hex, serial_hex, ...]
        self.close_callbacks = close_callbacks

        self.INIT_BUF_SIZE = 2000
        self.data = {
            dev: Buffer.init(initial_buf_size=self.INIT_BUF_SIZE, dims=dims)
            for dev in self.dev_names
        }

        ### Init UI
        main_layout = qw.QHBoxLayout()
        self.setLayout(main_layout)
        splitter = qw.QSplitter()
        main_layout.addWidget(splitter)

        pt = ptree.ParameterTree(showHeader=False)
        pt.setParameters(params)
        splitter.addWidget(pt)

        self.glw = glw = pg.GraphicsLayoutWidget(title="Plot title")
        splitter.addWidget(glw)

        ### Init Plots
        pens = ["r", "g", "b", "w"]

        def _init_curves(plot: pg.PlotItem):
            return [plot.plot(pen=pen) for pen in pens[:dims]]

        self.plots: Dict[str, pg.PlotItem | pg.ViewBox] = {}
        self.curves: Dict[str, List[pg.PlotCurveItem]] = {}
        for i, name in enumerate(self.dev_names):
            self.plots[name] = plot = glw.addPlot(row=i + 1, col=0)
            plot.setXRange(-5, 0)
            plot.setYRange(-np.pi, np.pi)
            plot.setLabel("bottom", "Time", units="s")
            plot.setLabel("left", "Euler Angle", units="rad")
            plot.setDownsampling(mode="peak")

            self.curves[name] = _init_curves(plot)

        # only update curves for a device when new packets are received
        self.new_packet: Dict[str, bool] = {dev: False for dev in self.dev_names}

        # Start timer
        self._running = False
        self.timer = qc.QTimer()
        self.timer.setInterval(30)
        self.timer.timeout.connect(self.update3)
        self.timer.start(0)

    def update3(self):
        dims = self.n_dims
        q = self.queue
        qsize = q.qsize()
        if not qsize:
            return
        try:
            for _ in range(qsize):  # process current items in queue
                # data, ts = self.data, self.timestamp
                packet: Packet = q.get()
                q.task_done()

                buf = self.data[packet.name]
                buf.add(packet)
                self.new_packet[packet.name] = True

        except Exception as e:
            _print("[Update Exception]", traceback.format_exc())

        else:  # On successful read from queue, update curves
            for name in self.dev_names:
                if not self.new_packet[name]:
                    continue
                self.new_packet[name] = False
                curves = self.curves[name]
                buf = self.data[name]
                x = buf.timestamp[: buf.ptr]
                x = -(x.max() - x)
                for i in range(dims):
                    curves[i].setData(x=x, y=buf.data[: buf.ptr, i])

    def closeEvent(self, event: qg.QCloseEvent) -> None:
        _print("Close event")
        self.timer.stop()
        [cb() for cb in self.close_callbacks]
        _print("Close event done")
        return super().closeEvent(event)
