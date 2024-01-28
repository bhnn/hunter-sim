import argparse
import timing
import logging
from sim import SimulationManager
import yaml
import os
from hunters import Borge, Ozzy
from datetime import datetime
from util.errors import BuildConfigError

def main(path: str, num_sims: int, dump_config: str, threaded: int, verbose: bool, log: bool):
    if dump_config:
        for fn, cls in [('empty_borge.yaml', Borge), ('empty_ozzy.yaml', Ozzy)]:
            # create dir if it doesn't exist
            with open(os.path.join(os.getcwd(), 'builds', fn), 'w') as f:
                yaml.dump(cls().to_yaml(), f, default_flow_style=False, sort_keys=False)
        return 0
    if num_sims == 1 and verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    if num_sims == 1 and log:
        logging.basicConfig(
            filename=os.path.join('./logs/', datetime.now().strftime("%Y%m%d-%H%M%S") + '.log'), #TODO which hunter?
            filemode='w',
            force=True,
            level=logging.DEBUG,
        )
    try:
        smgr = SimulationManager(path)
    except FileNotFoundError:
        print("No build config found. Please run with the -d flag to generate an empty build config file.")
        return 1
    except BuildConfigError as e:
        print(e.message)
        return 1
    res = smgr.run_sims(num_sims, threaded=threaded)
    smgr.pprint_res(res, 'Test')



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A simulation tool for Hunters from the CIFI game.")
    parser.add_argument("-f", "--path", type=str, help="Path to a valid build config .yaml file", required=True)
    parser.add_argument("-i", "--num-sims", type=int, help="Number of simulations to run", default=100)
    parser.add_argument("-d", "--dump-config", type=str, help="Save an empty config file to the specified path. Defaults to ./builds/")
    parser.add_argument("-t", "--threaded", type=int, help="Number of threads to use for parallelisation. -1 for sequential processing.", default=-1)
    parser.add_argument("-v", "--verbose", action="store_true", help="Print verbose output to stdout")
    parser.add_argument("-l", "--log", action="store_true", help="Write log of simulation to specified path. Currently only works with `-i 1`. Defaults to ./logs/")
    args = parser.parse_args()

    main(**vars(args))