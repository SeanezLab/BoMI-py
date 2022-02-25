import PySide6.QtCore as qc
import PySide6.QtWidgets as qw
import PySide6.QtMultimedia as qm
from PySide6.QtCore import Qt, Slot

from bomi.audio.generate_tone import generate_tone


def _print(*args):
    print("[TonePlayer]", *args)


class TonePlayer(qc.QObject):
    """TonePlayer generates a tone at a given frequency and duration,
    and can play the tone asynchronously when `play` is called.

    TonePlayer needs to regenerate and reload the audio when the frequency
    or duration is changed, so if different tones need to be played at low
    latency, create multiple TonePlayer objects and initialized them differently
    to cache all tones.
    """

    def __init__(self, freq: int = 500, duration_ms: int = 500):
        super().__init__()
        self.tmpdir = qc.QTemporaryDir()
        assert self.tmpdir.isValid()
        self.effect = qm.QSoundEffect(self)
        self.set_freq_duration(freq, duration_ms)

    def set_freq_duration(self, freq: int, duration_ms: int):
        """Update the frequency and duration of the tone
        Generates and loads the temporary wave file with the tone
        """
        self.freq = freq
        self.duration_ms = duration_ms
        self.initialize_audio()

    def initialize_audio(self):
        fname = f"{self.freq}Hz{self.duration_ms}ms.wav"
        tmpfile = self.tmpdir.filePath(fname)
        generate_tone(self.freq, self.duration_ms, tmpfile)
        url = qc.QUrl.fromLocalFile(tmpfile)
        self.effect.setSource(url)

    def set_volume(self, vol: int):
        self.effect.setVolume(vol)

    def play(self):
        self.effect.play()


class AudioCalibrationWidget(qw.QWidget):
    """
    Widget to try tones at different freq, duration and volume
    """

    def __init__(self):
        super().__init__()
        self.player = TonePlayer()
        self.initialize_window()

    def initialize_window(self):
        layout = qw.QFormLayout(self)

        self.m_freq = qw.QSpinBox()
        self.m_freq.setRange(10, 2000)
        self.m_freq.setValue(self.player.freq)
        self.m_freq.valueChanged.connect(self.freq_duration_changed)
        layout.addRow(qw.QLabel("Frequency (Hz)"), self.m_freq)

        self.m_duration = qw.QSpinBox()
        self.m_duration.setRange(10, 5000)
        self.m_duration.setValue(self.player.duration_ms)
        self.m_duration.valueChanged.connect(self.freq_duration_changed)
        layout.addRow(qw.QLabel("Duration (ms)"), self.m_duration)

        self.m_volumeLabel = qw.QLabel("Volume: ()")
        self.m_volumeSlider = qw.QSlider(
            Qt.Horizontal, minimum=0, maximum=100, singleStep=10
        )
        self.m_volumeSlider.valueChanged.connect(self.update_volume_label)  # type: ignore
        self.m_volumeSlider.sliderReleased.connect(self.update_volume)  # type: ignore
        self.m_volumeSlider.setValue(int(self.player.effect.volume() * 100))
        layout.addRow(self.m_volumeLabel, self.m_volumeSlider)

        self.m_playButton = qw.QPushButton()
        self.m_playButton.clicked.connect(self.play)  # type: ignore
        self.m_playButton.setText("Play")
        layout.addWidget(self.m_playButton)

    @Slot()  # type: ignore
    def freq_duration_changed(self):
        self.player.set_freq_duration(self.m_freq.value(), self.m_duration.value())

    @Slot()  # type: ignore
    def play(self):
        self.player.effect.play()

    @Slot()  # type: ignore
    def update_volume_label(self):
        self.m_volumeLabel.setText(f"Volume: {self.m_volumeSlider.value()}")

    @Slot()  # type: ignore
    def update_volume(self):
        self.player.effect.setVolume(self.m_volumeSlider.value() / 100.0)


if __name__ == "__main__":
    app = qw.QApplication()
    win = AudioCalibrationWidget()
    win.show()
    app.exec()
