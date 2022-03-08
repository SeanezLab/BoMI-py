import struct
import wave

import numpy as np


SAMPLE_FREQ = 44100  # WAV Hz
SCALER = 32767  # Scaler for signed 16-bit int


def generate_tone(tone_freq_hz=500, sample_duration_ms=20, fname=None):
    """
    Generate a tone at frequency `tone_freq_hz` with duration `sample_duration_ms`
    and write to a WAV file at `fname`.
    """
    fname = fname if fname else f"{tone_freq_hz}Hz{sample_duration_ms}ms.wav"

    sample_freq = 44100
    sample_len = int(sample_freq * sample_duration_ms / 1000)
    factor = 2 * np.pi * tone_freq_hz / sample_freq

    i = np.arange(0, sample_len)
    x = SCALER * np.sin((i % sample_freq) * factor)

    # Taper off the volume at the end to reduce the "pop"
    taper_ms = 20
    taper_length = int(SAMPLE_FREQ * taper_ms / 1000)
    taper = np.cos(np.linspace(0, np.pi / 2, taper_length))
    x[-taper_length:] = x[-taper_length:] * taper

    # Pack into binary, signed 16-bit int (WAV format)
    packed = struct.pack("h" * sample_len * 2, *np.repeat(x.astype(int), 2))

    noise_output = wave.open(fname, "w")
    noise_output.setparams((2, 2, sample_freq, 0, "NONE", "not compressed"))  # type: ignore
    noise_output.writeframes(packed)
    noise_output.close()


if __name__ == "__main__":
    generate_tone()
