from math import pi, sin
from struct import pack

from PySide6.QtCore import QByteArray, QIODevice, QSysInfo
from PySide6.QtMultimedia import QAudioFormat
from PySide6.QtWidgets import QWidget


class Generator(QIODevice):
    def __init__(
        self,
        format: QAudioFormat,
        duration_us: int,
        sample_freq: float,
        parent: QWidget,
    ):
        super().__init__(parent)

        self.m_pos = 0
        self.m_buffer = QByteArray()

        self.generate_data(format, duration_us, sample_freq)

    def start(self):
        self.open(QIODevice.ReadOnly)

    def stop(self):
        self.m_pos = 0
        self.close()

    def reset(self) -> bool:
        self.m_pos = 0
        return super().reset()

    def generate_data(self, fmt: QAudioFormat, duration_us: int, sample_freq: float):
        pack_format = ""

        sample_size = fmt.bytesPerSample() * 8
        if sample_size == 8:
            if fmt.sampleFormat() == QAudioFormat.UInt8:
                scaler = lambda x: ((1.0 + x) / 2 * 255)
                pack_format = "B"
            elif fmt.sampleFormat() == QAudioFormat.Int16:
                scaler = lambda x: x * 127
                pack_format = "b"
        elif sample_size == 16:
            little_endian = QSysInfo.ByteOrder == QSysInfo.LittleEndian
            if fmt.sampleFormat() == QAudioFormat.UInt8:
                scaler = lambda x: (1.0 + x) / 2 * 65535
                pack_format = "<H" if little_endian else ">H"
            elif fmt.sampleFormat() == QAudioFormat.Int16:
                scaler = lambda x: x * 32767
                pack_format = "<h" if little_endian else ">h"

        assert pack_format != ""

        channel_bytes = fmt.bytesPerSample()

        length = (
            (fmt.sampleRate() * fmt.channelCount() * channel_bytes)
            * duration_us
            // 1_000_000
        )

        self.m_buffer.clear()
        sample_index = 0
        factor = 2 * pi * sample_freq / fmt.sampleRate()

        while length != 0:
            x = sin((sample_index % fmt.sampleRate()) * factor)
            packed = pack(pack_format, int(scaler(x)))

            for _ in range(fmt.channelCount()):
                self.m_buffer.append(packed)
                length -= channel_bytes

            sample_index += 1

    def readData(self, maxlen: int):
        data = QByteArray()
        total = 0

        while maxlen > total:
            if self.m_pos >= self.m_buffer.size():
                break
            chunk = min(self.m_buffer.size() - self.m_pos, maxlen - total)
            data.append(self.m_buffer.mid(self.m_pos, chunk))
            self.m_pos += chunk
            # self.m_pos = (self.m_pos + chunk) % self.m_buffer.size()
            total += chunk

        return data.data()

    def writeData(self, data):
        return 0

    def bytesAvailable(self):
        return self.m_buffer.size() + super(Generator, self).bytesAvailable()
