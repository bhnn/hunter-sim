import logging
import statistics
from collections import defaultdict
from copy import deepcopy
from heapq import heapify
from heapq import heappop as hpop
from heapq import heappush as hpush
from typing import List

from hunters import Borge, Hunter
from tqdm import tqdm
from units import Enemy, Void, Boss

# class Simulation:
#     def __init__(self, hunter: Hunter) -> None:
#         self.current_stage = 0
#         self.hunter = hunter

#     def run(self, repetitions: int) -> defaultdict:
#         return self.__run_sim(self.hunter, repetitions)

#     def __run_sim(self, hunter: Hunter, repetitions: int) -> defaultdict:
#         results = list()
#         res = {}
#         for _ in range(repetitions):
#             h = deepcopy(hunter)
#             self.simulate_combat(h)
#             results.append(h.get_results())
#         for d in results:
#             for k, v in d.items():
#                 res.setdefault(k, []).append(v)
#         return res

#     def run_upgrade_experiment(self, repetitions: int, stat_boost: int) -> defaultdict:
#         res = list()
#         for stat in tqdm(['hp', 'power', 'regen', 'damage_reduction', 'evade_chance', 'effect_chance', 'special_chance', 'special_damage', 'speed', 'default']):
#             h = deepcopy(self.hunter)
#             if stat != 'default':
#                 h.base_stats[stat] += stat_boost
#             print(h)
#             r = self.__run_sim(h, repetitions)
#             del r["total_crits"], r["final_hp"], r["total_regen"], r["survived"]
#             res.append((stat, {k: round(statistics.fmean(v), 2) for k, v in r.items()}))
#         sorted_res = sorted(res, key=lambda x: x[1]['total_kills'], reverse=True)
#         print(sorted_res)

#     def simulate_combat(self, hunter: Hunter) -> None:
#         self.current_stage = 0
#         while not hunter.is_dead():
#             enemies = Void.spawn_exon12(self.current_stage)
#             logging.info(f'Entering STAGE {self.current_stage}')
#             for enemy in enemies:
#                 if enemy.is_dead():
#                     continue
#                 logging.info("")
#                 logging.info(hunter)
#                 logging.info(enemy)
#                 trample_kills = hunter.apply_trample(enemies)
#                 if trample_kills > 0:
#                     logging.info(f'[{hunter.name}]:\tTRAMPLE {trample_kills} enemies')
#                     hunter.total_kills += trample_kills
#                     continue
#                 hunter.apply_pog(enemy)
#                 while not enemy.is_dead() and not hunter.is_dead():
#                     if hunter.get_speed() <= enemy.get_speed(): # hunter goes first
#                         enemy.regen_hp(hunter.get_speed())
#                         hunter.attack(enemy)
#                         if enemy.is_dead(): # catch up on regen that happened during the wind-up
#                             hunter.regen_hp(hunter.get_speed())
#                             continue
#                         hunter.regen_hp(enemy.get_speed())
#                         enemy.attack(hunter)
#                         if hunter.is_dead():
#                             return self.current_stage
#                     else: # enemy goes first
#                         hunter.regen_hp(enemy.get_speed())
#                         enemy.attack(hunter)
#                         if enemy.is_dead():
#                             continue
#                         if hunter.is_dead():
#                             return self.current_stage
#                         enemy.regen_hp(hunter.get_speed())
#                         hunter.attack(enemy)
#                 hunter.total_kills += 1
#             self.current_stage += 1
#         return self.current_stage

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
        for _ in range(repetitions):
            h = deepcopy(hunter)
            self.simulate_combat(h)
            results.append(h.get_results())
        for d in results:
            for k, v in d.items():
                res.setdefault(k, []).append(v)
        return res

    def simulate_combat(self, hunter: Hunter):
        self.current_stage = 0
        self.elapsed_time = 0
        queue = []
        hpush(queue, (self.elapsed_time + hunter.get_speed(), 1, 'hunter'))
        hpush(queue, (self.elapsed_time + 1, 3, 'regen'))
        while not hunter.is_dead():
            logging.info("")
            logging.info(f'Entering STAGE {self.current_stage}')
            self.enemies = Void.spawn_exon12(self.current_stage)
            while self.enemies:
                logging.info(hunter)
                if not isinstance(self.enemies[0], Boss):
                    trample_kills = hunter.apply_trample(self.enemies)
                    if trample_kills > 0:
                        logging.info(f'[{hunter.name:>7}]:\tTRAMPLE {trample_kills} enemies')
                        hunter.total_kills += trample_kills
                        hunter.total_damage += trample_kills * hunter.power
                        self.enemies = self.enemies[trample_kills:]
                        continue
                enemy = self.enemies.pop(0)
                if enemy.is_dead():
                    raise ValueError('Enemy is dead')
                logging.info(enemy)
                hunter.apply_pog(enemy)
                hpush(queue, (self.elapsed_time + enemy.get_speed(), 2, 'enemy'))
                # combat loop
                while not enemy.is_dead() and not hunter.is_dead():
                    self.elapsed_time += 1
                    _, _, action = hpop(queue)
                    match action:
                        case 'hunter':
                            hunter.attack(enemy)
                            hpush(queue, (self.elapsed_time + hunter.get_speed(), 1, 'hunter'))
                        case 'enemy':
                            enemy.attack(hunter)
                            hpush(queue, (self.elapsed_time + enemy.get_speed(), 2, 'enemy'))
                        case 'regen':
                            hunter.regen_hp()
                            enemy.regen_hp()
                            hpush(queue, (self.elapsed_time + 1, 3, 'regen'))
                        case _:
                            raise ValueError(f'Unknown action: {action}')
                if enemy.is_dead():
                    logging.info("")
                    heapify(queue := [(p1, p2, u) for p1, p2, u in queue if u != 'enemy'])
                    hunter.total_kills += 1
                if hunter.is_dead():
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
        out += f'# Stage 100 reached: {res_dict["final_stage"].count(100):>7.2f}'
        print(out)

def main():
    logging.basicConfig(
        # filename='sanity4_log',
        # filemode='w',
        # level=logging.INFO,
    )
    logging.getLogger().setLevel(logging.INFO)

    b = Borge('./hunter-sim/builds/current.yaml')
    sim = Simulation(b)
    res = sim.run(1)
    # sim.pprint_res(res, 'Test')
    print(res)
    # sim.run_upgrade_experiment(200, 35)
    


if __name__ == "__main__":
    main()

# TODO: not sure when to remove stuns. currently removed on receiving damage but no idea how to handle multiple stuns during the same attack wind-up
# or what would happen if a hunter's attack speed would be more than twice as fast than an enemy and it would attack twice in that time

# TODO: if enemy is killed, apply stun to next target. shouldn't be the case (maybe have attack return if a stun occurred?)

# borge hp before relic: 879, after relic: 897 (1), 914 (2), 932 (3)