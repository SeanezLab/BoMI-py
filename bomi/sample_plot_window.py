import PySide6.QtGui as qg
import PySide6.QtWidgets as qw
import PySide6.QtCore as qc
import pyqtgraph as pg
import numpy as np


class SamplePlotWindow(qw.QWidget):
    def __init__(self):
        super().__init__()
        self.resize(300, 200)
        self.setWindowTitle("pyqtgraph example")

        layout = qw.QVBoxLayout()
        self.setLayout(layout)

        self.label = qw.QLabel("Plot Window")
        layout.addWidget(self.label)

        w = pg.GraphicsLayoutWidget(self)
        layout.addWidget(w)
        p1 = w.addPlot(row=0, col=0)
        p2 = w.addPlot(row=0, col=1)

        n = 300
        s1 = pg.ScatterPlotItem(
            size=10, pen=pg.mkPen(None), brush=pg.mkBrush(255, 255, 255, 120)
        )
        pos = np.random.normal(size=(2, n), scale=1e-5)
        spots = [{"pos": pos[:, i], "data": 1} for i in range(n)]
        s1.addPoints(spots)
        p1.addItem(s1)
