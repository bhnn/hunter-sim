import argparse
import logging
import os
import sys
from datetime import datetime

import yaml
from hunters import Borge, Ozzy
from sim import SimulationManager
from util.exceptions import BuildConfigError


def main(path: str, compare_path: str, num_sims: int, dump_config: str, threads: int, verbose: bool, log: bool):
    if num_sims > 1 and verbose:
        print("Verbose output is not supported for multiple simulations. Run with `-i 1` to enable verbose output.")
        sys.exit(1)
    if verbose and log:
        print("Logging can only be enabled without console output. Run without `-v` to disable console output.")
        sys.exit(1)
    if dump_config:
        for fn, cls in [('empty_borge.yaml', Borge), ('empty_ozzy.yaml', Ozzy)]:
            # TODO: create dir if it doesn't exist
            with open(os.path.join(os.getcwd(), 'builds', fn), 'w') as f:
                yaml.dump(cls().to_yaml(), f, default_flow_style=False, sort_keys=False)
        sys.exit(0)

    if num_sims == 1 and verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    try:
        if num_sims == 1 and log:
            with open(path, 'r') as f:
                cfg = yaml.safe_load(f)
            logging.basicConfig(
                filename=os.path.join('./logs/', datetime.now().strftime("%Y%m%d-%H%M%S") + f'_{cfg["meta"]["hunter"].lower()}.log'),
                filemode='w',
                force=True,
                level=logging.DEBUG,
            )
        smgr = SimulationManager(path)
        if compare_path:
            import timing
            res = smgr.compare_against(compare_path, num_sims, threaded=threads)
        else:
            import timing
            res = smgr.run(num_sims, threaded=threads)
    except FileNotFoundError:
        print("Build config file not found. Please specify the correct name or run with the -d flag to generate an empty build config file.")
        sys.exit(1)
    except BuildConfigError as e:
        print(e)
        sys.exit(1)



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A simulation tool for Hunters from the CIFI game.")
    parser.add_argument("-f", "--path", type=str, help="Path to a valid build config .yaml file", required=True)
    parser.add_argument("-c", "--compare_builds", type=str, help="Path to a second valid build config .yaml file to compare against the first", dest="compare_path")
    parser.add_argument("-i", "--num-sims", type=int, help="Number of simulations to run", default=100)
    parser.add_argument("-d", "--dump-config", type=str, help="Save an empty config file to the specified path. Defaults to ./builds/")
    parser.add_argument("-t", "--threaded", type=int, help="Number of threads to use for parallelisation. -1 for sequential processing.", default=-1, dest="threads")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print verbose output to stdout")
    parser.add_argument("-l", "--log", action="store_true", help="Write log of simulation to specified path. Currently only works with `-i 1`. Defaults to ./logs/")
    args = parser.parse_args()

    main(**vars(args))