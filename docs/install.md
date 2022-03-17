# Install BoMI

### 1. Create a virtual environment with Conda.

_**This application requires Python>=3.10**_, hence we're going to use `conda` to install a compatible version of Python. On **Windows**, use the **Anaconda Powershell Prompt**. If you don't have Anaconda or Miniconda installed, I recommend [Miniconda](https://docs.conda.io/en/latest/miniconda.html).

<div class="termy">
$ conda create -y -n bomi python==3.10
</div>

### 2. Activate the `conda` environment.

After this, you should see `(bomi)` in front of your command line prompt.

<div class="termy">
$ conda activate bomi
# (bomi) $$ 
</div>

### 3. Clone the git repo.

[Git with SSH is recommended](https://docs.github.com/en/authentication/connecting-to-github-with-ssh).

<div class="termy">
# (bomi) $$ git clone git@github.com:SeanezLab/BoMI-py.git
</div>

### 4. Install the packages with pip.

This installs 3 packages: `bomi`, `threespace_api` and `trigno_sdk`.

On Windows:

<div class="termy">
# (bomi) $$ cd BoMI-py
# (bomi) $$ python -m pip install .
</div>

On MacOS and Linux:

<div class="termy">
# (bomi) $$ cd BoMI-py
# (bomi) $$ python3 -m pip install .
</div>

### 5. Start BoMI

To test the installation of BoMI-py, run the command `bomi`.

<div class="termy">
# (bomi) $$ bomi
</div>

The BoMI window will open.

![BoMI Screenshot](./img/bomi-home.PNG)
