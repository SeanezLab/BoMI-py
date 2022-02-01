import PySide6.QtWidgets as qw
import PySide6.QtGui as qg


class WindowMixin(object):
    def error_dialog(self, msg: str):
        "Display `msg` in a popup error dialog"
        if not hasattr(self, "_err_dialog"):
            self._err_dialog = qw.QErrorMessage()
            self._err_dialog.setWindowTitle(f"BoMI Error")

        self._err_dialog.showMessage(msg)

    def no_sensors_error(self):
        return self.error_dialog(
            "No sensors available. Plug in the devices, then click on 'Discover devices'"
        )

    def start_widget(self, obj: qw.QWidget, maximize=True):
        "Run the given QWidget object in a new window"
        attr = str(type(obj))
        setattr(self, attr, obj)

        # Mockey patch QWidget's `closeEvent` to delete the object on close
        def closeEvent(event: qg.QCloseEvent):
            delattr(self, attr)
            obj._closeEvent(event)

        obj._closeEvent = obj.closeEvent
        obj.closeEvent = closeEvent

        if maximize:
            obj.showMaximized()
        else:
            obj.show()
