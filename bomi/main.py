from functools import partial
import PySide6.QtGui as qg
import PySide6.QtWidgets as qw

from bomi.device_managers.yost_manager import YostDeviceManager
from bomi.device_managers.yost_widget import YostWidget

from bomi.reaching_widget import ReachingWidget
from bomi.start_react_widget import StartReactWidget
from bomi.window_mixin import WindowMixin
from bomi.base_widgets import wrap_gb
from bomi.cursor import CursorControlWidget

from bomi.device_managers.trigno_widget import TrignoWidget, TrignoClient

__appname__ = "BoMI"
__all__ = ["MainWindow", "main"]


class MainWindow(qw.QMainWindow, WindowMixin):
    """Main entry point to BoMI"""

    def __init__(self):
        super().__init__()
        self.yost_dm = YostDeviceManager()
        self.trigno_client = TrignoClient()
        #TODO: qtmclient here?

        self.init_ui()
        self.init_actions()
        # menu bar overlaps with the device manager on Windows
        # self.init_menus()

        self.status_msg("Welcome to Seanez Lab")
        self.setWindowTitle(__appname__)
        self.setMinimumSize(1000, 600)

    def status_msg(self, msg: str):
        self.statusBar().showMessage(msg)

    def init_ui(self):
        w = qw.QWidget()
        self.setCentralWidget(w)

        hbox = qw.QHBoxLayout(w)
        vbox1 = qw.QVBoxLayout()
        vbox2 = qw.QVBoxLayout()

        hbox.addLayout(vbox1)
        tmp = qw.QWidget()
        tmp.setLayout(vbox2)
        tmp.setSizePolicy(qw.QSizePolicy.Fixed, qw.QSizePolicy.Expanding)
        hbox.addWidget(tmp)

        ### Device manager group
        _gb = wrap_gb("Yost Device Manager", YostWidget(self.yost_dm))
        _gb.setSizePolicy(qw.QSizePolicy.Expanding, qw.QSizePolicy.Fixed)
        vbox1.addWidget(_gb)

        ### Trigno Device manager group
        vbox1.addWidget(
            wrap_gb("Trigno Device Manager", TrignoWidget(self.trigno_client))
        )

        ### StartReact Group
        vbox2.addWidget(
            wrap_gb("StartReact", StartReactWidget(self.yost_dm, self.trigno_client))
        )

        ### Cursor Task group
        btn_reach = qw.QPushButton(text="Reaching")
        btn_reach.clicked.connect(partial(self.start_widget, ReachingWidget()))  # type: ignore

        vbox2.addWidget(wrap_gb("Cursor Tasks", btn_reach))

        ### Cursor Control group
        self.cursor_control = CursorControlWidget(
            dm=self.yost_dm, show_device_manager=False
        )
        vbox2.addWidget(wrap_gb("Cursor Control", self.cursor_control))
        self.installEventFilter(self.cursor_control)

        vbox2.addStretch()

    def init_actions(self):
        """
        Initialize QActions
        """
        quitAct = qg.QAction("Exit", self)
        quitAct.setShortcut("ctrl+q")
        quitAct.triggered.connect(self.close)  # type: ignore

        self.addAction(quitAct)

    def init_menus(self):
        """
        Initialize QMenuBar
        """
        menu_bar = qw.QMenuBar(self)
        self.file_menu = menu_bar.addMenu("File")
        self.file_menu.addActions(self.actions())

    def closeEvent(self, event: qg.QCloseEvent) -> None:
        self.cursor_control.stop()
        return super().closeEvent(event)


def main():
    app = qw.QApplication()
    win = MainWindow()
    win.show()
    app.exec()


if __name__ == "__main__":
    main()
