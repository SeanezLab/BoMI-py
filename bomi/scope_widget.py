from time import perf_counter
from queue import Queue
from typing import Callable, List, Optional
import pyqtgraph.parametertree as ptree
import PySide6.QtGui as qg
import PySide6.QtWidgets as qw
import PySide6.QtCore as qc
import pyqtgraph as pg
import numpy as np


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
        dims=4,
        close_callbacks: List[Callable] = [],
    ):
        assert all(
            callable(cb) for cb in close_callbacks
        ), "Some callbacks are not callable"
        ### data
        self.n_dims = dims
        self._queue = queue
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

        self.timestamp = np.empty(100)
        self.data = np.empty((100, dims))
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
            _print("qsize", qsize)
            for _ in range(qsize):
                data = self.data
                ts = self.timestamp
                arr = q.get()  # arr holds a list of tuples (each tuple is one device)
                dev1 = arr[0]  # Only read first device for now
                data[self.ptr, :dims] = dev1[0][:dims]
                ts[self.ptr] = dev1[1]
                self.ptr += 1

                # check for resize
                l = data.shape[0]
                if self.ptr >= l:
                    self.data = np.empty((l * 2, dims))
                    self.data[:l] = data
                    self.timestamp = np.empty(l * 2)
                    self.timestamp[:l] = ts
                q.task_done()
        except Exception as e:
            _print("[Update Exception]", e)
        else:
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


if __name__ == "__main__":
    app = pg.mkQApp("Plot Speed Test")
    p = Plot()
    p.show()
    pg.exec()
