from pathlib import Path
from queue import Queue
import tempfile

from trigno_sdk.client import TrignoClient

HOST_IP = "10.229.96.254"

c = TrignoClient(HOST_IP)
q = Queue()
tmpdir = tempfile.TemporaryDirectory()
savedir = Path(tmpdir.name)

c.connect()
breakpoint()

c.handle_stream(q, savedir)

