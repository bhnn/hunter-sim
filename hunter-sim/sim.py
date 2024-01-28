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

    def run(self, repetitions: int, threaded: int = -1) -> None:
        res = self.__run_sims(repetitions, threaded)
        self.pprint_res(res)

    def compare_against(self, compare_path: str, repetitions: int, threaded: int = -1) -> None:
        res = self.__run_sims(repetitions, threaded)
        self.hunter_config_path = compare_path
        res_c = self.__run_sims(repetitions, threaded)
        self.pprint_compare(res, res_c, 'Build Comparison')

    def __run_sims(self, repetitions: int, threaded: int = -1) -> None:
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
        
        # prepare results
        res = {'hunter': hunter_class}
        for d in self.results:
            for k, v in d.items():
                res.setdefault(k, []).append(v)
        return res

    @classmethod
    def make_printable(cls, res_dict: dict) -> [dict, dict]:
        res_dict["enrage_log"] = list(chain.from_iterable(res_dict["enrage_log"]))
        res_dict["first_revive"] = [r[0] for r in res_dict["revive_log"] if r]
        res_dict["second_revive"] = [r[1] for r in res_dict["revive_log"] if r and len(r) > 1]
        res_dict["lph"] = [(res_dict["total_loot"][i] / (res_dict["elapsed_time"][i] / (60 * 60))) for i in range(len(res_dict["total_loot"]))]
        if len(res_dict["final_stage"]) > 1:
            avg = {k: statistics.fmean(v) for k, v in res_dict.items() if v and type(v[0]) != list}
            std = {k: statistics.stdev(v) for k, v in res_dict.items() if v and type(v[0]) != list}
        else:
            avg = dict()
            for k, v in res_dict.items():
                if type(v) == list and len(v) == 1:
                    avg[k] = v[0]
            std = {k: 0 for k in res_dict}
        return avg, std

    @classmethod
    def pprint_res(cls, res_dict: dict, custom_message: str = None, coloured: bool = False) -> None:
        hunter_class = res_dict.pop('hunter')
        avg, std = cls.make_printable(res_dict)
        res_dict["lph"] = [(res_dict["total_loot"][i] / (res_dict["elapsed_time"][i] / (60 * 60))) for i in range(len(res_dict["total_loot"]))]
        out = []
        divider = "-" * 10
        c_off = '\033[0m'
        out.append(f'Average over {len(res_dict["total_kills"])} runs:\t\t {"> " + custom_message + " <" if custom_message else ""}')
        out.append("#" * 56)
        c_on = '\033[38;2;93;101;173m' if coloured else ''
        out.append(f'{c_on}Main stats:{c_off}')
        out.append(f'{c_on}{divider}{c_off}')
        if 'enrage_log' in avg:
            out.append(f'{c_on}Avg Enrage stacks: {avg["enrage_log"]:>20.2f}\t(+/- {std["enrage_log"]:>10.2f}){c_off}')
        if 'first_revive' in avg:
            out.append(f'{c_on}Revive stage 1st: {avg["first_revive"]:>21.2f}\t(+/- {std["first_revive"]:>10.2f}){c_off}')
        if 'second_revive' in avg:
            out.append(f'{c_on}Revive stage 2nd: {avg["second_revive"]:>21.2f}\t(+/- {std["second_revive"]:>10.2f}){c_off}')
        out.append(f'{c_on}Avg total kills: {avg["total_kills"]:>22,.2f}\t(+/- {std["total_kills"]:>10,.2f}){c_off}')
        out.append(f'{c_on}Elapsed time: {str(timedelta(seconds=round(avg["elapsed_time"], 0))):>25}\t(+/- {str(timedelta(seconds=round(std["elapsed_time"], 0))):>10}){c_off}')
        c_on = '\033[38;2;195;61;3m' if coloured else ''
        out.append(f'{c_on}Offence:{c_off}')
        out.append(f'{c_on}{divider}{c_off}')
        out.append(f'{c_on}Avg total attacks: {avg["total_attacks"]:>20,.2f}\t(+/- {std["total_attacks"]:>10,.2f}){c_off}')
        out.append(f'{c_on}Avg total damage: {avg["total_damage"]:>21,.2f}\t(+/- {std["total_damage"]:>10,.2f}){c_off}')
        if hunter_class == Borge:
            out.append(f'{c_on}Avg total crits: {avg["total_crits"]:>22,.2f}\t(+/- {std["total_crits"]:>10,.2f}){c_off}')
            out.append(f'{c_on}Avg total extra from crits: {avg["total_extra_from_crits"]:>11,.2f}\t(+/- {std["total_extra_from_crits"]:>10.2f}){c_off}')
        elif hunter_class == Ozzy:
            out.append(f'{c_on}Avg total multistrikes: {avg["total_multistrikes"]:>15.2f}\t(+/- {std["total_multistrikes"]:>10.2f}){c_off}')
            out.append(f'{c_on}Avg total extra from ms: {avg["total_ms_extra_damage"]:>14.2f}\t(+/- {std["total_ms_extra_damage"]:>10.2f}){c_off}')
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
        if hunter_class == Borge:
            out.append(f'{c_on}Avg total helltouch: {avg["total_helltouch"]:>18,.2f}\t(+/- {std["total_helltouch"]:>10,.2f}){c_off}')
            out.append(f'{c_on}Avg total loth: {avg["total_loth"]:>23,.2f}\t(+/- {std["total_loth"]:>10,.2f}){c_off}')
        out.append(f'{c_on}Avg total potion: {avg["total_potion"]:>21,.2f}\t(+/- {std["total_potion"]:>10,.2f}){c_off}')
        out.append(f'{c_on}{divider}{c_off}')
        c_on = '\033[38;2;98;65;169m' if coloured else ''
        out.append(f'{c_on}Loot:{c_off} (arbitrary values, for comparison only)')
        out.append(f'{c_on}{divider}{c_off}')
        out.append(f'{c_on}Avg LPH: {avg["lph"]:>30,.2f}\t(+/- {std["lph"]:>10,.2f}){c_off}')
        out.append(f'{c_on}Best LPH: {max(res_dict["lph"]):>29.3}\t{c_off}')
        out.append(f'{c_on}Worst LPH: {min(res_dict["lph"]):>28.3}\t{c_off}')
        out.append(f'{c_on}{divider}{c_off}')
        out.append(f'Final stage reached:  MAX({max(res_dict["final_stage"])}), MED({floor(statistics.median(res_dict["final_stage"]))}), AVG({floor(statistics.mean(res_dict["final_stage"]))}), MIN({min(res_dict["final_stage"])})')
        out.append('')
        stage_out = []
        final_stage_pct = {i:j/len(res_dict["final_stage"]) for i,j in Counter(res_dict["final_stage"]).items()}
        for i, k in enumerate(sorted([*final_stage_pct])):
            stage_out.append(f'{k:>3d}: {final_stage_pct[k]:>6.2%}   ' + ("\n" if (i + 1) % 5 == 0 and i > 0 else ""))
        out.append(''.join(stage_out))
        out.append('')
        print('\n'.join(out))

    @classmethod
    def pprint_compare(cls, res1: dict, res2: dict, custom_message: str = None, coloured: bool = False) -> None:
        hunter_class = res1.pop('hunter')
        res2.pop('hunter')
        avg1, std1 = cls.make_printable(res1)
        avg2, std2 = cls.make_printable(res2)
        res1["lph"] = [(res1["total_loot"][i] / (res1["elapsed_time"][i] / (60 * 60))) for i in range(len(res1["total_loot"]))]
        res2["lph"] = [(res2["total_loot"][i] / (res2["elapsed_time"][i] / (60 * 60))) for i in range(len(res2["total_loot"]))]
        out = []
        divider = "-" * 10
        c_off = '\033[0m'
        out.append(f'Average over {len(res1["total_kills"])} runs:\t\t {"> " + custom_message + " <" if custom_message else ""}')
        out.append("#" * 56)
        c_on = '\033[38;2;93;101;173m' if coloured else ''
        out.append(f'{c_on}Main stats:{c_off}')
        out.append(f'{c_on}{divider}{c_off}')
        # TODO: change all of this to .append(max()-min()) and then out[-1] += f'>> BUILD 1' or 2
        if 'enrage_log' in avg1 and 'enrage_log' in avg2:
            if avg1["enrage_log"] > avg2["enrage_log"] and avg2["enrage_log"] > 0:
                out.append(f'{c_on}Avg Enrage stacks: {avg1["enrage_log"]-avg2["enrage_log"]:>20.2f} stacks less{c_off}{">> BUILD 2":>20}')
            elif avg2["enrage_log"] > avg1["enrage_log"] and avg1["enrage_log"] > 0:
                out.append(f'{c_on}Avg Enrage stacks: {avg2["enrage_log"]-avg1["enrage_log"]:>20.2f} stacks less{c_off}{">> BUILD 1":>20}')
        if 'first_revive' in avg1 and 'first_revive' in avg2:
            if avg1["first_revive"] > avg2["first_revive"]:
                out.append(f'{c_on}Revive stage 1st: {avg1["first_revive"]-avg2["first_revive"]:>21.2f} stages later{c_off}{">> BUILD 1":>12}')
            else:
                out.append(f'{c_on}Revive stage 1st: {avg2["first_revive"]-avg1["first_revive"]:>21.2f} stages later{c_off}{">> BUILD 2":>12}')
        if 'second_revive' in avg1 and 'second_revive' in avg2:
            if avg1["second_revive"] > avg2["second_revive"]:
                out.append(f'{c_on}Revive stage 2nd: {avg1["second_revive"]-avg2["second_revive"]:>21.2f} stages later{c_off}{">> BUILD 1":>12}')
            else:
                out.append(f'{c_on}Revive stage 2nd: {avg2["second_revive"]-avg1["second_revive"]:>21.2f} stages later{c_off}{">> BUILD 2":>12}')
        if avg1["total_kills"] > avg2["total_kills"]:
            out.append(f'{c_on}Avg total kills: {avg1["total_kills"]-avg2["total_kills"]:>22,.2f} more{c_off}{">> BUILD 1":>20}')
        else:
            out.append(f'{c_on}Avg total kills: {avg2["total_kills"]-avg1["total_kills"]:>22,.2f} more{c_off}{">> BUILD 2":>20}')
        if avg1["elapsed_time"] > avg2["elapsed_time"]:
            out.append(f'{c_on}Elapsed time: {str(timedelta(seconds=round(avg1["elapsed_time"], 0))-timedelta(seconds=round(avg2["elapsed_time"], 0))):>25} faster{c_off}{">> BUILD 2":>18}')
        else:
            out.append(f'{c_on}Elapsed time: {str(timedelta(seconds=round(avg2["elapsed_time"], 0))-timedelta(seconds=round(avg1["elapsed_time"], 0))):>25} faster{c_off}{">> BUILD 1":>18}')
        c_on = '\033[38;2;195;61;3m' if coloured else ''
        out.append(f'{c_on}Offence:{c_off}')
        out.append(f'{c_on}{divider}{c_off}')
        if avg1["total_attacks"] > avg2["total_attacks"]:
            out.append(f'{c_on}Avg total attacks: {avg1["total_attacks"]-avg2["total_attacks"]:>20,.2f} more{c_off}{">> BUILD 1":>20}')
        else:
            out.append(f'{c_on}Avg total attacks: {avg2["total_attacks"]-avg1["total_attacks"]:>20,.2f} more{c_off}{">> BUILD 2":>20}')
        if avg1["total_damage"] > avg2["total_damage"]:
            out.append(f'{c_on}Avg total damage: {avg1["total_damage"]-avg2["total_damage"]:>21,.2f} more{c_off}{">> BUILD 1":>20}')
        else:
            out.append(f'{c_on}Avg total damage: {avg2["total_damage"]-avg1["total_damage"]:>21,.2f} more{c_off}{">> BUILD 2":>20}')
        if hunter_class == Borge:
            if avg1["total_crits"] > avg2["total_crits"]:
                out.append(f'{c_on}Avg total crits: {avg1["total_crits"]-avg2["total_crits"]:>22,.2f} more{c_off}{">> BUILD 1":>20}')
            else:
                out.append(f'{c_on}Avg total crits: {avg2["total_crits"]-avg1["total_crits"]:>22,.2f}) more{c_off}{">> BUILD 2":>20}')
            if avg1["total_extra_from_crits"] > avg2["total_extra_from_crits"]:
                out.append(f'{c_on}Avg total extra from crits: {avg1["total_extra_from_crits"]-avg2["total_extra_from_crits"]:>11,.2f} more{c_off}{">> BUILD 1":>20}')
            else:
                out.append(f'{c_on}Avg total extra from crits: {avg2["total_extra_from_crits"]-avg1["total_extra_from_crits"]:>11,.2f} more{c_off}{">> BUILD 2":>20}')
        elif hunter_class == Ozzy:
            if avg1["total_multistrikes"] > avg2["total_multistrikes"]:
                out.append(f'{c_on}Avg total multistrikes: {avg1["total_multistrikes"]-avg2["total_multistrikes"]:>15.2f} more{c_off}{">> BUILD 1":>20}')
            else:
                out.append(f'{c_on}Avg total multistrikes: {avg2["total_multistrikes"]-avg1["total_multistrikes"]:>15.2f} more{c_off}{">> BUILD 2":>20}')
            if avg1["total_ms_extra_damage"] > avg2["total_ms_extra_damage"]:
                out.append(f'{c_on}Avg total extra from ms: {avg1["total_ms_extra_damage"]-avg2["total_ms_extra_damage"]:>14.2f} more{c_off}{">> BUILD 1":>20}')
            else:
                out.append(f'{c_on}Avg total extra from ms: {avg2["total_ms_extra_damage"]-avg1["total_ms_extra_damage"]:>14.2f} more{c_off}{">> BUILD 2":>20}')
        c_on = '\033[38;2;1;163;87m' if coloured else ''
        out.append(f'{c_on}Sustain:{c_off}')
        out.append(f'{c_on}{divider}{c_off}')
        if avg1["total_taken"] > avg2["total_taken"]:
            out.append(f'{c_on}Avg total taken: {avg1["total_taken"]-avg2["total_taken"]:>22,.2f} less{c_off}{">> BUILD 2":>20}')
        else:
            out.append(f'{c_on}Avg total taken: {avg2["total_taken"]-avg1["total_taken"]:>22,.2f} less{c_off}{">> BUILD 1":>20}')
        if avg1["total_regen"] > avg2["total_regen"]:
            out.append(f'{c_on}Avg total regen: {avg1["total_regen"]-avg2["total_regen"]:>22,.2f} more{c_off}{">> BUILD 1":>20}')
        else:
            out.append(f'{c_on}Avg total regen: {avg2["total_regen"]-avg1["total_regen"]:>22,.2f} more{c_off}{">> BUILD 2":>20}')
        if avg1["total_attacks_suffered"] > avg2["total_attacks_suffered"]:
            out.append(f'{c_on}Avg total attacks taken: {avg1["total_attacks_suffered"]-avg2["total_attacks_suffered"]:>14,.2f} more{c_off}{">> BUILD 1":>20}')
        else:
            out.append(f'{c_on}Avg total attacks taken: {avg2["total_attacks_suffered"]-avg1["total_attacks_suffered"]:>14,.2f} more{c_off}{">> BUILD 2":>20}')
        if avg1["total_lifesteal"] > avg2["total_lifesteal"]:
            out.append(f'{c_on}Avg total lifesteal: {avg1["total_lifesteal"]-avg2["total_lifesteal"]:>18,.2f} more{c_off}{">> BUILD 1":>20}')
        else:
            out.append(f'{c_on}Avg total lifesteal: {avg2["total_lifesteal"]-avg1["total_lifesteal"]:>18,.2f} more{c_off}{">> BUILD 2":>20}')
        c_on = '\033[38;2;234;186;1m' if coloured else ''
        out.append(f'{c_on}Defence:{c_off}')
        out.append(f'{c_on}{divider}{c_off}')
        if avg1["total_evades"] > avg2["total_evades"]:
            out.append(f'{c_on}Avg total evades: {avg1["total_evades"]-avg2["total_evades"]:>21,.2f} more{c_off}{">> BUILD 1":>20}')
        else:
            out.append(f'{c_on}Avg total evades: {avg2["total_evades"]-avg1["total_evades"]:>21,.2f} more{c_off}{">> BUILD 2":>20}')
        if hunter_class == Ozzy:
            if avg1["total_trickster_evades"] > avg2["total_trickster_evades"]:
                out.append(f'{c_on}Avg trickster evades: {avg1["total_trickster_evades"]-avg2["total_trickster_evades"]:>17,.2f} more{c_off}{">> BUILD 1":>20}')
            else:
                out.append(f'{c_on}Avg trickster evades: {avg2["total_trickster_evades"]-avg1["total_trickster_evades"]:>17,.2f} more{c_off}{">> BUILD 2":>20}')
        if avg1["total_mitigated"] > avg2["total_mitigated"]:
            out.append(f'{c_on}Avg total mitigated: {avg1["total_mitigated"]-avg2["total_mitigated"]:>18,.2f} more{c_off}{">> BUILD 1":>20}')
        else:
            out.append(f'{c_on}Avg total mitigated: {avg2["total_mitigated"]-avg1["total_mitigated"]:>18,.2f} more{c_off}{">> BUILD 2":>20}')
        c_on = '\033[38;2;14;156;228m' if coloured else ''
        out.append(f'{c_on}Effects:{c_off}')
        out.append(f'{c_on}{divider}{c_off}')
        if avg1["total_effect_procs"] > avg2["total_effect_procs"]:
            out.append(f'{c_on}Avg total effect procs: {avg1["total_effect_procs"]-avg2["total_effect_procs"]:>15,.2f} more{c_off}{">> BUILD 1":>20}')
        else:
            out.append(f'{c_on}Avg total effect procs: {avg2["total_effect_procs"]-avg1["total_effect_procs"]:>15,.2f} more{c_off}{">> BUILD 2":>20}')
        if hunter_class == Borge:
            if avg1["total_helltouch"] > avg2["total_helltouch"]:
                out.append(f'{c_on}Avg total helltouch: {avg1["total_helltouch"]-avg2["total_helltouch"]:>18,.2f} more{c_off}{">> BUILD 1":>20}')
            else:
                out.append(f'{c_on}Avg total helltouch: {avg2["total_helltouch"]-avg1["total_helltouch"]:>18,.2f} more{c_off}{">> BUILD 2":>20}')
            if avg1["total_loth"] > avg2["total_loth"]:
                out.append(f'{c_on}Avg total loth: {avg1["total_loth"]-avg2["total_loth"]:>23,.2f} more{c_off}{">> BUILD 1":>20}')
            else:
                out.append(f'{c_on}Avg total loth: {avg2["total_loth"]-avg1["total_loth"]:>23,.2f} more{c_off}{">> BUILD 2":>20}')
        if avg1["total_potion"] > avg2["total_potion"]:
            out.append(f'{c_on}Avg total potion: {avg1["total_potion"]-avg2["total_potion"]:>21,.2f} more{c_off}{">> BUILD 1":>20}')
        else:
            out.append(f'{c_on}Avg total potion: {avg2["total_potion"]-avg1["total_potion"]:>21,.2f} more{c_off}{">> BUILD 2":>20}')
        out.append(f'{c_on}{divider}{c_off}')
        c_on = '\033[38;2;98;65;169m' if coloured else ''
        out.append(f'{c_on}Loot:{c_off} (arbitrary values, for comparison only)')
        out.append(f'{c_on}{divider}{c_off}')
        if avg1["lph"] > avg2["lph"]:
            out.append(f'{c_on}Avg LPH: {avg1["lph"]-avg2["lph"]:>30,.2f} more{c_off}{">> BUILD 1":>20}')
        else:
            out.append(f'{c_on}Avg LPH: {avg2["lph"]-avg1["lph"]:>30,.2f} more{c_off}{">> BUILD 2":>20}')
        if max(res1["lph"]) > max(res2["lph"]):
            out.append(f'{c_on}Best LPH: {max(res1["lph"])-max(res2["lph"]):>29.3} more{c_off}{">> BUILD 1":>20}')
        else:
            out.append(f'{c_on}Best LPH: {max(res2["lph"])-max(res1["lph"]):>29.3} more{c_off}{">> BUILD 2":>20}')
        if min(res1["lph"]) > min(res2["lph"]):
            out.append(f'{c_on}Worst LPH: {min(res1["lph"])-min(res2["lph"]):>28.3} more{c_off}{">> BUILD 1":>20}')
        else:
            out.append(f'{c_on}Worst LPH: {min(res2["lph"])-min(res1["lph"]):>28.3} more{c_off}{">> BUILD 2":>20}')
        out.append(f'{c_on}{divider}{c_off}')
        out.append(f'Final stage reached by BUILD 1:  MAX({max(res1["final_stage"])}), MED({floor(statistics.median(res1["final_stage"]))}), AVG({floor(statistics.mean(res1["final_stage"]))}), MIN({min(res1["final_stage"])})')
        out.append(f'Final stage reached by BUILD 2:  MAX({max(res2["final_stage"])}), MED({floor(statistics.median(res2["final_stage"]))}), AVG({floor(statistics.mean(res2["final_stage"]))}), MIN({min(res2["final_stage"])})')
        out.append('')
        # stage_out = []
        # final_stage_pct = {i:j/len(res_dict["final_stage"]) for i,j in Counter(res_dict["final_stage"]).items()}
        # for i, k in enumerate(sorted([*final_stage_pct])):
        #     stage_out.append(f'{k:>3d}: {final_stage_pct[k]:>6.2%}   ' + ("\n" if (i + 1) % 5 == 0 and i > 0 else ""))
        # out.append(''.join(stage_out))
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
                if 'trample' in hunter.mods and not isinstance(self.enemies[0], Boss):
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
                        case 'hunter_special':
                            hunter.attack(enemy)
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
    num_sims = 100
    if num_sims == 1:
        logging.basicConfig(
            filename='./logs/ozzy_test.txt',
            filemode='w',
            force=True,
            level=logging.DEBUG,
        )
        logging.getLogger().setLevel(logging.DEBUG)
    smgr = SimulationManager('./builds/current_borge.yaml')
    res = smgr.run_sims(num_sims, threaded=-1)
    smgr.pprint_res(res, 'Test')


if __name__ == "__main__":
    main()