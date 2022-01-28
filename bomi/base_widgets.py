from typing import Tuple
import PySide6.QtWidgets as qw
import PySide6.QtCore as qc


def create_spinbox(
    SpinBoxType: qw.QAbstractSpinBox,
    value: float,
    step_size: float,
    range: Tuple[float, float],
) -> qw.QAbstractSpinBox:
    spin_box = SpinBoxType()
    spin_box.setSingleStep(step_size)
    spin_box.setRange(*range)
    spin_box.setValue(value)
    return spin_box


class TaskDisplay(qw.QWidget):
    signal_task = qc.Signal(str)  # emits (event_name) when a GO signal is sent
