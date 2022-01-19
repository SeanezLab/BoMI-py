from time import perf_counter
from queue import Queue
from typing import Callable, Dict, List, Optional
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


class ScopeWidget(qw.QWidget):
    def __init__(
        self,
        queue: Optional[Queue] = None,
        dims=3,
        close_callbacks: List[Callable] = [],
    ):
        assert all(
            callable(cb) for cb in close_callbacks
        ), "Some callbacks are not callable"
        ### data
        self.n_dims = dims
        self._queue = queue
        self._devs: List[str] = []  # List[serial_hex, serial_hex, ...]
        self._close_callbacks = close_callbacks

        super().__init__()
        main_layout = qw.QHBoxLayout()
        self.setLayout(main_layout)

        splitter = qw.QSplitter()
        main_layout.addWidget(splitter)

        pt = ptree.ParameterTree(showHeader=False)
        pt.setParameters(params)

        self.glw = glw = pg.GraphicsLayoutWidget(title="Plot title")
        splitter.addWidget(pt)
        splitter.addWidget(glw)

        ### Plot
        self.p1 = glw.addPlot(row=1, col=0)
        self.p2 = glw.addPlot(row=2, col=0)
        self.p1.setDownsampling(mode="peak")
        # self.p2.setDownsampling(mode="peak")
        # self.p2.setClipToView(True)

        pens = ["r", "g", "b", "w"]
        self.curves2 = [self.p2.plot(pen=p) for p in pens[:dims]]

        INIT_BUF_SIZE = 100
        self.timestamp = np.empty(INIT_BUF_SIZE)
        self.data = np.empty((INIT_BUF_SIZE, dims))
        self.ptr = 0

        self._running = False

        self.timer = qc.QTimer()
        self.timer.timeout.connect(self.update3)
        self.timer.start(0)

    def update3(self):
        dims = self.n_dims
        q = self._queue
        qsize = q.qsize()
        try:
            for _ in range(qsize):  # process current imtes in queue
                data, ts = self.data, self.timestamp
                d = q.get()  # arr holds a list of tuples (each tuple is one device)

                packet = d[0]
                
                data[self.ptr, :dims] = packet[0]
                ts[self.ptr] = packet[1]
                self.ptr += 1

                # Double buffer size if full
                l = data.shape[0]
                if self.ptr >= l:
                    self.data = np.empty((l * 2, dims))
                    self.data[:l] = data
                    self.timestamp = np.empty(l * 2)
                    self.timestamp[:l] = ts
                q.task_done()
        except Exception as e:
            _print("[Update Exception]", e)
        else:  # On successful read from queue, update curves
            curves2 = self.curves2
            for i in range(dims):
                curves2[i].setData(
                    x=self.timestamp[: self.ptr], y=self.data[: self.ptr, i]
                )

    def closeEvent(self, event: qg.QCloseEvent) -> None:
        _print("Close event")
        self.timer.stop()
        [cb() for cb in self._close_callbacks]
        _print("Close event done")
        return super().closeEvent(event)
