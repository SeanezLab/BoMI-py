import sys
import os
from typing import NamedTuple
import PySide6.QtGui as qg
import PySide6.QtWidgets as qw
import PySide6.QtCore as qc
import pyqtgraph as pg
import numpy as np

from bomi.device_manager import DeviceManager
from bomi.sample_3d_window import Sample3DWindow
from bomi.sample_plot_window import SamplePlotWindow


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

        button2 = qw.QPushButton(text="Show sample plot", parent=self)
        button2.clicked.connect(self.show_sample_plot)
        layout.addWidget(button2)

        button3 = qw.QPushButton(text="Show sample 3D plot", parent=self)
        button3.clicked.connect(self.show_sample_3d_plot)
        layout.addWidget(button3)

    def _create_actions(self):
        newAct = qg.QAction("New", self)

        quitAct = qg.QAction("Quit", self)
        quitAct.setShortcut("ctrl+q")
        quitAct.triggered.connect(self.quit)

        self.actions = self.Actions(newAct=newAct, quitAct=quitAct)

    def _create_menus(self):
        menu_bar = qw.QMenuBar(self)
        self.file_menu = menu_bar.addMenu("File")
        self.file_menu.addActions(self.actions)

    @qc.Slot()
    def discover_devices(self):
        self._set_status("Discovering devices . . .")
        with pg.BusyCursor():
            self._device_manager.discover_devices()
        self._set_status(self._device_manager.status())
        # self._device_manager.setup_devices()

    @qc.Slot()
    def show_sample_plot(self):
        if not hasattr(self, "_plot_window"):
            self._plot_window = SamplePlotWindow()
        self._plot_window.show()

    @qc.Slot()
    def show_sample_3d_plot(self):
        if not hasattr(self, "_plot_3d_window"):
            self._plot_3d_window = Sample3DWindow()
        self._plot_3d_window.show()

    @qc.Slot()
    def quit(self):
        self.close()
        # qw.QApplication.quit()


if __name__ == "__main__":
    app = qw.QApplication()
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
