# Hunter-Sim

A simulation of the Interstellar Hunt content from the android incremental game CIFI (Cell Idle Factory Incremental). Can be used to simulate hunter build performance much quicker than in-game and compare build performance based on elapsed time, stage progression, loot per hour and many other statistics. Builds are stored in easy-to-read config files. Simulations can be parsed into logs to monitor moment-for-moment actions.

Working features:

- 🟩 Borge: including all talents and attributes, up to stage 199
- 🟨 Ozzy: mostly accurate, up to stage 199
  - 🟩 talents and attributes
  - 🟨 DwD talent has a numerical bug that I don't know the correct numbers to currently. It's close but not accurate at the moment
- 🟩 Build comparison: run sims of 2 different builds and see which performed better on each statistic
- 🟥 Easily compare and explore best upgrade paths
- 🟥 Log analysis tool: to visualise logs into a graph of hunter HP, showing damage and healing and events to help visually parse the progression of combat
- 🟥 Snappy name

## Table of Contents

- [Hunter-Sim](#hunter-sim)
  - [Installation](#installation)
  - [Usage](#usage)
  - [Contributing](#contributing)
  - [Acknowledgements](#acknowledgements)

## Installation

1) Install at least Python v3.10 or create a virtual environment of at least Python v3.10 using the tool of your choice (pyenv, Anaconda, etc).

2) [Download the latest version](https://github.com/bhnn/hunter-sim/releases) or clone the project onto your drive, then install its dependencies into your python environment from (1) using `pip install -r requirements.txt`.

## Usage

Navigate into the root directory of the project, then run the following command to see all available settings.

    python ./hunter-sim/hunter_sim.py -h

- `-f /path/to/file`: Path to a hunter build config file
- `-i num_sims`: How many simulated runs to perform
- `-t threads`: How many threads to use for parallelisation. `-1` for sequential processing.

Examples:

    python ./hunter-sim/hunter_sim.py -f ./builds/borge_lvl37.yaml -i 50 -t -1
Runs 50 simulations of the build `borge_lvl37.yaml` sequentially.

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
