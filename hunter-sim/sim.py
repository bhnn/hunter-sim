import logging
import statistics
from collections import defaultdict
from copy import deepcopy

from tqdm import tqdm
from units import Borge, Hunter, Void

# import timing


class Simulation:
    def __init__(self, hunter: Hunter) -> None:
        self.current_stage = 0
        self.hunter = hunter

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

    def simulate_combat(self, hunter: Hunter) -> None:
        self.current_stage = 0
        while not hunter.is_dead():
            enemies = Void.spawn_exon12(self.current_stage)
            logging.info(f'Entering STAGE {self.current_stage}')
            for enemy in enemies:
                if enemy.is_dead():
                    continue
                logging.info("")
                logging.info(hunter)
                logging.info(enemy)
                trample_kills = hunter.apply_trample(enemies)
                if trample_kills > 0:
                    logging.info(f'[{hunter.name}]:\tTRAMPLE {trample_kills} enemies')
                    hunter.total_kills += trample_kills
                    continue
                hunter.apply_pog(enemy)
                while not enemy.is_dead() and not hunter.is_dead():
                    if hunter.get_speed() <= enemy.get_speed(): # hunter goes first
                        enemy.regen_hp(hunter.get_speed())
                        hunter.attack(enemy)
                        if enemy.is_dead(): # catch up on regen that happened during the wind-up
                            hunter.regen_hp(hunter.get_speed())
                            continue
                        hunter.regen_hp(enemy.get_speed())
                        enemy.attack(hunter)
                        if hunter.is_dead():
                            return self.current_stage
                    else: # enemy goes first
                        hunter.regen_hp(enemy.get_speed())
                        enemy.attack(hunter)
                        if enemy.is_dead():
                            continue
                        if hunter.is_dead():
                            return self.current_stage
                        enemy.regen_hp(hunter.get_speed())
                        hunter.attack(enemy)
                hunter.total_kills += 1
            self.current_stage += 1
        return self.current_stage

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
        # filename='sanity2_log',
        # filemode='a',
        # level=logging.INFO,
    )
    logging.getLogger().setLevel(logging.WARNING)

    b = Borge('./hunter-sim/builds/new_stats_test.yaml')
    sim = Simulation(b)
    res = sim.run(100)
    sim.pprint_res(res, 'Test')
    # sim.run_upgrade_experiment(200, 35)
    


if __name__ == "__main__":
    main()

# TODO: not sure when to remove stuns. currently removed on receiving damage but no idea how to handle multiple stuns during the same attack wind-up
# or what would happen if a hunter's attack speed would be more than twice as fast than an enemy and it would attack twice in that time