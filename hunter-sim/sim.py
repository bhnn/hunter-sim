import logging
import queue
import statistics
from collections import Counter, defaultdict
from datetime import timedelta
from heapq import heappop as hpop
from heapq import heappush as hpush
from itertools import chain
from math import floor
from threading import Thread
from typing import List

import yaml
from hunters import Borge, Hunter, Ozzy
from tqdm import tqdm
from units import Boss, Enemy

# TODO: with cli, save empty copy of uptodate config file to disk so people know what they need to work with
# TODO: maybe yield the sims to the handler to speed it up? not sure if it's works like that

class SimulationManager():
    def __init__(self, hunter_config_path: str) -> None:
        self.hunter_config_path = hunter_config_path
        self.task_queue = queue.Queue()
        self.pbar = None
        self.results: List = []

    def __sim_worker(self) -> None:
        while True:
            sim = self.task_queue.get()
            self.results.append(sim.run())
            self.task_queue.task_done()
            self.pbar.update(1)

    def run_sims(self, repetitions: int, threaded: int = -1) -> None:
        # prepare sim instances to run
        with open(self.hunter_config_path, 'r') as f:
            cfg = yaml.safe_load(f)
        match cfg["meta"]["hunter"].lower():
            case "borge":
                hunter_class = Borge
            case "ozzy":
                hunter_class = Ozzy
            case _:
                raise ValueError(f'Unknown hunter type found in config {f}')
        if threaded > -1:
            self.pbar = tqdm(total=repetitions)
            for _ in range(repetitions):
                self.task_queue.put_nowait(Simulation(hunter_class(self.hunter_config_path)))
            
            # start sim workers
            max_cores = threaded
            for _ in range(max_cores):
                t = Thread(target=self.__sim_worker)
                t.daemon = True
                t.start()

            with self.pbar:
                self.task_queue.join()
        else:
            for _ in tqdm(range(repetitions), leave=False):
                self.results.append(Simulation(hunter_class(self.hunter_config_path)).run())
        
        # print results
        res = {}
        for d in self.results:
            for k, v in d.items():
                res.setdefault(k, []).append(v)
        return res

    @staticmethod
    def pprint_res(res_dict: dict, custom_message: str = None, coloured: bool = False) -> None:
        res_dict["enrage_log"] = list(chain.from_iterable(res_dict["enrage_log"]))
        res_dict["first_revive"] = [r[0] for r in res_dict["revive_log"] if r]
        res_dict["second_revive"] = [r[1] for r in res_dict["revive_log"] if r and len(r) > 1]
        if len(res_dict["final_stage"]) > 1:
            avg = {k: statistics.fmean(v) for k, v in res_dict.items() if v and type(v[0]) != list}
            std = {k: statistics.stdev(v) for k, v in res_dict.items() if v and type(v[0]) != list}
        else:
            avg = res_dict
            std = {k: 0 for k in res_dict}
        out = []
        divider = "-" * 10
        c_off = '\033[0m'
        out.append(f'Average over {len(res_dict["total_kills"])} runs:\t\t> {custom_message} <')
        out.append("#" * 56)
        c_on = '\033[38;2;93;101;173m' if coloured else ''
        out.append(f'{c_on}Main stats:{c_off}')
        out.append(f'{c_on}{divider}{c_off}')
        out.append(f'{c_on}Enrage log: {avg["enrage_log"]:>25.2f}\t(+/- {std["enrage_log"]:>10.2f}){c_off}')
        out.append(f'{c_on}Revive stage 1st: {avg["first_revive"]:>19.2f}\t(+/- {std["first_revive"]:>10.2f}){c_off}')
        out.append(f'{c_on}Revive stage 2nd: {avg["second_revive"]:>19.2f}\t(+/- {std["second_revive"]:>10.2f}){c_off}')
        out.append(f'{c_on}Avg total kills: {avg["total_kills"]:>20.2f}\t(+/- {std["total_kills"]:>10.2f}){c_off}')
        out.append(f'{c_on}Elapsed time: {str(timedelta(seconds=round(avg["elapsed_time"], 0))):>23}\t(+/- {str(timedelta(seconds=round(std["elapsed_time"], 0))):>10}){c_off}')
        c_on = '\033[38;2;195;61;3m' if coloured else ''
        out.append(f'{c_on}Offence:{c_off}')
        out.append(f'{c_on}{divider}{c_off}')
        out.append(f'{c_on}Avg total attacks: {avg["total_attacks"]:>18.2f}\t(+/- {std["total_attacks"]:>10.2f}){c_off}')
        out.append(f'{c_on}Avg total damage: {avg["total_damage"]:>19.2f}\t(+/- {std["total_damage"]:>10.2f}){c_off}')
        out.append(f'{c_on}Avg total crits: {avg["total_crits"]:>20.2f}\t(+/- {std["total_crits"]:>10.2f}){c_off}')
        out.append(f'{c_on}Avg total extra from crits: {avg["total_extra_from_crits"]:>3.2f}\t(+/- {std["total_extra_from_crits"]:>10.2f}){c_off}')
        c_on = '\033[38;2;1;163;87m' if coloured else ''
        out.append(f'{c_on}Sustain:{c_off}')
        out.append(f'{c_on}{divider}{c_off}')
        out.append(f'{c_on}Avg total taken: {avg["total_taken"]:>20.2f}\t(+/- {std["total_taken"]:>10.2f}){c_off}')
        out.append(f'{c_on}Avg total regen: {avg["total_regen"]:>20.2f}\t(+/- {std["total_regen"]:>10.2f}){c_off}')
        out.append(f'{c_on}Avg total attacks suffered: {avg["total_attacks_suffered"]:>9.2f}\t(+/- {std["total_attacks_suffered"]:>10.2f}){c_off}')
        out.append(f'{c_on}Avg total lifesteal: {avg["total_lifesteal"]:>16.2f}\t(+/- {std["total_lifesteal"]:>10.2f}){c_off}')
        c_on = '\033[38;2;234;186;1m' if coloured else ''
        out.append(f'{c_on}Defence:{c_off}')
        out.append(f'{c_on}{divider}{c_off}')
        out.append(f'{c_on}Avg total evades: {avg["total_evades"]:>19.2f}\t(+/- {std["total_evades"]:>10.2f}){c_off}')
        out.append(f'{c_on}Avg total mitigated: {avg["total_mitigated"]:>16.2f}\t(+/- {std["total_mitigated"]:>10.2f}){c_off}')
        c_on = '\033[38;2;14;156;228m' if coloured else ''
        out.append(f'{c_on}Effects:{c_off}')
        out.append(f'{c_on}{divider}{c_off}')
        out.append(f'{c_on}Avg total effect procs: {avg["total_effect_procs"]:>13.2f}\t(+/- {std["total_effect_procs"]:>10.2f}){c_off}')
        out.append(f'{c_on}Avg total helltouch: {avg["total_helltouch"]:>16.2f}\t(+/- {std["total_helltouch"]:>10.2f}){c_off}')
        out.append(f'{c_on}Avg total loth: {avg["total_loth"]:>21.2f}\t(+/- {std["total_loth"]:>10.2f}){c_off}')
        out.append(f'{c_on}Avg total potion: {avg["total_potion"]:>19.2f}\t(+/- {std["total_potion"]:>10.2f}){c_off}')
        out.append(f'{c_on}{divider}{c_off}')
        c_on = '\033[38;2;98;65;169m' if coloured else ''
        out.append(f'{c_on}Loot:{c_off}')
        out.append(f'Final stage reached:  MAX({max(res_dict["final_stage"])}), MED({floor(statistics.median(res_dict["final_stage"]))}), AVG({floor(statistics.mean(res_dict["final_stage"]))}), MIN({min(res_dict["final_stage"])})')
        out.append('')
        stage_out = []
        final_stage_pct = {i:j/len(res_dict["final_stage"]) for i,j in Counter(res_dict["final_stage"]).items()}
        for i, k in enumerate(sorted([*final_stage_pct])):
            stage_out.append(f'{k:>3d}: {final_stage_pct[k]:>6.2%}   ' + ("\n" if (i + 1) % 5 == 0 and i > 0 else ""))
        out.append(''.join(stage_out))
        out.append('')
        print('\n'.join(out))


class Simulation():
    def __init__(self, hunter: Hunter) -> None:
        self.hunter: Hunter = hunter
        self.hunter.sim = self
        self.enemies: List[Enemy] = None
        self.current_stage = -1
        self.queue: List[tuple] = []
        self.elapsed_time: int = 0

    def complete_stage(self) -> None:
        self.current_stage += 1
        self.hunter.current_stage += 1

    def spawn_enemies(self, hunter) -> None:
        if self.current_stage % 100 == 0 and self.current_stage > 0:
            self.enemies = [Boss(f'B{self.current_stage:>3}{1:>3}', hunter, self.current_stage, self)]
        else:
            self.enemies = [Enemy(f'E{self.current_stage:>3}{i+1:>3}', hunter, self.current_stage, self) for i in range(10)]

    def run(self) -> defaultdict:
        self.simulate_combat(self.hunter)
        return self.hunter.get_results() | {'elapsed_time': self.elapsed_time}

    def simulate_combat(self, hunter: Hunter) -> None:
        self.current_stage = 0
        self.elapsed_time = 0
        self.queue = []
        hpush(self.queue, (hunter.speed, 1, 'hunter'))
        hpush(self.queue, (self.elapsed_time, 3, 'regen'))
        while not hunter.is_dead():
            logging.debug('')
            logging.debug(f'Entering STAGE {self.current_stage}')
            self.spawn_enemies(hunter)
            while self.enemies:
                logging.debug('')
                logging.debug(hunter)
                if not isinstance(self.enemies[0], Boss):
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
                hpush(self.queue, (round(self.elapsed_time + enemy.speed, 3), 2, 'enemy'))
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

    # def run_upgrade_experiment(self, repetitions: int, stat_boost: int) -> defaultdict:
    #     res = list()
    #     for stat in tqdm(['hp', 'power', 'regen', 'damage_reduction', 'evade_chance', 'effect_chance', 'special_chance', 'special_damage', 'speed', 'default']):
    #         h = deepcopy(self.hunter)
    #         if stat != 'default':
    #             h.base_stats[stat] += stat_boost
    #         print(h)
    #         r = self.__run_sim(h, repetitions)
    #         res.append((stat, {k: round(statistics.fmean(v), 2) for k, v in r.items()}))
    #     sorted_res = sorted(res, key=lambda x: x[1]['total_kills'], reverse=True)
    #     print(sorted_res)

def main():
    import timing
    num_sims = 50
    if num_sims == 1:
        logging.basicConfig(
            # filename='./logs/1_time_advance_log.txt',
            # filemode='w',
            # force=True,
            # level=logging.DEBUG,
        )
        logging.getLogger().setLevel(logging.DEBUG)
    smgr = SimulationManager('./builds/current_borge.yaml')
    res = smgr.run_sims(num_sims, threaded=-1)
    smgr.pprint_res(res, 'Test')


if __name__ == "__main__":
    # import timing
    main()