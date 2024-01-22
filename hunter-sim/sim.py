import logging
import statistics
from collections import defaultdict
from copy import deepcopy
from heapq import heapify
from heapq import heappop as hpop
from heapq import heappush as hpush
from math import floor
from typing import List

from hunters import Borge, Hunter
from tqdm import tqdm
from units import Boss, Enemy, Void


class Simulation():
    def __init__(self, hunter: Hunter) -> None:
        self.hunter: Hunter = hunter
        self.enemies: List[Enemy] = None
        self.current_stage = -1
        self.elapsed_time: int = 0

    def complete_stage(self) -> None:
        self.current_stage += 1
        self.hunter.current_stage += self.hunter.current_stage + 1


    def run(self, repetitions: int) -> defaultdict:
        return self.__run_sim(self.hunter, repetitions)

    def __run_sim(self, hunter: Hunter, repetitions: int) -> defaultdict:
        results = list()
        res = {}
        for _ in tqdm(range(repetitions), leave=False):
            h = deepcopy(hunter)
            self.simulate_combat(h)
            results.append(h.get_results())
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
            del r["total_crits"], r["final_hp"], r["total_regen"], r["survived"]
            res.append((stat, {k: round(statistics.fmean(v), 2) for k, v in r.items()}))
        sorted_res = sorted(res, key=lambda x: x[1]['total_kills'], reverse=True)
        print(sorted_res)

    def simulate_combat(self, hunter: Hunter):
        self.current_stage = 0
        self.elapsed_time = 0
        queue = []
        hunter.sim_queue_entry = (self.elapsed_time + hunter.get_speed(), 1, 'hunter')
        hpush(queue, hunter.sim_queue_entry)
        hpush(queue, (self.elapsed_time + 1, 3, 'regen'))
        while not hunter.is_dead():
            logging.debug("")
            logging.debug(f'Entering STAGE {self.current_stage}')
            self.enemies = Void.spawn_exon12(self.current_stage)
            while self.enemies:
                logging.debug(hunter)
                if not isinstance(self.enemies[0], Boss):
                    trample_kills = hunter.apply_trample(self.enemies)
                    if trample_kills > 0:
                        logging.debug(f'[{hunter.name:>7}]:\tTRAMPLE {trample_kills} enemies')
                        hunter.total_kills += trample_kills
                        hunter.total_damage += trample_kills * hunter.power
                        self.enemies = self.enemies[trample_kills:]
                        continue
                enemy = self.enemies.pop(0)
                logging.debug(enemy)
                hunter.apply_pog(enemy)
                enemy.sim_queue_entry = (self.elapsed_time + enemy.get_speed(), 2, 'enemy')
                hpush(queue, enemy.sim_queue_entry)
                # combat loop
                while not enemy.is_dead() and not hunter.is_dead():
                    self.elapsed_time += 1
                    _, _, action = hpop(queue)
                    match action:
                        case 'hunter':
                            events = hunter.attack(enemy)
                            if "stun" in events:
                                hpush(queue, (0, 0, 'stun'))
                            hunter.sim_queue_entry = (self.elapsed_time + hunter.get_speed(), 1, 'hunter')
                            hpush(queue, hunter.sim_queue_entry)
                        case 'enemy':
                            enemy.attack(hunter)
                            enemy.sim_queue_entry = (self.elapsed_time + enemy.get_speed(), 2, 'enemy')
                            hpush(queue, enemy.sim_queue_entry)
                        case 'regen':
                            hunter.regen_hp()
                            enemy.regen_hp()
                            hpush(queue, (self.elapsed_time + 1, 3, 'regen'))
                        case 'stun':
                            queue.remove(enemy.sim_queue_entry)
                            enemy.sim_queue_entry = (enemy.sim_queue_entry[0] + hunter.apply_stun(enemy), enemy.sim_queue_entry[1], enemy.sim_queue_entry[2])
                            hpush(queue, enemy.sim_queue_entry)
                        case _:
                            raise ValueError(f'Unknown action: {action}')
                if enemy.is_dead():
                    logging.debug("")
                    heapify(queue := [(p1, p2, u) for p1, p2, u in queue if u != 'enemy'])
                    hunter.total_kills += 1
                if hunter.is_dead():
                    hunter.elapsed_time = self.elapsed_time
                    return self.current_stage
            self.complete_stage()
        raise ValueError('Hunter is dead, no return triggered')

    @staticmethod
    def pprint_res(res_dict: dict, custom_message: str = None) -> None:
        avg = {k: statistics.fmean(v) for k, v in res_dict.items()}
        std = {k: statistics.stdev(v) for k, v in res_dict.items()}
        out  = f'Average over {len(res_dict["total_kills"])} runs:\t\t> {custom_message} <\n'
        out += f'Avg total damage: {avg["total_damage"]:>10.2f}\t(+/- {std["total_damage"]:>7.2f})\n'
        out += f'Avg total regen: {avg["total_regen"]:>11.2f}\t(+/- {std["total_regen"]:>7.2f})\n'
        out += f'Avg total crits: {avg["total_crits"]:>11.2f}\t(+/- {std["total_crits"]:>7.2f})\n'
        out += f'Avg total kills: {avg["total_kills"]:>11.2f}\t(+/- {std["total_kills"]:>7.2f})\n'
        out += f'Avg final hp: {avg["final_hp"]:>14.2f}\t(+/- {std["final_hp"]:>7.2f})\n'
        out += f'Elapsed time: {avg["elapsed_time"]/60:>14.2f}min\t(+/- {std["elapsed_time"]/60:>7.2f})\n'
        out += f'Survival %: {avg["survived"]*100:>16.2f}\t(+/- {std["survived"]*100:>7.2f})\n'
        out += f'Final stage reached:  MAX({max(res_dict["final_stage"])}, MED({floor(statistics.median(res_dict["final_stage"]))}), MIN({min(res_dict["final_stage"])}))'
        print(out)

def main():
    logging.basicConfig(
        filename='boss_log',
        filemode='w',
        level=logging.INFO,
    )
    logging.getLogger().setLevel(logging.DEBUG)

    b = Borge('./hunter-sim/builds/boss_sanity.yaml')
    sim = Simulation(b)
    res = sim.run(1)
    print(res)
    # sim.pprint_res(res, 'Test')
    # sim.run_upgrade_experiment(200, 35)



if __name__ == "__main__":
    main()

# TODO: not sure when to remove stuns. currently removed on receiving damage but no idea how to handle multiple stuns during the same attack wind-up
# or what would happen if a hunter's attack speed would be more than twice as fast than an enemy and it would attack twice in that time

# TODO: have hunter compare build config file to internal empty config dict to see if any keys are missing. with cli, save empty copy of uptodate config file to disk so people know what they need to work with

# TODO: check stun. apply only in the match 'stun' part and make sure that this works for bosses and regular mobs after they spawn

# TODO: add all stats from the game to the sim

# borge hp before relic: 879, after relic: 897 (1), 914 (2), 932 (3) (multiplied in the end, together with ares)

# ozzy 101: 1790, 208.17, 12.53, 0.01, 0.16, 1.84, 2.80s