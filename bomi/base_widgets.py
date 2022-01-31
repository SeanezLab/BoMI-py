from typing import Tuple, TypeVar
import PySide6.QtWidgets as qw
import PySide6.QtCore as qc

T = TypeVar("T")


def set_spinbox(
    spin_box: T,
    value: float,
    step_size: float,
    range: Tuple[float, float],
) -> T:
    spin_box.setSingleStep(step_size)
    spin_box.setRange(*range)
    spin_box.setValue(value)
    return spin_box


class TaskDisplay(qw.QWidget):
    signal_task = qc.Signal(str)  # emits (event_name) when a GO signal is sent
