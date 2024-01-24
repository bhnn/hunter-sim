import logging
import statistics
from collections import Counter, defaultdict
from copy import deepcopy
from heapq import heappop as hpop
from heapq import heappush as hpush
from itertools import chain
from math import floor
from typing import List

from hunters import Borge, Hunter
from tqdm import tqdm
from units import Boss, Enemy

# TODO: use SimulationHandler() to manage multiple sims for parallesisation
# TODO: add get_sim_results() to Simulation that returns sim and hunter results
# TODO: build log analyser that translates log into graph of borge hp over time, with little marks for enemy and boss kills

class Simulation():
    def __init__(self, build_path: str) -> None:
        self.build_path = build_path
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

    def run(self, repetitions: int) -> defaultdict:
        return self.__run_sim(repetitions)

    def run_test(self) -> dict:
        self.simulate_combat(self.hunter)
        return self.hunter.get_results()


    def __run_sim(self, repetitions: int) -> defaultdict:
        results = list()
        res = {}
        for _ in tqdm(range(repetitions), leave=False):
            self.hunter = Borge(self.build_path)
            self.hunter.sim = self
            self.simulate_combat(self.hunter)
            results.append(self.hunter.get_results())
            results.append({'elapsed_time': self.elapsed_time})
        for d in results:
            for k, v in d.items():
                res.setdefault(k, []).append(v)
        return res

    def run_upgrade_experiment(self, repetitions: int, stat_boost: int) -> defaultdict:
        res = list()
        for stat in tqdm(['hp', 'power', 'regen', 'damage_reduction', 'evade_chance', 'effect_chance', 'special_chance', 'special_damage', 'speed', 'default']):
            h = deepcopy(self.hunter)
            if stat != 'default':
                h.base_stats[stat] += stat_boost
            print(h)
            r = self.__run_sim(h, repetitions)
            res.append((stat, {k: round(statistics.fmean(v), 2) for k, v in r.items()}))
        sorted_res = sorted(res, key=lambda x: x[1]['total_kills'], reverse=True)
        print(sorted_res)

    def simulate_combat(self, hunter: Hunter):
        self.current_stage = 0
        self.elapsed_time = 0
        self.queue = []
        hpush(self.queue, (self.elapsed_time + hunter.speed, 1, 'hunter'))
        hpush(self.queue, (self.elapsed_time + 1, 3, 'regen'))
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
                hunter.apply_pog(enemy)
                hpush(self.queue, (self.elapsed_time + enemy.speed, 2, 'enemy'))
                # combat loop
                while not enemy.is_dead() and not hunter.is_dead():
                    logging.debug(f'[  QUEUE]:           {self.queue}')
                    _, _, action = hpop(self.queue)
                    match action:
                        case 'hunter':
                            hunter.attack(enemy)
                            hpush(self.queue, (self.elapsed_time + 1 + hunter.speed, 1, 'hunter'))
                            self.elapsed_time += 1
                        case 'enemy':
                            enemy.attack(hunter)
                            if not enemy.is_dead():
                                hpush(self.queue, (self.elapsed_time + 1 + enemy.speed, 2, 'enemy'))
                            self.elapsed_time += 1
                        case 'stun':
                            hunter.apply_stun(enemy, isinstance(enemy, Boss))
                        case 'regen':
                            hunter.regen_hp()
                            enemy.regen_hp()
                            hpush(self.queue, (self.elapsed_time + 1, 3, 'regen'))
                            self.elapsed_time += 1
                        case _:
                            raise ValueError(f'Unknown action: {action}')
                if hunter.is_dead():
                    return self.current_stage
            self.complete_stage()
        raise ValueError('Hunter is dead, no return triggered')

    @staticmethod
    def pprint_res(res_dict: dict, custom_message: str = None) -> None:
        res_dict["enrage_log"] = list(chain.from_iterable(res_dict["enrage_log"]))
        res_dict["first_revive"] = [r[0] for r in res_dict["revive_log"] if r]
        res_dict["second_revive"] = [r[1] for r in res_dict["revive_log"] if r and len(r) > 1]
        final_stages = {i:j/len(res_dict["final_stage"]) for i,j in Counter(res_dict["final_stage"]).items()}
        avg = {k: statistics.fmean(v) for k, v in res_dict.items() if v and type(v[0]) != list}
        std = {k: statistics.stdev(v) for k, v in res_dict.items() if v and type(v[0]) != list}
        out  = f'Average over {len(res_dict["total_kills"])} runs:\t\t> {custom_message} <\n'
        out += f'Main stats:\n'
        out += f'Enrage log: {avg["enrage_log"]:>25.2f}\t(+/- {std["enrage_log"]:>10.2f})\n'
        out += f'Revive stage 1st: {avg["first_revive"]:>19.2f}\t(+/- {std["first_revive"]:>10.2f})\n'
        out += f'Revive stage 2nd: {avg["second_revive"]:>19.2f}\t(+/- {std["second_revive"]:>10.2f})\n'
        out += f'Avg total kills: {avg["total_kills"]:>20.2f}\t(+/- {std["total_kills"]:>10.2f})\n'
        out += f'Elapsed time: {avg["elapsed_time"]/60:>23.2f}m\t(+/- {std["elapsed_time"]/60:>10.2f})\n'
        out += f'Offence:\n'
        out += f'Avg total attacks: {avg["total_attacks"]:>18.2f}\t(+/- {std["total_attacks"]:>10.2f})\n'
        out += f'Avg total damage: {avg["total_damage"]:>19.2f}\t(+/- {std["total_damage"]:>10.2f})\n'
        out += f'Avg total crits: {avg["total_crits"]:>20.2f}\t(+/- {std["total_crits"]:>10.2f})\n'
        out += f'Avg total extra from crits: {avg["total_extra_from_crits"]:>3.2f}\t(+/- {std["total_extra_from_crits"]:>10.2f})\n'
        out += f'Sustain:\n'
        out += f'Avg total taken: {avg["total_taken"]:>20.2f}\t(+/- {std["total_taken"]:>10.2f})\n'
        out += f'Avg total regen: {avg["total_regen"]:>20.2f}\t(+/- {std["total_regen"]:>10.2f})\n'
        out += f'Avg total attacks suffered: {avg["total_attacks_suffered"]:>9.2f}\t(+/- {std["total_attacks_suffered"]:>10.2f})\n'
        out += f'Avg total lifesteal: {avg["total_lifesteal"]:>16.2f}\t(+/- {std["total_lifesteal"]:>10.2f})\n'
        out += f'Defence:\n'
        out += f'Avg total evades: {avg["total_evades"]:>19.2f}\t(+/- {std["total_evades"]:>10.2f})\n'
        out += f'Avg total mitigated: {avg["total_mitigated"]:>16.2f}\t(+/- {std["total_mitigated"]:>10.2f})\n'
        out += f'Effects:\n'
        out += f'Avg total effect procs: {avg["total_effect_procs"]:>13.2f}\t(+/- {std["total_effect_procs"]:>10.2f})\n'
        out += f'Avg total helltouch: {avg["total_helltouch"]:>16.2f}\t(+/- {std["total_helltouch"]:>10.2f})\n'
        out += f'Avg total loth: {avg["total_loth"]:>21.2f}\t(+/- {std["total_loth"]:>10.2f})\n'
        out += f'Avg total potion: {avg["total_potion"]:>19.2f}\t(+/- {std["total_potion"]:>10.2f})\n'
        out += f'Final stage reached:  MAX({max(res_dict["final_stage"])}), MED({floor(statistics.median(res_dict["final_stage"]))}), MIN({min(res_dict["final_stage"])})\n'
        print(out)
        for i,k in enumerate(sorted([*final_stages])):
            print(f'{k:>3d}: {final_stages[k]:>6.2%}   ', "\n" if (i+1) % 5 == 0 and i > 0 else "", end="")

def main():
    logging.basicConfig(
        # filename='nrwoope_log.txt',
        # filemode='w',
        # force=True,
        # level=logging.DEBUG,
    )
    logging.getLogger().setLevel(logging.INFO)

    # sim = Simulation('./builds/aussie_canadian_dutchman.yaml')
    sim = Simulation('./builds/current.yaml')
    res = sim.run(2000)
    # print(json.dumps(res, indent=4))
    sim.pprint_res(res, 'Test')
    # sim.run_upgrade_experiment(200, 35)



if __name__ == "__main__":
    # import timing
    main()


# TODO: with cli, save empty copy of uptodate config file to disk so people know what they need to work with

# TODO: multithread each sim run

# borge hp before relic: 879, after relic: 897 (1), 914 (2), 932 (3) (multiplied in the end, together with ares)

# ozzy 101: 1790, 208.17, 12.53, 0.01, 0.16, 1.84, 2.80s