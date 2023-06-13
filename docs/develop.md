## Installing dev dependencies
Development dependencies can be installed with:
```commandline
pip install -e ".[dev]"
```

## External Sensor Interface

The [Yost 3-Space Python API](https://yostlabs.com/3-space-application-programming-interface/) is [included in the source code](https://github.com/SeanezLab/BoMI-StartReact/tree/main/threespace_api) and has been modified for compatibility with Python>=3.8.

The Delsys Trigno Control Utility (Delsys SDK Server) must be running on a computer connected to the Delsys base station for the EMG part to work. The `trigno_sdk` package implements a client to the Delsys SDK, which communicates over TCP. Refer to the Trigno SDK User's Guide document to learn more about its internals.
