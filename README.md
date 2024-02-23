# Hunter-Sim

A simulation of the Interstellar Hunt content from the android incremental game CIFI (Cell Idle Factory Incremental). Can be used to simulate hunter build performance much quicker than in-game and compare build performance based on elapsed time, stage progression, loot per hour and many other statistics. Builds are stored in easy-to-read config files. Simulations can be parsed into logs to monitor moment-for-moment actions.

Working features:

- 🟩 Borge: including all talents and attributes, up to stage 199
- 🟨 Ozzy: mostly accurate, up to stage 199
  - 🟩 talents and attributes
  - 🟨 DwD talent has a numerical bug that I don't know the correct numbers to currently. It's close but not accurate at the moment
- 🟩 Build comparison: run sims of 2 different builds and see which performed better on each statistic
- 🟩 Sim as many repetitions as desired to get robust predictions
- 🟥 Easily compare and explore best upgrade paths
- 🟥 Log analysis tool: to visualise logs into a graph of hunter HP, showing damage and healing and events to help visually parse the progression of combat
- 🟥 Snappy name

## Table of Contents

- [Hunter-Sim](#hunter-sim)
  - [Installation](#installation)
    - [Windows](#windows)
  - [Usage](#usage)
  - [Frequently Asked Questions and Frequently Encountered Problems](#frequently-asked-questions-and-frequently-encountered-problems)
  - [Contributing](#contributing)
  - [Acknowledgements](#acknowledgements)

## Installation

### Windows

1. Install <ins>at least</ins> Python v3.10.

2. Download the [latest version of the sim](https://github.com/bhnn/hunter-sim/releases) or clone the project onto your drive.

3. Inside the `hunter-sim` folder, open the `builds/` directory and edit either `empty_borge.yaml` or `empty_ozzy.yaml`, depending on which hunter you want to simulate. The file can be renamed to anything you desire for organisational purposes. Input:
    - the upgrade levels of all your main stats (e.g. `hp: 200`, not `hp: 910.33`)
    - your point spent on the talents and attributes screens
    - your levels in any inscryptions and relics listed in the file
    - *Adding, removing or renaming any fixed names in the build config file causes the code to reject it*

4. Open a Powershell window to verify the correct Python version is being accessed by running `python --version`.

5. Then navigate to the `hunter-sim` folder using the `cd` command.
    - eg.: if you downloaded and unpacked the code to `D:\Downloads`, then run `cd D:\Downloads\hunter-sim-v0.1.0`

6. Then install the project's dependencies (read: required modules) into your python installation from (1) using `python -m pip install -r requirements.txt`.

7. You're now set to run simulations. See [Usage](#usage) for an explanation and examples, or [FAQ](#faq) in case you're experiencing issues.

## Usage

Navigate into the root directory of the project, then run the following command to see all available settings.

    python ./hunter-sim/hunter_sim.py -h

- `-f /path/to/file`: Path to a hunter build config file
- `-i num_sims`: How many simulated runs to perform
- `-t processes`: How many processes to use for parallelisation. `-1` for sequential processing.

Examples:

    python ./hunter-sim/hunter_sim.py -f ./builds/borge_lvl37.yaml -i 50 -t -1
Runs 50 simulations of the build `borge_lvl37.yaml` sequentially.

    python ./hunter-sim/hunter_sim.py -f ./builds/borge_lvl40.yaml -i 50 -t 4
Runs 50 simulations of the build `borge_lvl40.yaml` in 4 parallel processes.

    python ./hunter-sim/hunter_sim.py -f ./builds/borge_no_bfb.yaml -c ./builds/borge_3bfb.yaml -i 100
Runs 100 simulations for each build `borge_no_bfb.yaml` and `borge_3bfb.yaml` and compares their performance.

    python ./hunter-sim/hunter_sim.py -f ./builds/experimental_borge.yaml -i 1 -l
Runs a single simulation of the build `experimental_borge.yaml` and saves the corresponding log file to `logs/`.

Optional:

- `-c`: Path to another hunter build config file to compare against the first. The results display of the simulation will change to compare which build performed best on which statistic.
- `-d`: Will save 2 empty config files (Borge and Ozzy) into `builds/` in your current directory. This will always produce config files that contain all build components currently accepted
- `-v`: Prints simulation progress to terminal. Usually they have a limited history and long encounters will produce a lot of messages, so this is best used for short sims.
- `-l`: Produces a log file of the simulation and save it to `logs/` in your current directory. Can be used for runs of any length.

`-v` and `-l` can currently only be used for single simulations

## Frequently Asked Questions and Frequently Encountered Problems

> Which Python version do I need?

The sim needs <ins>at least Python v3.10</ins> to function.

> ModuleNotFoundError: No module named `xyz`

[Installation](#installation) step 6 deals with installing all the required modules to run the code. If you're still seeing this error after running the command, then either 1. an update might have introduced a new package and you need to repeat [Installation](#installation) step 6 or 2. you might have multiple Python versions installed and the modules were installed into the wrong one. Try installing the missing modules using `python -m pip install xyz`.

> Terminal window shows:

    Python 3.10 ...
    Type "help", "copyright", "credits", or "license" for more information.
    >>>
This means you're inside a Python interactive shell (like Powershell or Command Prompt, but for Python). Usually this happens when you open Python from the Windows Search or type `python` into a terminal window. Simply exit the shell by running `exit()` and repeat [Installation](#installation) step 4.

> How does multiprocessing/parallelisation work?

Since the simulations are independent of each other, you can optionally run them in parallel to speed up running all of your repetitions. For this, use the parameter `-t <n>` with any number between `1 <= n < 62`. The most optimal amount of processes seems to be the amount of CPU cores you have installed in your computer. More than 61 processes are not permitted by OS scheduling.

## Contributing

I will work out some contribution guidelines in the future. In the meantime, submitting issues outlining bugs or requests and style-matching pull requests are more than welcome :)

## Acknowledgements

Thank you all for contributing knowledge, stats or ideas! (*in alphabetical order*):

- Aussie Canadian Dutchman
- Chunkeekong
- Feii
- grandmasta
- Nrwoope
- SirRed
- Statphantom
- Theorizon

and of course Octocube Games!
