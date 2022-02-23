import struct
import wave

import numpy as np


def generate_tone(tone_freq_hz=500, sample_duration_ms=20, fname=None):
    fname = fname if fname else f"{tone_freq_hz}Hz{sample_duration_ms}ms.wav"

    sample_freq = 44100
    sample_len = int(sample_freq * sample_duration_ms / 1000)

    factor = 2 * np.pi * tone_freq_hz / sample_freq
    scaler = lambda x: x * 32767

    i = np.arange(0, sample_len)
    x = scaler(np.sin((i % sample_freq) * factor)).astype(int)
    packed = struct.pack("h" * sample_len * 2, *np.repeat(x, 2))

    noise_output = wave.open(fname, "w")
    noise_output.setparams((2, 2, sample_freq, 0, "NONE", "not compressed"))  # type: ignore
    noise_output.writeframes(packed)
    noise_output.close()


if __name__ == "__main__":
    generate_tone()
