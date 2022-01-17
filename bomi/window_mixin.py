import PySide6.QtWidgets as qw


class WindowMixin:
    def error_dialog(self, msg: str):
        if not hasattr(self, "_popup_window"):
            self._popup_window = popup = qw.QErrorMessage()
            popup.setWindowTitle(f"BoMI Error")

        self._popup_window.showMessage(msg)
