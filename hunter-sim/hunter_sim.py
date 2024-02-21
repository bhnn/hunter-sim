import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml
from hunters import Borge, Ozzy
from sim import SimulationManager
from util.exceptions import BuildConfigError


def main(path: str, compare_path: str, num_sims: int, show_stats: bool, dump_config: str, processes: int, verbose: bool, log: bool):
    """Main entry point for the simulation tool.

    Args:
        path (str): Path to a valid build config file
        compare_path (str): Optional: path to a second valid build config file to compare against the first
        num_sims (int): Number of simulations to run
        show_stats (bool): Whether to show combat statistics after the simulation, only the stage breakdown and loot
        dump_config (str): Optional: whether to dump empty build config files to ./builds/ directory and exit
        threads (int): Number of threads to use for parallelisation. -1 for sequential processing.
        verbose (bool): Whether to print verbose output to stdout
        log (bool): Whether to write log of simulation to specified path. Currently only works with `-i 1`. Defaults to ./logs/
    """
    if processes == 0 or processes > 61:
        print("hunter_sim.py: error: number of parallel processes cannot be 0 or larger than 61.")
        sys.exit(1)
    if num_sims > 1 and verbose:
        print("hunter_sim.py: error: verbose output is not supported for multiple simulations. Run with `-i 1` to enable verbose output.")
        sys.exit(1)
    if verbose and log:
        print("hunter_sim.py: error: logging can only be enabled without console output. Run without `-v` to disable console output.")
        sys.exit(1)
    if dump_config:
        for fn, cls in [('empty_borge.yaml', Borge), ('empty_ozzy.yaml', Ozzy)]:
            build_dir = os.path.join(os.getcwd(), 'builds')
            Path(build_dir).mkdir(parents=True, exist_ok=True)
            with open(os.path.join(build_dir, fn), 'w') as f:
                yaml.dump(cls.load_dummy(), f, default_flow_style=False, sort_keys=False)
        sys.exit(0)
    if not path and not dump_config:
        print("hunter_sim.py: error: the following arguments are required: -f/--path")
        sys.exit(1)
    if num_sims == 1 and verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    try:
        with open(path, 'r') as f:
            cfg1 = yaml.safe_load(f)
        if cfg1["meta"]["hunter"].lower() not in ["borge", "ozzy"]:
            print("hunter_sim.py: error: invalid hunter found in primary build config file. Please specify a valid hunter.")
            sys.exit(1)
        if compare_path:
            with open(compare_path, 'r') as f:
                cfg2 = yaml.safe_load(f)
            if cfg2["meta"]["hunter"].lower() not in ["borge", "ozzy"]:
                print("hunter_sim.py: error: invalid hunter found in secondary build config file. Please specify a valid hunter.")
                sys.exit(1)
            if cfg1["meta"]["hunter"] != cfg2["meta"]["hunter"]:
                print("hunter_sim.py: error: cannot compare builds of different hunters")
                sys.exit(1)
        if num_sims == 1 and log:
            log_dir = os.path.join(os.getcwd(), 'logs')
            Path(log_dir).mkdir(parents=True, exist_ok=True)
            logging.basicConfig(
                filename=os.path.join(log_dir, datetime.now().strftime("%Y%m%d-%H%M%S") + f'_{Path(path).stem}.log'),
                filemode='w',
                force=True,
                level=logging.DEBUG,
            )
        smgr = SimulationManager(cfg1)
        if compare_path:
            import timing
            smgr.compare_against(cfg2, num_sims, num_processes=processes, show_stats=show_stats)
        else:
            import timing
            smgr.run(num_sims, num_processes=processes, show_stats=show_stats)
    except FileNotFoundError:
        print("hunter_sim.py: error: build config file not found. Please specify the correct name or run with the -d flag to generate an empty build config file.")
        sys.exit(1)
    except BuildConfigError as e:
        print(e)
        sys.exit(1)



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A simulation tool for Hunters from the CIFI game.")
    parser.add_argument("-f", "--path", type=str, help="Path to a valid build config .yaml file")
    parser.add_argument("-c", "--compare_builds", type=str, help="Path to a second valid build config .yaml file to compare against the first", dest="compare_path")
    parser.add_argument("-i", "--num-sims", type=int, help="Number of simulations to run", default=100)
    parser.add_argument("-s", "--no-stats", action="store_false", help="Suppresses display of combat statistics after the simulation, only the stage breakdown and loot.", dest="show_stats")
    parser.add_argument("-d", "--dump-config", action="store_true", help="Save an empty config file to ./builds/ directory and exits.")
    parser.add_argument("-t", "--processes", type=int, help="Number of processes to use for parallelisation. -1 for sequential processing.", default=-1, dest="processes")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print simulation progress to stdout")
    parser.add_argument("-l", "--log", action="store_true", help="Write log of simulation to specified path. Currently only works with `-i 1`. Defaults to ./logs/")
    args = parser.parse_args()

    main(**vars(args))