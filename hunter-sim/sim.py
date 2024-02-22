import logging
import statistics
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import timedelta
from heapq import heappop as hpop
from heapq import heappush as hpush
from itertools import chain
from math import floor
from string import capwords
from typing import Dict, Generator, List, Tuple

import rich
from hunters import Borge, Hunter, Ozzy
from tqdm import tqdm
from units import Boss, Enemy


def sim_worker(hunter_class: Hunter, config_dict: Dict) -> None:
    """Worker process for running simulations in parallel.
    """
    return Simulation(hunter_class(config_dict)).run()

class SimulationManager():
    def __init__(self, hunter_config_dict: Dict) -> None:
        self.hunter_config_dict = hunter_config_dict
        self.results: List = []

    def run(self, repetitions: int, num_processes: int = -1, show_stats: bool = True) -> None:
        """Run simulations and print results.

        Args:
            repetitions (int): Number of simulations to run.
            num_processes (int, optional): Number of processes to use for parallelisation. Defaults to -1, which processes runs sequentially.
            show_stats (bool, optional): Whether to show combat statistics after the simulation, only the stage breakdown and loot. Defaults to True.
        """
        res = self.__run_sims(repetitions, num_processes)
        avg, std = self.prepare_results(res)
        self.display_stats(avg, std, show_stats)

    def compare_against(self, compare_dict: str, repetitions: int, num_processes: int = -1, show_stats: bool = True) -> None:
        """Run simulations for 2 builds, compare results and print.

        Args:
            compare_path (str): Path to valid build config file to compare against the current hunter build.
            repetitions (int): Number of simulations to run.
            num_processes (int, optional): Number of processes to use for parallelisation. Defaults to -1, which processes runs sequentially.
            show_stats (bool, optional): Whether to show combat statistics after the simulation, only the stage breakdown and loot. Defaults to True.
        """
        print('BUILD 1:')
        res = self.__run_sims(repetitions, num_processes)
        self.hunter_config_dict = compare_dict
        print('BUILD 2:')
        res_c = self.__run_sims(repetitions, num_processes)
        (res, _), (res_c, _) = self.prepare_results(res), self.prepare_results(res_c)
        res, res_c = self.make_comparable(res, res_c)
        self.display_stats(res, res_c, show_stats)

    def __run_sims(self, repetitions: int, num_processes: int = -1) -> dict:
        """Run simulations and return results.

        Args:
            repetitions (int): Number of simulations to run.
            threaded (int, optional): Number of processes to use for parallelisation. Defaults to -1, which processes runs sequentially.

        Raises:
            ValueError: Unknown hunter type found in config

        Returns:
            dict: Results of simulations.
        """
        # prepare sim instances to run
        match self.hunter_config_dict["meta"]["hunter"].lower():
            case "borge":
                hunter_class = Borge
            case "ozzy":
                hunter_class = Ozzy
        hunter_class(self.hunter_config_dict).show_build()
        if num_processes > 0:
            with ProcessPoolExecutor(max_workers=num_processes) as e:
                self.results = list(tqdm(e.map(sim_worker, [hunter_class] * repetitions, [self.hunter_config_dict] * repetitions), total=repetitions, leave=True))
        else:
            for _ in tqdm(range(repetitions), leave=False):
                self.results.append(Simulation(hunter_class(self.hunter_config_dict)).run())
        
        # prepare results
        res = {'hunter': hunter_class}
        for d in self.results:
            for k, v in d.items():
                res.setdefault(k, []).append(v)
        return res

    @classmethod
    def prepare_results(cls, res_dict: Dict) -> Dict:
        res_avg, res_std = {}, {}
        hunter = res_dict.pop('hunter')
        # Enrages
        enrage = {'enrage_stacks:_1st_boss': [], 'enrage_stacks:_2nd_boss': [], 'enrage_stacks:_3rd_boss': []}
        for e in res_dict.pop('enrage_log'):
            try:
                enrage['enrage_stacks:_1st_boss'].append(e[0])
                enrage['enrage_stacks:_2nd_boss'].append(e[1])
                enrage['enrage_stacks:_3rd_boss'].append(e[2])
            except:
                pass
        res_dict = res_dict | enrage
        # Revives
        revives = {'first_revive_stage': [], 'second_revive_stage': []}
        for e in res_dict.pop("revive_log"):
            try:
                revives['first_revive_stage'].append(e[0])
                revives['second_revive_stage'].append(e[1])
            except:
                pass
        res_dict = res_dict | revives
        # Loot
        res_dict['loot_per_hour'] = [(res_dict['total_loot'][i] / (res_dict['elapsed_time'][i] / (60 * 60))) for i in range(len(res_dict['total_loot']))]
        # compute averages and standard deviations
        if len(res_dict['elapsed_time']) > 1:
            avg = {k: statistics.fmean(v) for k, v in res_dict.items() if v and type(v[0]) != list}
            std = {k: statistics.stdev(v) for k, v in res_dict.items() if v and type(v[0]) != list}
        else:
            avg = dict()
            for k, v in res_dict.items():
                if type(v) == list and len(v) == 1:
                    avg[k] = v[0]
            std = {k: 0 for k in res_dict}
        # declare which stats belong to which categories
        output_format = {
            'main': ['elapsed_time', 'kills', 'first_revive_stage', 'second_revive_stage', 'enrage_stacks:_1st_boss', 'enrage_stacks:_2nd_boss', 'enrage_stacks:_3rd_boss'],
            'offence': ['attacks', 'damage', 'crits', 'extra_damage_from_crits', 'multistrikes', 'extra_damage_from_ms', 'decay_damage', 'extra_damage_from_crippling_shots'],
            'sustain': ['damage_taken', 'regenerated_hp', 'attacks_suffered', 'lifesteal'],
            'defence': ['evades', 'trickster_evades', 'mitigated_damage'],
            'effects': ['effect_procs', 'stun_duration_inflicted', 'helltouch_barrier', 'life_of_the_hunt_healing', 'echo_bullets', 'unfair_advantage_healing'],
            'loot*': ['loot_per_hour'],
        }
        for k, v in output_format.items():
            res_avg[k] = {val: avg[val] for val in v if val in avg}
            res_std[k] = {val: std[val] for val in v if val in std}
        # custom formatting
        res_avg['main']['elapsed_time'] = timedelta(seconds=round(avg["elapsed_time"]))
        res_std['main']['elapsed_time'] = timedelta(seconds=round(std["elapsed_time"]))
        res_avg['effects']['stun_duration_inflicted'] = timedelta(seconds=round(avg['stun_duration_inflicted']))
        res_std['effects']['stun_duration_inflicted'] = timedelta(seconds=round(std['stun_duration_inflicted']))
        res_avg['loot*'].update({'best_lph': max(res_dict['loot_per_hour']), 'worst_lph': min(res_dict['loot_per_hour'])})
        res_std['loot*'].update({'best_lph': 0, 'worst_lph': 0})
        res_avg['final_stage'] = {'max': max(res_dict['final_stage']), 'med': floor(statistics.median(res_dict['final_stage'])), 'avg': floor(statistics.mean(res_dict['final_stage'])), 'min': min(res_dict['final_stage'])}
        res_avg['is_comparison'] = False
        return res_avg, res_std

    @classmethod
    def make_comparable(cls, dict1: Dict, dict2: Dict) -> Tuple[Dict, Dict]:
        res, diff = {}, {}
        res['is_comparison'] = not dict1.pop('is_comparison')
        for k, v in dict1.items():
            if k not in ['final_stage']:
                res[k], diff[k] = {}, {}
                for vk in v:
                    if vk not in ['elapsed_time', 'worst_lph', 'enrage_stacks:_1st_boss', 'enrage_stacks:_2nd_boss', 'enrage_stacks:_3rd_boss']:
                        if dict1[k][vk] > dict2[k][vk]:
                            res[k][vk] = dict1[k][vk] - dict2[k][vk]
                            diff[k][vk] = (dict1[k][vk] / dict2[k][vk]) - 1 if dict2[k][vk] != 0 else float('inf') # BUILD 1
                        else:
                            res[k][vk] = dict2[k][vk] - dict1[k][vk]
                            # negative value signals output function that this is build2 instead of 1
                            diff[k][vk] = -1 * ((dict2[k][vk] / dict1[k][vk]) - 1) if dict1[k][vk] != 0 else -1 # BUILD 2
                    else:
                        if dict2[k][vk] > dict1[k][vk]:
                            res[k][vk] = dict2[k][vk] - dict1[k][vk]
                            diff[k][vk] = (dict2[k][vk] / dict1[k][vk]) - 1 if dict1[k][vk] != 0 else -1 # BUILD 1
                        else:
                            res[k][vk] = dict1[k][vk] - dict2[k][vk]
                            diff[k][vk] = -1 * ((dict1[k][vk] / dict2[k][vk]) - 1) if dict2[k][vk] != 0 else float('inf') # BUILD 2
        res.update({'final_stage': {'build_1': dict1['final_stage'], 'build_2': dict2['final_stage']}})
        return res, diff

    @classmethod
    def display_stats(cls, dict1: Dict, dict2: Dict, show_stats: bool) -> None:
        def get_all_values(d: Dict) -> Generator:
            for _, v in d.items():
                if not isinstance(v, dict):
                    if not isinstance(v, timedelta):
                        yield v
                else:
                    yield from get_all_values(v)

        console = rich.get_console()
        # base table
        table = rich.table.Table(title="Combat Statistics", show_header=True, header_style="bold dim cyan", caption='*) Loot values are arbitrary and for build comparison only.')
        table.add_column("Category", style="dim cyan")
        table.add_column("Statistic", style="cyan")
        if is_comparison := dict1.pop('is_comparison'):
            # add diff, qualifier and winner columns for comparisons, max_width calc without decimals (2nd dict is just "BUILD 1/2")
            table.add_column("Average diff.", justify='right', style="yellow")
            table.add_column("Qual.", justify='left', style="dim yellow")
            table.add_column(r"% diff", justify='right', style="magenta")
            table.add_column("Winner", justify='center', style="magenta")
        else:
            # add average and stdev columns for regular runs, max_width calc with decimals
            table.add_column("Average", justify='right', style="yellow")
            table.add_column("+/- Std Dev", justify='right', style="dim yellow")
        keys_to_display = ['main', 'offence', 'sustain', 'defence', 'effects', 'loot*'] if show_stats else ['loot*']
        max_width_avg = max([max(len(f'{k:,.2f}') for k in get_all_values(dict1))])
        max_width_std = max([max(len(f'{k:,.2f}') for k in get_all_values(dict2))])
        for k in keys_to_display:
            last_key = ''
            for subkey in dict1[k]:
                main_cat = capwords(k if k != last_key else '')
                if subkey in ['best_lph', 'worst_lph']:
                    cstat = ' '.join([capwords(subkey.split('_')[0]), 'LPH'])
                else:
                    cstat = ' '.join(capwords(subkey).split('_'))
                val = f'{str(dict1[k][subkey]):>{max_width_avg}}' if isinstance(dict1[k][subkey], timedelta) else f'{dict1[k][subkey]:>{max_width_avg},.2f}'
                if is_comparison:
                    if subkey in ['worst_lph']:
                        qual = 'less'
                    elif subkey in ['elapsed_time']:
                        qual = 'faster'
                    elif subkey in ['enrage_stacks:_1st_boss', 'enrage_stacks:_2nd_boss', 'enrage_stacks:_3rd_boss']:
                        qual = 'fewer'
                    elif subkey in ['first_revive_stage', 'second_revive_stage']:
                        qual = 'later'
                    else:
                        qual = 'more'
                    if dict2[k][subkey] > 0:
                        diff = f'{abs(dict2[k][subkey]):>{max_width_std},.2%}'
                        winner = '1'
                    elif dict2[k][subkey] < 0:
                        diff = f'{abs(dict2[k][subkey]):>{max_width_std},.2%}'
                        winner = '2'
                    else:
                        diff = '-'
                        winner = '-'
                    table.add_row(main_cat, cstat, val, qual, diff, winner)
                else:
                    stdev = f'{str(dict2[k][subkey]):>{max_width_std}}' if isinstance(dict1[k][subkey], timedelta) else f'{dict2[k][subkey]:>{max_width_std},.2f}'
                    table.add_row(main_cat, cstat, val, stdev)
                if last_key != k:
                    # so the main category is only shown everytime it changes, makes for a less busy table
                    last_key = k
            table.add_section()
        console.print(table)
        # TODO: add final stage to table as new section, not looking good like this
        # grid = rich.table.Table(title="Final stage", show_header=True, box=None, header_style="bold dim cyan" )
        # grid.add_column("Final stage", justify='center', style="dim cyan")
        # grid.add_column("Max", justify='right', style="cyan")
        # grid.add_column("Med", justify='right', style="cyan")
        # grid.add_column("Avg", justify='right', style="cyan")
        # grid.add_column("Min", justify='right', style="cyan")
        # grid.add_row(
        #     'Build 1',
        #     str(dict1['final_stage']['build_1']['max']),
        #     str(dict1['final_stage']['build_1']['med']),
        #     str(dict1['final_stage']['build_1']['avg']),
        #     str(dict1['final_stage']['build_1']['min'])
        # )
        # grid.add_row(
        #     'Build 2',
        #     str(dict1['final_stage']['build_2']['max']),
        #     str(dict1['final_stage']['build_2']['med']),
        #     str(dict1['final_stage']['build_2']['avg']),
        #     str(dict1['final_stage']['build_2']['min'])
        # )
        # console.print(grid)


class Simulation():
    def __init__(self, hunter: Hunter) -> None:
        self.hunter: Hunter = hunter
        self.hunter.sim = self
        self.enemies: List[Enemy] = None
        self.current_stage = -1
        self.queue: List[tuple] = []
        self.elapsed_time: int = 0

    def complete_stage(self) -> None:
        """Increment stage counter for simulation and hunter.
        """
        self.current_stage += 1
        self.hunter.complete_stage()

    def spawn_enemies(self, hunter) -> None:
        """Spawn enemies for the current stage.

        Args:
            hunter (Hunter): Hunter instance.
        """
        if self.current_stage % 100 == 0 and self.current_stage > 0:
            self.enemies = [Boss(f'B{self.current_stage:>3}{1:>3}', hunter, self.current_stage, self)]
        else:
            self.enemies = [Enemy(f'E{self.current_stage:>3}{i+1:>3}', hunter, self.current_stage, self) for i in range(10)]

    def run(self) -> Dict:
        """Run a single simulation.

        Returns:
            defaultdict: Results of the simulation.
        """
        self.simulate_combat(self.hunter)
        return self.hunter.get_results() | {'elapsed_time': self.elapsed_time}

    def simulate_combat(self, hunter: Hunter) -> None:
        """Simulate combat behaviour for a hunter.

        Args:
            hunter (Hunter): Hunter instance.

        Raises:
            ValueError: Raised when encountering unknown actions.
            ValueError: Raised when the hunter dies and no return is triggered.
        """
        self.current_stage = 0
        self.elapsed_time = 0
        self.queue = []
        hpush(self.queue, (round(hunter.speed, 3), 1, 'hunter'))
        hpush(self.queue, (self.elapsed_time, 3, 'regen'))
        while not hunter.is_dead():
            logging.debug('')
            logging.debug(f'Entering STAGE {self.current_stage}')
            self.spawn_enemies(hunter)
            while self.enemies:
                logging.debug('')
                logging.debug(hunter)
                if 'trample' in hunter.mods and hunter.mods['trample'] and not isinstance(self.enemies[0], Boss):
                    trample_kills = hunter.apply_trample(self.enemies)
                    if trample_kills > 0:
                        logging.debug(f'[{hunter.name:>7}]:\tTRAMPLE {trample_kills} enemies')
                        hunter.total_kills += trample_kills
                        hunter.total_attacks += 1
                        hunter.total_damage += trample_kills * hunter.power
                        self.enemies = [e for e in self.enemies if not e.is_dead()]
                        continue
                enemy = self.enemies.pop(0)
                logging.debug(enemy)
                enemy.queue_initial_attack()
                # combat loop
                while not enemy.is_dead() and not hunter.is_dead():
                    logging.debug(f'[  QUEUE]:           {self.queue}')
                    prev_time, _, action = hpop(self.queue)
                    match action:
                        case 'hunter':
                            hunter.attack(enemy)
                            hpush(self.queue, (round(prev_time + hunter.speed, 3), 1, 'hunter'))
                        case 'enemy':
                            enemy.attack(hunter)
                            if not enemy.is_dead():
                                hpush(self.queue, (round(prev_time + enemy.speed, 3), 2, 'enemy'))
                        case 'stun':
                            hunter.apply_stun(enemy, isinstance(enemy, Boss))
                        case 'hunter_special':
                            hunter.attack(enemy)
                        case 'enemy_special':
                            enemy.attack_special(hunter)
                            if not enemy.is_dead():
                                hpush(self.queue, (round(prev_time + enemy.speed2, 3), 2, 'enemy_special'))
                        case 'regen':
                            hunter.regen_hp()
                            enemy.regen_hp()
                            self.elapsed_time += 1
                            hpush(self.queue, (self.elapsed_time, 3, 'regen'))
                        case _:
                            raise ValueError(f'Unknown action: {action}')
                if hunter.is_dead():
                    return
            self.complete_stage()
        raise ValueError('Hunter is dead, no return triggered')


def main():
    num_sims = 25
    if num_sims == 1:
        logging.basicConfig(
            filename='./logs/ozzy_test.txt',
            filemode='w',
            force=True,
            level=logging.DEBUG,
        )
        logging.getLogger().setLevel(logging.DEBUG)
    smgr = SimulationManager('./builds/current_borge.yaml')
    smgr.run(num_sims, threaded=4)


if __name__ == "__main__":
    main()