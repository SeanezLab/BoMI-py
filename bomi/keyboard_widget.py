import os
import PySide6.QtGui as qg
import PySide6.QtWidgets as qw
import PySide6.QtCore as qc
from PySide6.QtCore import Qt
import pyqtgraph as pg


class KeyboardWidget(qw.QWidget):
    def __init__(self):
        super().__init__()
        self._init_ui()
        
        os.environ["QT_IM_MODULE"] = "qtvirtualkeyboard"
        
    def _init_ui(self):
        layout = qw.QHBoxLayout()
        self.setLayout(layout)

        self.le = qw.QLineEdit("Input")
        layout.addWidget(self.le)


if __name__ == "__main__":
    app = qw.QApplication()
    win = KeyboardWidget()
    win.show()
    app.exec()