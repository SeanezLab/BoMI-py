from __future__ import annotations
from enum import Enum
from functools import partial
from typing import Callable, Dict, List, Tuple, TypeVar
import PySide6.QtWidgets as qw
import PySide6.QtCore as qc
from dataclasses import Field


T = TypeVar("T", qw.QSpinBox, qw.QDoubleSpinBox)


def set_spinbox(
    spin_box: T,
    value: float,
    step_size: float,
    range: Tuple[float, float],
) -> T:
    "Util func to set the parameters of a QSpinBox"
    spin_box.setSingleStep(step_size)  # type: ignore
    spin_box.setRange(*range)  # type: ignore
    spin_box.setValue(value)  # type: ignore
    return spin_box


class TaskEvent(Enum):
    """
    Measurement matching task event types
    """

    OUTSIDE = 0
    ENTER_TARGET = 1
    EXIT_TARGET = 2
    ENTER_BASE = 3
    EXIT_BASE = 4
    ENTER_PREP = 5
    EXIT_PREP = 6


class TaskDisplay(qw.QWidget):
    """
    Measurement matching task display widget
    provides signals for communication with a Scope
    """

    # emits (event_name) of key events in task for logging purposes
    sigTrialBegin: qc.SignalInstance = qc.Signal()  # type: ignore
    sigTrialEnd: qc.SignalInstance = qc.Signal()  # type: ignore

    sigTargetMoved: qc.SignalInstance = qc.Signal(tuple)  # type: ignore
    sigPreparedMoved: qc.SignalInstance = qc.Signal(tuple)  # type: ignore
    sigBaseMoved: qc.SignalInstance = qc.Signal(tuple)  # type: ignore

    # receive input events on state changes
    sigTaskEventIn: qc.SignalInstance = qc.Signal(TaskEvent)  # type: ignore

    sigColorRegion: qc.SignalInstance = qc.Signal(str, bool)

    selected_channel: str
    """
    The channel to use for the task, e.g. Roll.
    
    When StartReact is run, it cannot be changed,
    although the shown input channels can be changed.
    
    Replaces the functionality of SRConfig.angle_type,
    and allows StartReact to be performed for inputs besides angles.
    """

    def __init__(self, selected_channel):
        super().__init__()
        self.selected_channel = selected_channel


def generate_edit_form(
    dc: object,
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

    (str) - QLineEdit (default for str, if 'completion' present)
        - metadata: dict(name=str, completion=[str])

    (str) - QComboBox (used if 'options' present)
        - metadata: dict(name=str, options=[str])

    (int) - QSpinBox
        - metadata: dict(name=str, range=(int, int), step=int)

    (float) - QDoubleSpinBox
        - metadata: dict(name=str, range=(float, float), step=float)

    (bool) - QCheckBox
        - metadata: dict(name=str)

    """
    assert hasattr(dc, "__dataclass_fields__")

    name = name if name else dc.__class__.__name__

    layout = qw.QFormLayout()

    fields: Dict[str, Field] = dc.__dataclass_fields__  # type: ignore
    widgets: Dict[str, qw.QWidget] = {}

    def accept_QComboBox(key: str):
        combo: qw.QComboBox = widgets[key]  # type: ignore
        setattr(dc, key, combo.currentText())

    def reject_QComboBox(key: str):
        combo: qw.QComboBox = widgets[key]  # type: ignore
        combo.setCurrentText(fields[key].default)

    def accept_QLineEdit(key: str):
        le: qw.QLineEdit = widgets[key]  # type: ignore
        setattr(dc, key, le.text())

    def reject_QLineEdit(key: str):
        le: qw.QLineEdit = widgets[key]  # type: ignore
        le.setText(fields[key].default)

    def accept_QSpinBox(key: str):
        sb: qw.QSpinBox | qw.QDoubleSpinBox = widgets[key]  # type: ignore
        setattr(dc, key, sb.value())

    def reject_QSpinBox(key: str):
        sb: qw.QSpinBox | qw.QDoubleSpinBox = widgets[key]  # type: ignore
        sb.setValue(fields[key].default)

    def accept_QCheckBox(key: str):
        qcb: qw.QCheckBox = widgets[key]
        setattr(dc, key, qcb.isChecked())

    def reject_QCheckBox(key: str):
        qcb: qw.QCheckBox = widgets[key]
        qcb.setChecked(fields[key].default)

    accept_cbs: List[Callable[[], None]] = []
    reject_cbs: List[Callable[[], None]] = []

    for key, field in fields.items():
        if field.type == "str":

            if "options" in field.metadata:
                # if 'options' available, use QComboBox
                widget = qw.QComboBox()
                widget.addItems(field.metadata["options"])
                widget.setCurrentText(getattr(dc, key))
                widgets[key] = widget

                accept_cbs.append(partial(accept_QComboBox, key))
                reject_cbs.append(partial(reject_QComboBox, key))

            else:
                # by default use QLineEdit for str type
                widget = qw.QLineEdit(getattr(dc, key))
                widgets[key] = widget
                if "completion" in field.metadata:
                    model = qc.QStringListModel()
                    model.setStringList(field.metadata["completion"])
                    completer = qw.QCompleter()
                    completer.setModel(model)
                    widget.setCompleter(completer)
                widget.setText(getattr(dc, key))

                accept_cbs.append(partial(accept_QLineEdit, key))
                reject_cbs.append(partial(reject_QLineEdit, key))

        elif field.type in ("float", "int"):
            widget = qw.QSpinBox() if field.type == "int" else qw.QDoubleSpinBox()
            widgets[key] = widget
            if "step" in field.metadata:
                widget.setSingleStep(field.metadata["step"])
            if "range" in field.metadata:
                _range = field.metadata["range"]
                assert len(_range) == 2
                widget.setRange(*_range)
            widget.setValue(getattr(dc, key))

            accept_cbs.append(partial(accept_QSpinBox, key))
            reject_cbs.append(partial(reject_QSpinBox, key))

        elif field.type == "bool":
            widget = qw.QCheckBox()
            widgets[key] = widget
            widget.setChecked(getattr(dc, key))

            accept_cbs.append(partial(accept_QCheckBox, key))
            reject_cbs.append(partial(reject_QCheckBox, key))

        else:
            breakpoint()
            raise NotImplementedError(
                f"Support for type {field.type} not implemented yet"
            )

        fieldname = field.metadata.get("name", key.replace("_", " ").title())
        layout.addRow(fieldname, widget)

    gb = qw.QGroupBox(name)
    gb.setLayout(layout)

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

        button_box.accepted.connect(_accept)  # type: ignore
        button_box.rejected.connect(_reject)  # type: ignore

        return dialog
    else:
        widget = qw.QWidget()
        widget.setLayout(main_layout)

        button_box.accepted.connect(accept)  # type: ignore
        button_box.rejected.connect(reject)  # type: ignore

        return widget


def wrap_gb(name: str, *widgets: qw.QWidget):
    """
    Wrap widgets in a QGroupBox

    Usage:
    >>> wrap_gb("Cursor tasks", widget1, widget2, widget3)
    """

    gb = qw.QGroupBox(name)
    layout = qw.QVBoxLayout()
    for widget in widgets:
        layout.addWidget(widget)
    gb.setLayout(layout)
    return gb
