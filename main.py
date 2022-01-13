import sys
from typing import NamedTuple
from functools import partial
import PySide6.QtGui as qg
import PySide6.QtWidgets as qw
import PySide6.QtCore as qc
import pyqtgraph as pg
import numpy as np

from bomi.device_manager import DeviceManager
from bomi.painter_widget import PainterWindow
from bomi.reaching_widget import ReachingWidget
from bomi.sample_3d_window import Sample3DWindow
from bomi.sample_plot_window import SamplePlotWindow


__appname__ = "BoMI"


class MainWindow(qw.QMainWindow):
    class Actions(NamedTuple):
        quitAct: qg.QAction

    fileMenu: qw.QMenu
    actions: Actions

    def __init__(self):
        super().__init__()
        self._device_manager = DeviceManager()

        self._init_ui()
        self._create_actions()
        self._create_menus()

        self._set_status("Welcome to Seanez Lab")
        self.setWindowTitle(__appname__)
        self.setMinimumSize(160, 160)
        self.resize(480, 320)

    def _set_status(self, msg: str):
        self.statusBar().showMessage(msg)
        self.statusBar().show()

    def _init_ui(self):
        cw = qw.QWidget()
        self.setCentralWidget(cw)
        layout = qw.QGridLayout()
        cw.setLayout(layout)

        l = qw.QLabel(self, text="BoMI :)", alignment=qc.Qt.AlignCenter)
        l.setFont(qg.QFont("Arial", 16))
        layout.addWidget(l, 0, 0)

        ### Calibration group
        cal_group = qw.QGroupBox("Calibration")
        layout.addWidget(cal_group)
        cal_group_layout = qw.QVBoxLayout()
        cal_group.setLayout(cal_group_layout)

        btn1 = qw.QPushButton(text="Discover devices")
        btn1.clicked.connect(self.discover_devices)
        cal_group_layout.addWidget(btn1)


        ### Task group
        task_group = qw.QGroupBox("Tasks")
        layout.addWidget(task_group)
        task_group_layout = qw.QVBoxLayout()
        task_group.setLayout(task_group_layout)

        btn_reach = qw.QPushButton(text="Reaching")
        btn_reach.clicked.connect(partial(self._start_widget, ReachingWidget))
        task_group_layout.addWidget(btn_reach)

        btn_paint = qw.QPushButton(text="Painter")
        btn_paint.clicked.connect(partial(self._start_widget, PainterWindow))
        task_group_layout.addWidget(btn_paint)

        ### Misc group
        misc_group = qw.QGroupBox("Others")
        layout.addWidget(misc_group)
        misc_group_layout = qw.QVBoxLayout()
        misc_group.setLayout(misc_group_layout)

        btn2 = qw.QPushButton(text="Show sample plot")
        btn2.clicked.connect(partial(self._start_widget, SamplePlotWindow))
        misc_group_layout.addWidget(btn2)

        btn3 = qw.QPushButton(text="Show sample 3D plot")
        btn3.clicked.connect(partial(self._start_widget, Sample3DWindow))
        misc_group_layout.addWidget(btn3)

    def _create_actions(self):
        quitAct = qg.QAction("Exit", self)
        quitAct.setShortcut("ctrl+q")
        quitAct.triggered.connect(self.close)

        self.actions = self.Actions(quitAct=quitAct)

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
    def _start_widget(self, _cls: qw.QWidget):
        _attr = str(_cls)
        if not hasattr(self, _attr):
            _app = _cls()
            setattr(self, _attr, _app)

            def closeEvent(event: qg.QCloseEvent):
                event.accept()
                delattr(self, _attr)

            _app.closeEvent = closeEvent
            _app.showMaximized()


if __name__ == "__main__":
    app = qw.QApplication()
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
