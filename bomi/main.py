from functools import partial
import PySide6.QtGui as qg
import PySide6.QtWidgets as qw
import PySide6.QtCore as qc
from PySide6.QtCore import Qt

from bomi.device_managers.yost_manager import YostDeviceManager
from bomi.device_managers.yost_widget import YostWidget

from bomi.painter_widget import PainterWidget
from bomi.reaching_widget import ReachingWidget
from bomi.sample_3d_widget import Sample3DWidget
from bomi.sample_plot_widget import SamplePlotWidget
from bomi.start_react_widget import StartReactWidget
from bomi.window_mixin import WindowMixin
from bomi.version import __version__

from bomi.device_managers.trigno_widget import TrignoWidget, TrignoClient

__appname__ = "BoMI"
__all__ = ["MainWindow", "main"]


def wrap_gb(name: str, *widgets: qw.QWidget):
    "Wrap widgets in a QGroupBox"
    gb = qw.QGroupBox(name)
    layout = qw.QVBoxLayout()
    for widget in widgets:
        layout.addWidget(widget)
    gb.setLayout(layout)
    return gb


class MainWindow(qw.QMainWindow, WindowMixin):
    """Main entry point to BoMI"""

    def __init__(self):
        super().__init__()
        self.yost_dm = YostDeviceManager()
        self.trigno_client = TrignoClient()

        self.init_ui()
        self.init_actions()
        self.init_menus()

        self.status_msg("Welcome to Seanez Lab")
        self.setWindowTitle(__appname__)
        self.setMinimumSize(650, 1000)

    def status_msg(self, msg: str):
        self.statusBar().showMessage(msg)

    def init_ui(self):
        vsplit = qw.QSplitter(Qt.Vertical)
        self.setCentralWidget(vsplit)

        l = qw.QLabel(self, text="BoMI 🚶", alignment=qc.Qt.AlignCenter)  # type: ignore
        l.setFont(qg.QFont("Arial", 16))
        vsplit.addWidget(l)

        ### Device manager group
        vsplit.addWidget(wrap_gb("Yost Device Manager", YostWidget(self.yost_dm)))

        ### Trigno Device manager group
        vsplit.addWidget(
            wrap_gb("Trigno Device Manager", TrignoWidget(self.trigno_client))
        )

        hsplit = qw.QSplitter(Qt.Horizontal)
        vsplit.addWidget(hsplit)

        ### StartReact Group
        hsplit.addWidget(
            wrap_gb("StartReact", StartReactWidget(self.yost_dm, self.trigno_client))
        )

        ### Cursor Task group
        btn_reach = qw.QPushButton(text="Reaching")
        btn_reach.clicked.connect(partial(self.start_widget, ReachingWidget()))  # type: ignore

        btn_paint = qw.QPushButton(text="Painter")
        btn_paint.clicked.connect(partial(self.start_widget, PainterWidget()))  # type: ignore

        hsplit.addWidget(wrap_gb("Cursor Tasks", btn_reach, btn_paint))

        ### Misc group
        btn2 = qw.QPushButton(text="Show sample plot")
        btn2.clicked.connect(partial(self.start_widget, SamplePlotWidget()))  # type: ignore

        btn3 = qw.QPushButton(text="Show sample 3D plot")
        btn3.clicked.connect(partial(self.start_widget, Sample3DWidget()))  # type: ignore

        hsplit.addWidget(wrap_gb("Others", btn2, btn3))

    def init_actions(self):
        quitAct = qg.QAction("Exit", self)
        quitAct.setShortcut("ctrl+q")
        quitAct.triggered.connect(self.close)  # type: ignore

        self.addAction(quitAct)

    def init_menus(self):
        menu_bar = qw.QMenuBar(self)
        self.file_menu = menu_bar.addMenu("File")
        self.file_menu.addActions(self.actions())


def main():
    app = qw.QApplication()
    win = MainWindow()
    win.show()
    app.exec()
