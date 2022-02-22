from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtMultimedia import QAudio, QAudioFormat, QAudioSink, QMediaDevices
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QWidget,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from bomi.audio.generator import Generator


def _print(*args):
    print("[AudioPlayer]", *args)


class AudioPlayer(QWidget):

    PUSH_MODE_LABEL = "Enable push mode"
    SUSPEND_LABEL = "Suspend playback"
    RESUME_LABEL = "Resume playback"

    DURATION_SECONDS = 1
    TONE_SAMPLE_RATE_HZ = 500
    DATA_SAMPLE_RATE_HZ = 44100

    def __init__(self):
        super().__init__()

        devices = QMediaDevices.audioOutputs()
        if not devices:
            print("No audio outputs found.", file=sys.stderr)

        self.m_devices = devices
        self.m_device = self.m_devices[0]
        self.m_output = None

        self.initialize_window()
        self.initialize_audio()

    def initialize_window(self):
        layout = QVBoxLayout(self)

        self.m_deviceBox = QComboBox()
        self.m_deviceBox.activated.connect(self.device_changed)  # type: ignore
        for device_info in self.m_devices:
            self.m_deviceBox.addItem(device_info.description(), device_info)

        layout.addWidget(self.m_deviceBox)

        self.m_suspendResumeButton = QPushButton()
        self.m_suspendResumeButton.clicked.connect(self.toggle_suspend_resume)  # type: ignore
        self.m_suspendResumeButton.setText(self.SUSPEND_LABEL)

        layout.addWidget(self.m_suspendResumeButton)

        volume_box = QHBoxLayout()
        volume_label = QLabel("Volume:")
        self.m_volumeSlider = QSlider(
            Qt.Horizontal, minimum=0, maximum=100, singleStep=10
        )
        self.m_volumeSlider.valueChanged.connect(self.volume_changed)  # type: ignore

        volume_box.addWidget(volume_label)
        volume_box.addWidget(self.m_volumeSlider)

        layout.addLayout(volume_box)

    def initialize_audio(self):
        self.m_format = QAudioFormat()
        self.m_format.setSampleRate(self.DATA_SAMPLE_RATE_HZ)
        self.m_format.setChannelCount(1)
        self.m_format.setSampleFormat(QAudioFormat.Int16)

        info = self.m_devices[0]
        if not info.isFormatSupported(self.m_format):
            _print("Default format not supported - trying to use nearest")
            self.m_format = info.nearestFormat(self.m_format)

        self.m_generator = Generator(
            self.m_format,
            self.DURATION_SECONDS * 1_000_000,
            self.TONE_SAMPLE_RATE_HZ,
            self,
        )

        self.create_audio_output()

    def create_audio_output(self):
        self.m_audioSink = QAudioSink(self.m_device, self.m_format)
        self.m_audioSink.stateChanged.connect(self.handle_state_changed)  # type: ignore

        self.m_generator.start()
        self.m_output = self.m_audioSink.start(self.m_generator)
        self.m_volumeSlider.setValue(int(self.m_audioSink.volume() * 100))

    @Slot(int)  # type: ignore
    def device_changed(self, index: int):
        self.m_generator.stop()
        self.m_audioSink.stop()
        self.m_device = self.m_deviceBox.itemData(index)

        self.create_audio_output()

    @Slot(int)  # type: ignore
    def volume_changed(self, value: int):
        if self.m_audioSink is not None:
            self.m_audioSink.setVolume(value / 100.0)

    @Slot()  # type: ignore
    def notified(self):
        bytes_free = self.m_audioSink.bytesFree()
        elapsed = self.m_audioSink.elapsedUSecs()
        processed = self.m_audioSink.processedUSecs()
        _print(
            f"bytesFree = {bytes_free}, "
            f"elapsedUSecs = {elapsed}, "
            f"processedUSecs = {processed}"
        )

    @Slot()  # type: ignore
    def toggle_suspend_resume(self):
        if self.m_audioSink.state() == QAudio.SuspendedState:
            _print("status: Suspended, resume()")
            self.m_audioSink.resume()
            self.m_suspendResumeButton.setText(self.SUSPEND_LABEL)

        elif self.m_audioSink.state() == QAudio.ActiveState:
            _print("status: Active, suspend()")
            self.m_audioSink.suspend()
            self.m_suspendResumeButton.setText(self.RESUME_LABEL)

        elif self.m_audioSink.state() == QAudio.StoppedState:
            _print("status: Stopped, resume()")
            self.m_audioSink.resume()
            self.m_suspendResumeButton.setText(self.SUSPEND_LABEL)

        elif self.m_audioSink.state() == QAudio.IdleState:
            _print("status: IdleState")
            self.m_audioSink.start(self.m_generator)

    state_map = {
        QAudio.ActiveState: "ActiveState",
        QAudio.SuspendedState: "SuspendedState",
        QAudio.StoppedState: "StoppedState",
        QAudio.IdleState: "IdleState",
    }

    @Slot(QAudio.State)  # type: ignore
    def handle_state_changed(self, state: QAudio.State):
        _print(f"state = {self.state_map.get(state, 'Unknown')}")
        if state == QAudio.IdleState:
            self.m_generator.reset()
            self.m_suspendResumeButton.setText(self.RESUME_LABEL)


if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)
    app.setApplicationName("Audio Output Test")

    audio = AudioPlayer()
    audio.show()

    sys.exit(app.exec())
