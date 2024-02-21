import logging
import statistics
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import timedelta
from heapq import heappop as hpop
from heapq import heappush as hpush
from itertools import chain
from math import floor
from typing import List, Tuple

import yaml
from hunters import Borge, Hunter, Ozzy
from tqdm import tqdm
from units import Boss, Enemy


def sim_worker(hunter_class: Hunter, config_path: str) -> None:
    """Worker process for running simulations in parallel.
    """
    return Simulation(hunter_class(config_path)).run()

class SimulationManager():
    def __init__(self, hunter_config_path: str) -> None:
        self.hunter_config_path = hunter_config_path
        self.results: List = []

    def run(self, repetitions: int, num_processes: int = -1, show_stats: bool = True) -> None:
        """Run simulations and print results.

        Args:
            repetitions (int): Number of simulations to run.
            num_processes (int, optional): Number of processes to use for parallelisation. Defaults to -1, which processes runs sequentially.
            show_stats (bool, optional): Whether to show combat statistics after the simulation, only the stage breakdown and loot. Defaults to True.
        """
        res = self.__run_sims(repetitions, num_processes)
        self.pprint_res(res, show_stats=show_stats)

    def compare_against(self, compare_path: str, repetitions: int, num_processes: int = -1, show_stats: bool = True) -> None:
        """Run simulations for 2 builds, compare results and print.

        Args:
            compare_path (str): Path to valid build config file to compare against the current hunter build.
            repetitions (int): Number of simulations to run.
            num_processes (int, optional): Number of processes to use for parallelisation. Defaults to -1, which processes runs sequentially.
            show_stats (bool, optional): Whether to show combat statistics after the simulation, only the stage breakdown and loot. Defaults to True.
        """
        print('BUILD 1:')
        res = self.__run_sims(repetitions, num_processes)
        self.hunter_config_path = compare_path
        print('BUILD 2:')
        res_c = self.__run_sims(repetitions, num_processes)
        self.pprint_compare(res, res_c, 'Build Comparison', show_stats=show_stats)

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
        with open(self.hunter_config_path, 'r') as f:
            cfg = yaml.safe_load(f)
        match cfg["meta"]["hunter"].lower():
            case "borge":
                hunter_class = Borge
            case "ozzy":
                hunter_class = Ozzy
            case _:
                raise ValueError(f'Unknown hunter type found in config {f}')
        hunter_class(self.hunter_config_path).show_build()
        if num_processes > 0:
            with ProcessPoolExecutor(max_workers=num_processes) as e:
                self.results = list(tqdm(e.map(sim_worker, [hunter_class] * repetitions, [self.hunter_config_path] * repetitions), total=repetitions, leave=True))
        else:
            for _ in tqdm(range(repetitions), leave=False):
                self.results.append(Simulation(hunter_class(self.hunter_config_path)).run())
        
        # prepare results
        res = {'hunter': hunter_class}
        for d in self.results:
            for k, v in d.items():
                res.setdefault(k, []).append(v)
        return res

    @classmethod
    def make_printable(cls, res_dict: dict) -> Tuple[dict, dict]:
        """Converts the results dict into a printable format and computes averages and standard deviations.

        Args:
            res_dict (dict): Results dict.

        Returns:
            [dict, dict]: Average and standard deviation dicts.
        """
        res_dict["enrage_log"] = list(chain.from_iterable(res_dict["enrage_log"]))
        res_dict["first_revive"] = [r[0] for r in res_dict["revive_log"] if r]
        res_dict["second_revive"] = [r[1] for r in res_dict["revive_log"] if r and len(r) > 1]
        res_dict["lph"] = [(res_dict["total_loot"][i] / (res_dict["elapsed_time"][i] / (60 * 60))) for i in range(len(res_dict["total_loot"]))]
        if len(res_dict["final_stage"]) > 1:
            enrage = res_dict.pop('enrage_log')
            avg = {k: statistics.fmean(v) for k, v in res_dict.items() if v and type(v[0]) != list}
            std = {k: statistics.stdev(v) for k, v in res_dict.items() if v and type(v[0]) != list}
            print(enrage)
            if len(enrage) > 1:
                avg["enrage_log"] = statistics.fmean(enrage)
                std["enrage_log"] = statistics.stdev(enrage)
            else:
                avg["enrage_log"] = [enrage]
                std["enrage_log"] = [0]
        else:
            avg = dict()
            for k, v in res_dict.items():
                if type(v) == list and len(v) == 1:
                    avg[k] = v[0]
            std = {k: 0 for k in res_dict}
        return avg, std

    @classmethod
    def pprint_res(cls, res_dict: dict, custom_message: str = None, coloured: bool = False, show_stats: bool = True) -> None:
        """Pretty print results dict.

        Args:
            res_dict (dict): Results dict.
            custom_message (str, optional): A custom title for the headline of the printout. Defaults to None.
            coloured (bool, optional): Whether to colour the output or not. Defaults to False.
            show_stats (bool, optional): Whether to show combat statistics after the simulation, only the stage breakdown and loot. Defaults to True.
        """
        hunter_class = res_dict.pop('hunter')
        avg, std = cls.make_printable(res_dict)
        res_dict["lph"] = [(res_dict["total_loot"][i] / (res_dict["elapsed_time"][i] / (60 * 60))) for i in range(len(res_dict["total_loot"]))]
        out = []
        divider = "-" * 10
        c_off = '\033[0m'
        out.append(f'Average over {len(res_dict["total_kills"])} run{"s" if len(res_dict["total_kills"]) > 1 else ""}:\t\t {"> " + custom_message + " <" if custom_message else ""}')
        out.append("#" * 56)
        c_on = '\033[38;2;93;101;173m' if coloured else ''
        if show_stats:
            out.append(f'{c_on}Main stats:{c_off}')
            out.append(f'{c_on}{divider}{c_off}')
            if 'enrage_log' in avg:
                out.append(f'{c_on}Avg Enrage stacks: {avg["enrage_log"]:>20,.2f}\t(+/- {std["enrage_log"]:>10,.2f}){c_off}')
            if 'first_revive' in avg:
                out.append(f'{c_on}Revive stage 1st: {avg["first_revive"]:>21,.2f}\t(+/- {std["first_revive"]:>10,.2f}){c_off}')
            if 'second_revive' in avg:
                out.append(f'{c_on}Revive stage 2nd: {avg["second_revive"]:>21,.2f}\t(+/- {std["second_revive"]:>10,.2f}){c_off}')
            out.append(f'{c_on}Avg total kills: {avg["total_kills"]:>22,.2f}\t(+/- {std["total_kills"]:>10,.2f}){c_off}')
            out.append(f'{c_on}Elapsed time: {str(timedelta(seconds=round(avg["elapsed_time"], 0))):>25}\t(+/- {str(timedelta(seconds=round(std["elapsed_time"], 0))):>10}){c_off}')
            c_on = '\033[38;2;195;61;3m' if coloured else ''
            out.append(f'{c_on}Offence:{c_off}')
            out.append(f'{c_on}{divider}{c_off}')
            out.append(f'{c_on}Avg total attacks: {avg["total_attacks"]:>20,.2f}\t(+/- {std["total_attacks"]:>10,.2f}){c_off}')
            out.append(f'{c_on}Avg total damage: {avg["total_damage"]:>21,.2f}\t(+/- {std["total_damage"]:>10,.2f}){c_off}')
            if hunter_class == Borge:
                out.append(f'{c_on}Avg total crits: {avg["total_crits"]:>22,.2f}\t(+/- {std["total_crits"]:>10,.2f}){c_off}')
                out.append(f'{c_on}Avg total extra from crits: {avg["total_extra_from_crits"]:>11,.2f}\t(+/- {std["total_extra_from_crits"]:>10,.2f}){c_off}')
            elif hunter_class == Ozzy:
                out.append(f'{c_on}Avg total multistrikes: {avg["total_multistrikes"]:>15,.2f}\t(+/- {std["total_multistrikes"]:>10,.2f}){c_off}')
                out.append(f'{c_on}Avg total extra from ms: {avg["total_ms_extra_damage"]:>14,.2f}\t(+/- {std["total_ms_extra_damage"]:>10,.2f}){c_off}')
                out.append(f'{c_on}Avg total decay damage: {avg["total_decay_damage"]:>15,.2f}\t(+/- {std["total_decay_damage"]:>10,.2f}){c_off}')
                out.append(f'{c_on}Avg total cripple extra: {avg["total_cripple_extra_damage"]:>14,.2f}\t(+/- {std["total_cripple_extra_damage"]:>10,.2f}){c_off}')
            c_on = '\033[38;2;1;163;87m' if coloured else ''
            out.append(f'{c_on}Sustain:{c_off}')
            out.append(f'{c_on}{divider}{c_off}')
            out.append(f'{c_on}Avg total taken: {avg["total_taken"]:>22,.2f}\t(+/- {std["total_taken"]:>10,.2f}){c_off}')
            out.append(f'{c_on}Avg total regen: {avg["total_regen"]:>22,.2f}\t(+/- {std["total_regen"]:>10,.2f}){c_off}')
            out.append(f'{c_on}Avg total attacks taken: {avg["total_attacks_suffered"]:>14,.2f}\t(+/- {std["total_attacks_suffered"]:>10,.2f}){c_off}')
            out.append(f'{c_on}Avg total lifesteal: {avg["total_lifesteal"]:>18,.2f}\t(+/- {std["total_lifesteal"]:>10,.2f}){c_off}')
            c_on = '\033[38;2;234;186;1m' if coloured else ''
            out.append(f'{c_on}Defence:{c_off}')
            out.append(f'{c_on}{divider}{c_off}')
            out.append(f'{c_on}Avg total evades: {avg["total_evades"]:>21,.2f}\t(+/- {std["total_evades"]:>10,.2f}){c_off}')
            if hunter_class == Ozzy:
                out.append(f'{c_on}Avg trickster evades: {avg["total_trickster_evades"]:>17,.2f}\t(+/- {std["total_trickster_evades"]:>10,.2f}){c_off}')
            out.append(f'{c_on}Avg total mitigated: {avg["total_mitigated"]:>18,.2f}\t(+/- {std["total_mitigated"]:>10,.2f}){c_off}')
            c_on = '\033[38;2;14;156;228m' if coloured else ''
            out.append(f'{c_on}Effects:{c_off}')
            out.append(f'{c_on}{divider}{c_off}')
            out.append(f'{c_on}Avg total effect procs: {avg["total_effect_procs"]:>15,.2f}\t(+/- {std["total_effect_procs"]:>10,.2f}){c_off}')
            out.append(f'{c_on}Avg stun time inflicted: {str(timedelta(seconds=avg["total_stuntime_inflicted"])):>14.7}\t(+/- {str(timedelta(seconds=std["total_stuntime_inflicted"])):>10.7}){c_off}')
            if hunter_class == Borge:
                out.append(f'{c_on}Avg total helltouch: {avg["total_helltouch"]:>18,.2f}\t(+/- {std["total_helltouch"]:>10,.2f}){c_off}')
                out.append(f'{c_on}Avg total loth: {avg["total_loth"]:>23,.2f}\t(+/- {std["total_loth"]:>10,.2f}){c_off}')
            elif hunter_class == Ozzy:
                out.append(f'{c_on}Avg total echo procs: {avg["total_echo"]:>17,.2f}\t(+/- {std["total_echo"]:>10,.2f}){c_off}')
            out.append(f'{c_on}Avg total potion: {avg["total_potion"]:>21,.2f}\t(+/- {std["total_potion"]:>10,.2f}){c_off}')
            out.append(f'{c_on}{divider}{c_off}')
        c_on = '\033[38;2;98;65;169m' if coloured else ''
        out.append(f'{c_on}Loot:{c_off} (arbitrary values, for comparison only)')
        out.append(f'{c_on}{divider}{c_off}')
        out.append(f'{c_on}Avg LPH: {avg["lph"]:>30,.2f}\t(+/- {std["lph"]:>10,.2f}){c_off}')
        out.append(f'{c_on}Best LPH: {max(res_dict["lph"]):>29,.2f}\t{c_off}')
        out.append(f'{c_on}Worst LPH: {min(res_dict["lph"]):>28,.2f}\t{c_off}')
        out.append(f'{c_on}{divider}{c_off}')
        c_on = '\033[38;2;128;128;128m'
        out.append(f'Final stage reached:  MAX:{c_on}{max(res_dict["final_stage"]):>4}{c_off}, MED:{c_on}{floor(statistics.median(res_dict["final_stage"])):>4}{c_off}, AVG:{c_on}{floor(statistics.mean(res_dict["final_stage"])):>4}{c_off}, MIN:{c_on}{min(res_dict["final_stage"]):>4}{c_off}')
        out.append('')
        stage_out = []
        final_stage_pct = {i:j/len(res_dict["final_stage"]) for i,j in Counter(res_dict["final_stage"]).items()}
        for i, k in enumerate(sorted([*final_stage_pct])):
            stage_out.append(f'{k:>3d}: {c_on}{final_stage_pct[k]:>6.2%}{c_off}   ' + ("\n" if (i + 1) % 5 == 0 and i > 0 else ""))
        out.append(''.join(stage_out))
        out.append('')
        print('\n'.join(out))

    @classmethod
    def eval_perf(cls, b1: float, b2: float) -> str:
        """Evaluate performance of 2 builds by comparing the passed values.

        Args:
            b1 (float): Performance of build 1.
            b2 (float): Performance of build 2.

        Returns:
            str: Performance evaluation: "BUILD 1/2 (+ diff%)".
        """
        if b1 > b2:
            if b2 == 0:
                return f'>> BUILD 1 (+{b1:,.2f})'
            return f'>> BUILD 1 (+{(b1/b2)-1:>7,.2%})'
        elif b2 > b1:
            if b1 == 0:
                return f'>> BUILD 2 (+{b2:,.2f})'
            return f'>> BUILD 2 (+{(b2/b1)-1:>7,.2%})'
        else:
            return ''

    @classmethod
    def pprint_compare(cls, res1: dict, res2: dict, custom_message: str = None, coloured: bool = False, show_stats: bool = True) -> None:
        """Pretty print comparison of 2 results dicts.

        Args:
            res1 (dict): Result dict of the first build
            res2 (dict): Result dict of the second build
            custom_message (str, optional): A custom title for the headline of the printout. Defaults to None.
            coloured (bool, optional): Whether to colour the output or not. Defaults to False.
            show_stats (bool, optional): Whether to show combat statistics after the simulation, only the stage breakdown and loot. Defaults to True.
        """
        hunter_class = res1.pop('hunter')
        res2.pop('hunter')
        avg1, _ = cls.make_printable(res1)
        avg2, _ = cls.make_printable(res2)
        res1["lph"] = [(res1["total_loot"][i] / (res1["elapsed_time"][i] / (60 * 60))) for i in range(len(res1["total_loot"]))]
        res2["lph"] = [(res2["total_loot"][i] / (res2["elapsed_time"][i] / (60 * 60))) for i in range(len(res2["total_loot"]))]
        out = []
        divider = "-" * 10
        c_off = '\033[0m'
        out.append(f'Average over {len(res1["total_kills"])} run{"s" if len(res1["total_kills"]) > 1 else ""}:\t\t {"> " + custom_message + " <" if custom_message else ""}')
        out.append("#" * 56)
        c_on = '\033[38;2;93;101;173m' if coloured else ''
        if show_stats:
            out.append(f'{c_on}Main stats:{c_off}')
            out.append(f'{c_on}{divider}{c_off}')
            if 'enrage_log' in avg1 and 'enrage_log' in avg2:
                out.append(f'{c_on}Avg Enrage stacks: {round(max(avg1["enrage_log"], avg2["enrage_log"])-min(avg1["enrage_log"], avg2["enrage_log"]), 2):>20,.2f} stacks less{c_off}{SimulationManager.eval_perf(avg1["enrage_log"], avg2["enrage_log"]):>24}')
            if 'first_revive' in avg1 and 'first_revive' in avg2:
                out.append(f'{c_on}Revive stage 1st: {max(avg1["first_revive"], avg2["first_revive"])-min(avg1["first_revive"], avg2["first_revive"]):>21,.2f} stages later{c_off}{SimulationManager.eval_perf(avg1["first_revive"], avg2["first_revive"]):>23}')
            if 'second_revive' in avg1 and 'second_revive' in avg2:
                out.append(f'{c_on}Revive stage 2nd: {max(avg1["second_revive"], avg2["second_revive"])-min(avg1["second_revive"], avg2["second_revive"]):>21,.2f} stages later{c_off}{SimulationManager.eval_perf(avg1["second_revive"], avg2["second_revive"]):>23}')
            out.append(f'{c_on}Avg total kills: {max(avg1["total_kills"], avg2["total_kills"])-min(avg1["total_kills"], avg2["total_kills"]):>22,.2f} more{c_off}{SimulationManager.eval_perf(avg1["total_kills"], avg2["total_kills"]):>31}')
            out.append(f'{c_on}Elapsed time: {str(max(timedelta(seconds=round(avg1["elapsed_time"], 0)), timedelta(seconds=round(avg2["elapsed_time"], 0)))-min(timedelta(seconds=round(avg1["elapsed_time"], 0)), timedelta(seconds=round(avg2["elapsed_time"], 0)))):>25} faster{c_off}{SimulationManager.eval_perf(timedelta(seconds=round(avg1["elapsed_time"], 0)), timedelta(seconds=round(avg2["elapsed_time"], 0))):>29}')
            c_on = '\033[38;2;195;61;3m' if coloured else ''
            out.append(f'{c_on}Offence:{c_off}')
            out.append(f'{c_on}{divider}{c_off}')
            out.append(f'{c_on}Avg total attacks: {max(avg1["total_attacks"], avg2["total_attacks"])-min(avg1["total_attacks"], avg2["total_attacks"]):>20,.2f} more{c_off}{SimulationManager.eval_perf(avg1["total_attacks"], avg2["total_attacks"]):>31}')
            out.append(f'{c_on}Avg total damage: {max(avg1["total_damage"], avg2["total_damage"])-min(avg1["total_damage"], avg2["total_damage"]):>21,.2f} more{c_off}{SimulationManager.eval_perf(avg1["total_damage"], avg2["total_damage"]):>31}')
            if hunter_class == Borge:
                out.append(f'{c_on}Avg total crits: {max(avg1["total_crits"], avg2["total_crits"])-min(avg1["total_crits"], avg2["total_crits"]):>22,.2f} more{c_off}{SimulationManager.eval_perf(avg1["total_crits"], avg2["total_crits"]):>31}')
                out.append(f'{c_on}Avg total extra from crits: {max(avg1["total_extra_from_crits"], avg2["total_extra_from_crits"])-min(avg1["total_extra_from_crits"], avg2["total_extra_from_crits"]):>11,.2f} more{c_off}{SimulationManager.eval_perf(avg1["total_extra_from_crits"], avg2["total_extra_from_crits"]):>31}')
            elif hunter_class == Ozzy:
                out.append(f'{c_on}Avg total multistrikes: {max(avg1["total_multistrikes"], avg2["total_multistrikes"])-min(avg1["total_multistrikes"], avg2["total_multistrikes"]):>15,.2f} more{c_off}{SimulationManager.eval_perf(avg1["total_multistrikes"], avg2["total_multistrikes"]):>31}')
                out.append(f'{c_on}Avg total extra from ms: {max(avg1["total_ms_extra_damage"], avg2["total_ms_extra_damage"])-min(avg1["total_ms_extra_damage"], avg2["total_ms_extra_damage"]):>14,.2f} more{c_off}{SimulationManager.eval_perf(avg1["total_ms_extra_damage"], avg2["total_ms_extra_damage"]):>31}')
                out.append(f'{c_on}Avg total decay damage: {max(avg1["total_decay_damage"], avg2["total_decay_damage"])-min(avg1["total_decay_damage"], avg2["total_decay_damage"]):>15,.2f} more{c_off}{SimulationManager.eval_perf(avg1["total_decay_damage"], avg2["total_decay_damage"]):>31}')
                out.append(f'{c_on}Avg total cripple extra: {max(avg1["total_cripple_extra_damage"], avg2["total_cripple_extra_damage"])-min(avg1["total_cripple_extra_damage"], avg2["total_cripple_extra_damage"]):>15,.2f} more{c_off}{SimulationManager.eval_perf(avg1["total_cripple_extra_damage"], avg2["total_cripple_extra_damage"]):>31}')
            c_on = '\033[38;2;1;163;87m' if coloured else ''
            out.append(f'{c_on}Sustain:{c_off}')
            out.append(f'{c_on}{divider}{c_off}')
            out.append(f'{c_on}Avg total taken: {max(avg1["total_taken"], avg2["total_taken"])-min(avg1["total_taken"], avg2["total_taken"]):>22,.2f} less{c_off}{SimulationManager.eval_perf(avg1["total_taken"], avg2["total_taken"]):>31}')
            out.append(f'{c_on}Avg total regen: {max(avg1["total_regen"], avg2["total_regen"])-min(avg1["total_regen"], avg2["total_regen"]):>22,.2f} more{c_off}{SimulationManager.eval_perf(avg1["total_regen"], avg2["total_regen"]):>31}')
            out.append(f'{c_on}Avg total attacks taken: {max(avg1["total_attacks_suffered"], avg2["total_attacks_suffered"])-min(avg1["total_attacks_suffered"], avg2["total_attacks_suffered"]):>14,.2f} more{c_off}{SimulationManager.eval_perf(avg1["total_attacks_suffered"], avg2["total_attacks_suffered"]):>31}')
            out.append(f'{c_on}Avg total lifesteal: {max(avg1["total_lifesteal"], avg2["total_lifesteal"])-min(avg1["total_lifesteal"], avg2["total_lifesteal"]):>18,.2f} more{c_off}{SimulationManager.eval_perf(avg1["total_lifesteal"], avg2["total_lifesteal"]):>31}')
            c_on = '\033[38;2;234;186;1m' if coloured else ''
            out.append(f'{c_on}Defence:{c_off}')
            out.append(f'{c_on}{divider}{c_off}')
            out.append(f'{c_on}Avg total evades: {max(avg1["total_evades"], avg2["total_evades"])-min(avg1["total_evades"], avg2["total_evades"]):>21,.2f} more{c_off}{SimulationManager.eval_perf(avg1["total_evades"], avg2["total_evades"]):>31}')
            if hunter_class == Ozzy:
                out.append(f'{c_on}Avg trickster evades: {max(avg1["total_trickster_evades"], avg2["total_trickster_evades"])-min(avg1["total_trickster_evades"], avg2["total_trickster_evades"]):>17,.2f} more{c_off}{SimulationManager.eval_perf(avg1["total_trickster_evades"], avg2["total_trickster_evades"]):>31}')
            out.append(f'{c_on}Avg total mitigated: {max(avg1["total_mitigated"], avg2["total_mitigated"])-min(avg1["total_mitigated"], avg2["total_mitigated"]):>18,.2f} more{c_off}{SimulationManager.eval_perf(avg1["total_mitigated"], avg2["total_mitigated"]):>31}')
            c_on = '\033[38;2;14;156;228m' if coloured else ''
            out.append(f'{c_on}Effects:{c_off}')
            out.append(f'{c_on}{divider}{c_off}')
            out.append(f'{c_on}Avg total effect procs: {max(avg1["total_effect_procs"], avg2["total_effect_procs"])-min(avg1["total_effect_procs"], avg2["total_effect_procs"]):>15,.2f} more{c_off}{SimulationManager.eval_perf(avg1["total_effect_procs"], avg2["total_effect_procs"]):>31}')
            out.append(f'{c_on}Avg stun time inflicted: {str(timedelta(seconds=max(avg1["total_stuntime_inflicted"], avg2["total_stuntime_inflicted"])-min(avg1["total_stuntime_inflicted"], avg2["total_stuntime_inflicted"]))):>14.7} more{c_off}{SimulationManager.eval_perf(avg1["total_stuntime_inflicted"], avg2["total_stuntime_inflicted"]):>31}')
            if hunter_class == Borge:
                out.append(f'{c_on}Avg total helltouch: {max(avg1["total_helltouch"], avg2["total_helltouch"])-min(avg1["total_helltouch"], avg2["total_helltouch"]):>18,.2f} more{c_off}{SimulationManager.eval_perf(avg1["total_helltouch"], avg2["total_helltouch"]):>31}')
                out.append(f'{c_on}Avg total loth: {max(avg1["total_loth"], avg2["total_loth"])-min(avg1["total_loth"], avg2["total_loth"]):>23,.2f} more{c_off}{SimulationManager.eval_perf(avg1["total_loth"], avg2["total_loth"]):>31}')
            elif hunter_class == Ozzy:
                out.append(f'{c_on}Avg total loth: {max(avg1["total_echo"], avg2["total_echo"])-min(avg1["total_echo"], avg2["total_echo"]):>23,.2f} more{c_off}{SimulationManager.eval_perf(avg1["total_echo"], avg2["total_echo"]):>31}')
            out.append(f'{c_on}Avg total potion: {max(avg1["total_potion"], avg2["total_potion"])-min(avg1["total_potion"], avg2["total_potion"]):>21,.2f} more{c_off}{SimulationManager.eval_perf(avg1["total_potion"], avg2["total_potion"]):>31}')
            out.append(f'{c_on}{divider}{c_off}')
        c_on = '\033[38;2;98;65;169m' if coloured else ''
        out.append(f'{c_on}Loot:{c_off} (arbitrary values, for comparison only)')
        out.append(f'{c_on}{divider}{c_off}')
        out.append(f'{c_on}Avg LPH: {max(avg1["lph"], avg2["lph"])-min(avg1["lph"], avg2["lph"]):>30,.2f} more{c_off}{SimulationManager.eval_perf(avg1["lph"], avg2["lph"]):>31}')
        out.append(f'{c_on}Best LPH: {max(max(res1["lph"]), max(res2["lph"]))-min(max(res1["lph"]), max(res2["lph"])):>29,.2f} more{c_off}{SimulationManager.eval_perf(max(res1["lph"]), max(res2["lph"])):>31}')
        out.append(f'{c_on}Worst LPH: {max(min(res1["lph"]), min(res2["lph"]))-min(min(res1["lph"]), min(res2["lph"])):>28,.2f} less{c_off}{SimulationManager.eval_perf(min(res1["lph"]), min(res2["lph"])):>31}')
        out.append(f'{c_on}{divider}{c_off}')
        c_on = '\033[38;2;128;128;128m'
        if statistics.median(res1["final_stage"]) > 100 and min(res1["final_stage"]) % 100 == 0:
            # out.append(f'Final stage reached by BUILD 1:  MAX:{c_on}{(mx := max(res1["final_stage"])):>4} ({final_pct1[mx]:>6.2%}{c_off}), MED:{c_on}{(med := floor(statistics.median(res1["final_stage"]))):>4} ({final_pct1[med]:>6.2%}){c_off}, MIN:{c_on}{(mn := min(res1["final_stage"])):>4} ({final_pct1[mn]:>6.2%}){c_off}')
            final_pct1 = {i:j/len(res1["final_stage"]) for i,j in Counter(res1["final_stage"]).items()}
            out.append(f'Final stage reached by BUILD 1:  MAX:{c_on}{max(res1["final_stage"]):>4}{c_off}, MED:{c_on}{floor(statistics.median(res1["final_stage"])):>4}{c_off}, AVG:{c_on}{floor(statistics.mean(res1["final_stage"])):>4}{c_off}, MIN:\033[91m{(mn := min(res1["final_stage"])):>4} ({final_pct1[mn]:>6.2%}){c_off}')

        else:
            out.append(f'Final stage reached by BUILD 1:  MAX:{c_on}{max(res1["final_stage"]):>4}{c_off}, MED:{c_on}{floor(statistics.median(res1["final_stage"])):>4}{c_off}, AVG:{c_on}{floor(statistics.mean(res1["final_stage"])):>4}{c_off}, MIN:{c_on}{min(res1["final_stage"]):>4}{c_off}')
        if statistics.median(res2["final_stage"]) > 100 and min(res2["final_stage"]) % 100 == 0:
            final_pct2 = {i:j/len(res2["final_stage"]) for i,j in Counter(res2["final_stage"]).items()}
            out.append(f'Final stage reached by BUILD 2:  MAX:{c_on}{max(res2["final_stage"]):>4}{c_off}, MED:{c_on}{floor(statistics.median(res2["final_stage"])):>4}{c_off}, AVG:{c_on}{floor(statistics.mean(res2["final_stage"])):>4}{c_off}, MIN:\033[91m{(mn := min(res2["final_stage"])):>4} ({final_pct2[mn]:>6.2%}){c_off}')

        else:
            out.append(f'Final stage reached by BUILD 2:  MAX:{c_on}{max(res2["final_stage"]):>4}{c_off}, MED:{c_on}{floor(statistics.median(res2["final_stage"])):>4}{c_off}, AVG:{c_on}{floor(statistics.mean(res2["final_stage"])):>4}{c_off}, MIN:{c_on}{min(res2["final_stage"]):>4}{c_off}')
        out.append('')
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

    def run(self) -> defaultdict:
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