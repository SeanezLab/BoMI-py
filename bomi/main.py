from typing import NamedTuple
from functools import partial
import PySide6.QtGui as qg
import PySide6.QtWidgets as qw
import PySide6.QtCore as qc
from PySide6.QtCore import Qt
import pyqtgraph as pg

from bomi.device_manager import YostDeviceManager
from bomi.device_manager_widget import DeviceManagerWidget
from bomi.painter_widget import PainterWidget
from bomi.reaching_widget import ReachingWidget
from bomi.sample_3d_widget import Sample3DWidget
from bomi.sample_plot_widget import SamplePlotWidget
from bomi.start_react_widget import StartReactWidget
from bomi.window_mixin import WindowMixin
from bomi.version import __version__


__appname__ = "BoMI"

__all__ = ["MainWindow", "main"]


class MainWindow(qw.QMainWindow, WindowMixin):
    class Actions(NamedTuple):
        quitAct: qg.QAction

    fileMenu: qw.QMenu
    actions: Actions

    def __init__(self):
        super().__init__()
        self._device_manager = YostDeviceManager()

        self._init_ui()
        self._init_actions()
        self._init_menus()

        self._status_msg("Welcome to Seanez Lab")
        self.setWindowTitle(__appname__)
        self.setMinimumSize(650, 400)

    def _status_msg(self, msg: str):
        self.statusBar().showMessage(msg)

    def _init_ui(self):
        cw = qw.QWidget()
        self.setCentralWidget(cw)
        main_layout = qw.QGridLayout()
        cw.setLayout(main_layout)

        l = qw.QLabel(self, text="BoMI 🚶", alignment=qc.Qt.AlignCenter)
        l.setFont(qg.QFont("Arial", 16))
        main_layout.addWidget(l, 0, 0)

        ### Device manager group
        cal_group = qw.QGroupBox("Device manager")
        main_layout.addWidget(cal_group)
        cal_group_layout = qw.QVBoxLayout()
        cal_group.setLayout(cal_group_layout)

        dm_widget = DeviceManagerWidget(self._device_manager)
        cal_group_layout.addWidget(dm_widget)

        ### StartReact Group
        sr_groupbox = qw.QGroupBox("Start React")
        main_layout.addWidget(sr_groupbox)
        sr_layout = qw.QGridLayout()
        sr_groupbox.setLayout(sr_layout)

        sr_w = StartReactWidget(self._device_manager)
        sr_layout.addWidget(sr_w)

        ### Cursor Task group
        task_group = qw.QGroupBox("Cursor Tasks")
        main_layout.addWidget(task_group)
        task_group_layout = qw.QVBoxLayout()
        task_group.setLayout(task_group_layout)

        btn_reach = qw.QPushButton(text="Reaching")
        btn_reach.clicked.connect(partial(self.start_widget, ReachingWidget))
        task_group_layout.addWidget(btn_reach)

        btn_paint = qw.QPushButton(text="Painter")
        btn_paint.clicked.connect(partial(self.start_widget, PainterWidget))
        task_group_layout.addWidget(btn_paint)

        ### Misc group
        misc_group = qw.QGroupBox("Others")
        main_layout.addWidget(misc_group)
        misc_group_layout = qw.QVBoxLayout()
        misc_group.setLayout(misc_group_layout)

        btn2 = qw.QPushButton(text="Show sample plot")
        btn2.clicked.connect(partial(self.start_widget, SamplePlotWidget))
        misc_group_layout.addWidget(btn2)

        btn3 = qw.QPushButton(text="Show sample 3D plot")
        btn3.clicked.connect(partial(self.start_widget, Sample3DWidget))
        misc_group_layout.addWidget(btn3)

    def _init_actions(self):
        quitAct = qg.QAction("Exit", self)
        quitAct.setShortcut("ctrl+q")
        quitAct.triggered.connect(self.close)

        self.actions = self.Actions(quitAct=quitAct)

    def _init_menus(self):
        menu_bar = qw.QMenuBar(self)
        self.file_menu = menu_bar.addMenu("File")
        self.file_menu.addActions(self.actions)



def main():
    app = qw.QApplication()
    win = MainWindow()
    win.show()
    app.exec()
