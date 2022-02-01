import PySide6.QtWidgets as qw
import PySide6.QtCore as qc
import PySide6.QtGui as qg
from PySide6.QtCore import Qt


class WindowMixin(object):
    def error_dialog(self, msg: str):
        "Display `msg` in a popup error dialog"
        if not hasattr(self, "_popup_window"):
            self._err_dialog = qw.QErrorMessage()
            self._err_dialog.setWindowTitle(f"BoMI Error")

        self._err_dialog.showMessage(msg)

    def no_sensors_error(self):
        return self.error_dialog(
            "No sensors available. Plug in the devices, then click on 'Discover devices'"
        )

    def start_widget(self, obj: qw.QWidget, maximize=True):
        "Run the given QWidget class in a new window"
        attr = str(type(obj))
        setattr(self, attr, obj)

        # hijack the QWidget's `closeEvent` to delete this attribute
        obj._closeEvent = obj.closeEvent

        def closeEvent(event: qg.QCloseEvent):
            delattr(self, attr)
            obj._closeEvent(event)

        obj.closeEvent = closeEvent

        if maximize:
            obj.showMaximized()
        else:
            obj.show()
