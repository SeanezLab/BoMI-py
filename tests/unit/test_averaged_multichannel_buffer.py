import numpy as np
import pytest
from importlib import resources

from bomi.datastructure import AveragedMultichannelBuffer, Packet


@pytest.fixture
def multichannel_data_file():
    import tests.unit.fixtures
    return resources.files(tests.unit.fixtures).joinpath("multichannel_data.csv")


def test_saves_correct_data(tmp_path, multichannel_data_file):
    channel_labels = ["first", "second", "third"]

    buffer = AveragedMultichannelBuffer(
        bufsize=AveragedMultichannelBuffer.DEFAULT_MOVING_AVERAGE_POINTS,
        savedir=tmp_path,
        name="1",
        input_kind="FakeSensor",
        channel_labels=channel_labels
    )

    with open(multichannel_data_file) as f:
        expected = np.genfromtxt(multichannel_data_file, delimiter=",", skip_header=1)

        for row in expected:
            packet = Packet(
                time=row[0],
                device_name="1",
                channel_readings=dict(zip(channel_labels, row[1:]))
            )
            buffer.add_packet(packet)

    actual = np.genfromtxt(buffer.save_file, delimiter=",", skip_header=1)
    expected = np.genfromtxt(multichannel_data_file, delimiter=",", skip_header=1)
    assert(np.array_equal(actual, expected))




