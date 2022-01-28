import PySide6.QtWidgets as qw
import PySide6.QtCore as qc


class TaskDisplay(qw.QWidget):
    signal_task = qc.Signal(str)  # emits (event_name) when a GO signal is sent
