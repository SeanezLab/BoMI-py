# BoMI

Body Machine Interface (BoMI) is a GUI application written in Python 3.10 with Qt6.

## Installation

1. Clone the repo

3. Create a virtual environment with Conda. _**This application requires Python>=3.10**_, hence we're going to use `conda` to install a compatible version of Python. On Windows, use Anaconda Powershell Prompt. If you don't have Anaconda or Miniconda installed, I recommend you install [Miniconda](https://docs.conda.io/en/latest/miniconda.html).

```
conda create -y -n bomi python==3.10
```

3. Activate the `conda` environment. After this, you should see `(bomi)` in front of your command line prompt.

```
conda activate bomi
```

4. Install the packages with pip. This installs 3 packages: `bomi`, `threespace_api` and `trigno_sdk`.

On Windows:

```
cd BoMI-py  # or wherever you cloned the repo
python -m pip install .
```

On MacOS and Linux:

```
cd BoMI-py  # or wherever you cloned the repo
python3 -m pip install .
```

To start BoMI

5. To test the installation of BoMI-py try `bomi` and the main window should open. 

```
bomi
```

## External Sensor Interface

The [Yost 3-Space Python API](https://yostlabs.com/3-space-application-programming-interface/) is [included in the source code](https://github.com/SeanezLab/BoMI-py/tree/main/threespace_api) and has been modified for compatibility with Python>=3.8. 

The Delsys Trigno Control Utility (Delsys SDK Server) must be running on a computer connected to the Delsys base station for the EMG part to work. The `trigno_sdk` package implements a client to the Delsys SDK, which communicates over TCP. Refer to the Trigno SDK User's Guide document to learn more about its internals.
