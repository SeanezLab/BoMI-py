import sys
from typing import NamedTuple
import PySide6.QtGui as qg
import PySide6.QtWidgets as qw
import PySide6.QtCore as qc
import pyqtgraph as pg
import numpy as np

from bomi.device_manager import DeviceManager


__appname__ = "BoMI"


class MainWindow(qw.QMainWindow):
    class Actions(NamedTuple):
        newAct: qg.QAction
        quitAct: qg.QAction

    fileMenu: qw.QMenu
    actions: Actions

    def __init__(self):
        super().__init__()
        self._device_manager = DeviceManager()

        self._init_window()
        self._create_actions()
        self._create_menus()

        self._set_status("Welcome to Seanez Lab")
        self.setWindowTitle(__appname__)
        self.setMinimumSize(160, 160)
        self.resize(480, 320)

    def _set_status(self, msg: str):
        self.statusBar().showMessage(msg)
        self.statusBar().show()

    def _init_window(self):
        cw = qw.QWidget()
        self.setCentralWidget(cw)
        layout = qw.QGridLayout()
        cw.setLayout(layout)

        l = qw.QLabel(self, text="Hello", alignment=qc.Qt.AlignCenter)
        layout.addWidget(l, 0, 0)

        button1 = qw.QPushButton(text="Discover devices", parent=self)
        button1.clicked.connect(self.discover_devices)
        layout.addWidget(button1)

        button2 = qw.QPushButton(text="Show plot", parent=self)
        button2.clicked.connect(self.show_plot)
        layout.addWidget(button2)

    def _create_actions(self):
        newAct = qg.QAction("New", self)

        quitAct = qg.QAction("Quit", self)
        quitAct.setShortcut("ctrl+Q")
        quitAct.toggled.connect(self.close)

        self.actions = self.Actions(newAct=newAct, quitAct=quitAct)

    def _create_menus(self):
        menu_bar = qw.QMenuBar(self)
        self.file_menu = menu_bar.addMenu("File")
        self.file_menu.addActions(self.actions)

    @qc.Slot()
    def discover_devices(self):
        self._set_status("Discovering devices . . .")
        self._device_manager.discover_devices()
        self._set_status(self._device_manager.status())
        # self._device_manager.setup_devices()

    @qc.Slot()
    def show_plot(self):
        if not hasattr(self, "_plot_window"):
            self._plot_window = SamplePlotWindow()
        self._plot_window.show()


class SamplePlotWindow(qw.QWidget):
    def __init__(self):
        super().__init__()
        self.resize(300, 200)
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


if __name__ == "__main__":
    app = qw.QApplication()
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
