from __future__ import annotations
from functools import partial
from typing import Callable, Dict, List, Tuple, TypeVar
import PySide6.QtWidgets as qw
import PySide6.QtCore as qc
from dataclasses import Field

from bomi.datastructure import Metadata

T = TypeVar("T", qw.QSpinBox, qw.QDoubleSpinBox)


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
    signal_task: qc.SignalInstance = qc.Signal(
        str
    )  # emits (event_name) when a GO signal is sent
    _task_stack: List[str] = []

    def emit_begin(self, event_name: str):
        self.signal_task.emit("begin_" + event_name)
        self._task_stack.append(event_name)

    def emit_end(self):
        """End the last begin signal"""
        if self._task_stack:
            self.signal_task.emit("end_" + self._task_stack.pop())


def generate_edit_form(
    dc: Metadata,
    name: str = None,
    dialog_box=False,
    callback: Callable[[], None] = None,
) -> qw.QWidget | qw.QDialog:
    """Given a dataclass, generate a QGroupBox with a QFormLayout that allows
    one to edit every field in the dataclass. The `metadata` attribute of each
    field will be inspected for extra information

    Params
    ------
    dc: DataClass instance
    name: name for the QGroupBox
    dialog_box: If False, returns a QGroupBox, where every edit will take effect immediately.
        If True, returns a QDialog, where edits will only take effect if the dialog is accepted.
    callback: called when the edits are accepted

    Implemented types, their corresponding QWidget and the metadata keys

    (str) - QLineEdit
        - metadata: dict(name=str)

    (int) - QSpinBox
        - metadata: dict(name=str, range=(float, float), step=float)

    (float) - QDoubleSpinBox
        - metadata: dict(name=str, range=(float, float), step=float)

    """
    assert hasattr(dc, "__dataclass_fields__")

    name = name if name else dc.__class__.__name__

    gb = qw.QGroupBox(name)
    layout = qw.QFormLayout()
    gb.setLayout(layout)

    fields: Dict[str, Field] = dc.__dataclass_fields__
    widgets: Dict[str, qw.QWidget] = {}

    def accept_QLineEdit(key: str):
        le: qw.QLineEdit = widgets[key]
        setattr(dc, key, le.text())

    def reject_QLineEdit(key: str):
        le: qw.QLineEdit = widgets[key]
        le.setText(fields[key].default)

    def accept_QSpinBox(key: str):
        sb: qw.QSpinBox | qw.QDoubleSpinBox = widgets[key]
        setattr(dc, key, sb.value())

    def reject_QSpinBox(key: str):
        sb: qw.QSpinBox | qw.QDoubleSpinBox = widgets[key]
        sb.setValue(fields[key].default)

    accept_cbs: List[Callable[[], None]] = []
    reject_cbs: List[Callable[[], None]] = []

    for key, field in fields.items():
        if field.type == "str":
            widget = qw.QLineEdit(getattr(dc, key))
            widgets[key] = widget

            accept_cbs.append(partial(accept_QLineEdit, key))
            reject_cbs.append(partial(reject_QLineEdit, key))

        elif field.type in ("float", "int"):
            widget = qw.QSpinBox() if field.type == "int" else qw.QDoubleSpinBox()
            widgets[key] = widget
            widget.setValue(getattr(dc, key))
            if "step" in field.metadata:
                widget.setSingleStep(field.metadata["step"])
            if "range" in field.metadata:
                _range = field.metadata["range"]
                assert len(_range) == 2
                widget.setRange(*_range)

            accept_cbs.append(partial(accept_QSpinBox, key))
            reject_cbs.append(partial(reject_QSpinBox, key))
        else:
            breakpoint()
            raise NotImplementedError(
                f"Support for type {field.type} not implemented yet"
            )

        fieldname = field.metadata.get("name", key.replace("_", " ").title())
        layout.addRow(fieldname, widget)

    main_layout = qw.QVBoxLayout()
    main_layout.addWidget(gb)

    button_box = qw.QDialogButtonBox(
        qw.QDialogButtonBox.Ok | qw.QDialogButtonBox.Cancel
    )
    main_layout.addWidget(button_box)

    def accept():
        [cb() for cb in accept_cbs]
        callback and callback()

    def reject():
        [cb() for cb in reject_cbs]

    if dialog_box:
        dialog = qw.QDialog()
        dialog.setWindowTitle(name)
        dialog.setLayout(main_layout)

        def _reject():
            reject()
            dialog.reject()

        def _accept():
            accept()
            dialog.accept()

        button_box.accepted.connect(_accept)
        button_box.rejected.connect(_reject)

        return dialog
    else:
        widget = qw.QWidget()
        widget.setLayout(main_layout)

        button_box.accepted.connect(accept)
        button_box.rejected.connect(reject)

        return widget
