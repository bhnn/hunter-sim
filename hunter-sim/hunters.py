import logging
import random
from heapq import heappush as hpush
from typing import Dict, List, Tuple

import yaml
from util.exceptions import BuildConfigError

hunter_name_spacing: int = 7

# TODO: maybe find a better way to trample()
# TODO: validate vectid elixir
# TODO: Ozzy: move @property code to on_death() to speed things up?
# TODO: Borge: move @property code as well?
# TODO: DwD power is a little off: 200 ATK, 2 exo, 3 DwD, 1 revive should be 110.59 power but is 110.71. I think DwD might be 0.0196 power instead of 0.02
# TODO: confirm how creation nodes 2+3 apply

""" Assumptions:
- order of attacks: main -> ms -> echo -> echo ms
- only the main attack can stun
- multistrike damage (irrespective of trigger source) always depends on main attack power
"""

class Hunter:
    ### SETUP
    def __init__(self, name: str) -> None:
        self.name = name
        self.missing_hp: float
        self.missing_hp_pct: float
        self.sim = None
        self.catching_up: bool = True

        # statistics
        # main
        self.current_stage = 0
        self.total_kills: int = 0
        self.elapsed_time: int = 0
        self.times_revived: int = 0
        self.revive_log = []
        self.enrage_log = []

        # offence
        self.total_attacks: int = 0
        self.total_damage: float = 0

        # sustain
        self.total_taken: float = 0
        self.total_regen: float = 0
        self.total_attacks_suffered: int = 0
        self.total_lifesteal: float = 0

        # defence
        self.total_evades: int = 0
        self.total_mitigated: float = 0

        # effects
        self.total_effect_procs: int = 0
        self.total_stuntime_inflicted: float = 0

        # loot
        self.total_loot: float = 0

    @classmethod
    def from_file(cls, file_path: str) -> 'Hunter':
        """Create a Hunter instance from a build config file.

        Args:
            file_path (str): The path to the build config file.

        Returns:
            Hunter: The Hunter instance.
        """
        with open(file_path, 'r') as f:
            cfg = yaml.safe_load(f)
        if cfg["meta"]["hunter"].lower() not in ["borge", "ozzy"]:
            raise ValueError("hunter_sim.py: error: invalid hunter found in primary build config file. Please specify a valid hunter.")
        if cls != Hunter:
            return cls(cfg)
        else:
            return globals()[cfg["meta"]["hunter"].title()](cfg)

    def as_dict(self) -> dict:
        """Create a build config dictionary from a loaded hunter instance.

        Returns:
            dict: The hunter build dict.
        """
        return {
            "meta": self.meta,
            "stats": self.base_stats,
            "talents": self.talents,
            "attributes": self.attributes,
            "mods": self.mods,
            "inscryptions": self.inscryptions,
            "relics": self.relics,
            "gems": self.gems,
        }

    def get_results(self) -> List:
        """Fetch the hunter results for end-of-run statistics.

        Returns:
            List: List of all collected stats.
        """
        return {
            'final_stage': self.current_stage,
            'kills': self.total_kills,
            'revive_log': self.revive_log,
            'enrage_log': self.enrage_log,
            'attacks': self.total_attacks,
            'damage': self.total_damage,
            'damage_taken': self.total_taken,
            'regenerated_hp': self.total_regen,
            'attacks_suffered': self.total_attacks_suffered,
            'lifesteal': self.total_lifesteal,
            'evades': self.total_evades,
            'mitigated_damage': self.total_mitigated,
            'effect_procs': self.total_effect_procs,
            'total_loot': self.total_loot,
            'stun_duration_inflicted': self.total_stuntime_inflicted,
        }

    @staticmethod
    def load_dummy() -> dict:
        """Abstract placeholder for load_dummy() method. Must be implemented by child classes.

        Raises:
            NotImplementedError: When called from the Hunter class.

        Returns:
            dict: The dummy build dict, created by the child class.
        """
        raise NotImplementedError('load_dummy() not implemented for Hunter() base class')

    def load_build(self, config_dict: Dict) -> None:
        """Load a build config from build config dict, validate it and assign the stats to the hunter's internal dictionaries.

        Args:
            config_dict (dict): A build config dictionary object.

        Raises:
            ValueError: If the config file is invalid.
        """
        if not (invalid_keys := self.validate_config(config_dict)) == set():
            raise BuildConfigError(invalid_keys)
        self.meta = config_dict["meta"]
        self.base_stats = config_dict["stats"]
        self.talents = config_dict["talents"]
        self.attributes = config_dict["attributes"]
        self.mods = config_dict["mods"]
        self.inscryptions = {k: self.costs["inscryptions"][k]["max"] if v == "max" else v for k, v in config_dict["inscryptions"].items()}
        self.relics = config_dict["relics"]
        self.gems = config_dict["gems"]

    def validate_config(self, cfg: Dict) -> bool:
        """Validate a build config dict against a perfect dummy build to see if they have identical keys in themselves and all value entries.

        Args:
            cfg (dict): The build config

        Returns:
            bool: Whether the configs contain identical keys.
        """
        return (set(cfg.keys()) ^ set(self.load_dummy().keys())) | set().union(*cfg.values()) ^ set().union(*self.load_dummy().values())

    def validate_build(self) -> Tuple[int, int, set, int, int]:
        """Validate the attributes of a build to make sure no attribute maximum levels are exceeded.

        Raises:
            ValueError: When the function is called from a Hunter instance.

        Returns:
            Tuple[int, int, set, int, int]: Attribute points spent, points available, any invalid points found, talent points spent, points available
        """
        if self.__class__ == Hunter:
            raise ValueError('Cannot validate a Hunter() instance.')
        invalid, attr_spent, tal_spent = set(), 0, 0
        # go through all talents and attributes and check if they are within the valid range, then add their cost to the total
        for tal in self.talents.keys():
            if (lvl := self.talents[tal]) > self.costs["talents"][tal]["max"]:
                invalid.add(tal)
            tal_spent += lvl
        for att in self.attributes.keys():
            if (lvl := self.attributes[att]) > self.costs["attributes"][att]["max"]:
                invalid.add(att)
            attr_spent += lvl * self.costs["attributes"][att]["cost"]
        return attr_spent, (self.meta["level"] * 3), invalid, tal_spent, (self.meta["level"])

    def attack(self, target, damage: float) -> None:
        """Attack the enemy unit.

        Args:
            target (Enemy): The enemy to attack.
            damage (float): The amount of damage to deal.
        """
        target.receive_damage(damage)

    def receive_damage(self, damage: float) -> float:
        """Receive damage from an attack. Accounts for damage reduction, evade chance and reflected damage.

        Args:
            damage (float): The amount of damage to receive.
        """
        if random.random() < self.evade_chance:
            self.total_evades += 1
            logging.debug(f'[{self.name:>{hunter_name_spacing}}][@{self.sim.elapsed_time:>5}]:\tEVADE')
            return 0
        else:
            mitigated_damage = damage * (1 - self.damage_reduction)
            self.hp -= mitigated_damage
            self.total_taken += mitigated_damage
            self.total_mitigated += (damage - mitigated_damage)
            self.total_attacks_suffered += 1
            logging.debug(f"[{self.name:>{hunter_name_spacing}}][@{self.sim.elapsed_time:>5}]:\tTAKE\t{mitigated_damage:>6.2f}, {self.hp:.2f} HP left")
            if self.is_dead():
                self.on_death()
            return mitigated_damage

    def heal_hp(self, value: float, source: str) -> None:
        """Applies healing to hp from different sources. Accounts for overhealing.

        Args:
            value (float): The amount of hp to heal.
            source (str): The source of the healing. Valid: regen, lifesteal, life_of_the_hunt
        """
        effective_heal = min(value, self.missing_hp)
        overhealing = value - effective_heal
        self.hp += effective_heal
        logging.debug(f'[{self.name:>{hunter_name_spacing}}][@{self.sim.elapsed_time:>5}]:\t{source.upper().replace("_", " ")}\t{effective_heal:>6.2f} (+{overhealing:>6.2f} OVERHEAL)')
        match source.lower():
            case 'regen':
                self.total_regen += effective_heal
            case 'steal':
                self.total_lifesteal += effective_heal
            case 'loth':
                self.total_loth += effective_heal
            case 'potion':
                self.total_potion += effective_heal
            case _:
                raise ValueError(f'Unknown heal source: {source}')

    def on_kill(self) -> None:
        """Actions to take when the hunter kills an enemy. The Hunter() implementation only handles loot.
        """
        loot = self.compute_loot()
        if (self.current_stage % 100 != 0 and self.current_stage > 0) and random.random() < self.effect_chance and (LL := self.talents["call_me_lucky_loot"]):
            # Talent: Call Me Lucky Loot, cannot proc on bosses
            loot *= 1 + (self.talents["call_me_lucky_loot"] * 0.2)
            self.total_effect_procs += 1
        loot *= (1 + 0.25 * self.gems["attraction_node_#3"])
        self.total_loot += loot

    def complete_stage(self, stages: int = 1) -> None:
        """Actions to take when the hunter completes a stage. The Hunter() implementation only handles stage progression.

        Args:
            stages (int, optional): The number of stages to complete. Defaults to 1.
        """
        self.current_stage += stages
        if self.current_stage >= 100:
            self.catching_up = False

    def compute_loot(self) -> float:
        """Compute the amount of loot gained from a kill. Affected by stage loot bonus, talents and attributes.

        Returns:
            float: The amount of loot gained.
        """
        stage_mult = (1.05 ** (self.current_stage+1)) * (5 if self.current_stage >= 101 else 1)
        if isinstance(self, Borge):
            base_loot = 1.0 if self.current_stage != 100 else (700 + 500 + 60 + 50)
            timeless_mastery = 1 + self.attributes["timeless_mastery"] * 0.14
            additional_multipliers = 1 + (self.inscryptions["i60"] * 0.03)
        elif isinstance(self, Ozzy):
            base_loot = 1.0 if self.current_stage != 100 else (400 + 300 + 60 + 50)
            timeless_mastery = 1 + (self.attributes["timeless_mastery"] * 0.16)
            additional_multipliers = 1
        return base_loot * 0.01 * stage_mult * timeless_mastery * additional_multipliers

    def is_dead(self) -> bool:
        """Check if the hunter is dead.

        Returns:
            bool: True if the hunter is dead, False otherwise.
        """
        return self.hp <= 0

    def on_death(self) -> None:
        """Actions to take when the hunter dies. Logs the revive and resets the hp to 80% of max hp if a `Death is my Companion`
        charge can be used. If no revives are left, the hunter is marked as dead.
        """
        if self.times_revived < self.talents["death_is_my_companion"]:
            self.hp = self.max_hp * 0.8
            self.revive_log.append(self.current_stage)
            self.times_revived += 1
            logging.debug(f'[{self.name:>{hunter_name_spacing}}][@{self.sim.elapsed_time:>5}]:\tREVIVED, {self.talents["death_is_my_companion"] - self.times_revived} left')
        else:
            logging.debug(f'[{self.name:>{hunter_name_spacing}}][@{self.sim.elapsed_time:>5}]:\tDIED\n')


    ### UTILITY
    @property
    def missing_hp(self) -> float:
        return self.max_hp - self.hp

    @property
    def missing_hp_pct(self) -> float:
        return round((1 - self.hp / self.max_hp) * 100, 0)

    def show_build(self, in_colour: bool = True) -> None:
        """Prints the build of this Hunter's instance.
        """
        c_off = '\033[0m'
        c_on = '\033[38;2;128;128;128m'
        attr_spent, attr_avail, invalid, tal_spent, tal_avail = self.validate_build()
        if tal_spent > tal_avail:
            tals = f'(\033[91m{tal_spent:>3}\033[0m/{c_on}{tal_avail:>3}{c_off})'
        else:
            tals = f'({tal_spent:>3}/{c_on}{tal_avail:>3}{c_off})'
        if attr_spent > attr_avail:
            attr = f'(\033[91m{attr_spent:>3}\033[0m/{c_on}{attr_avail:>3}{c_off})'
        else:
            attr = f'({attr_spent:>3}/{c_on}{attr_avail:>3}{c_off})'
        invalid_out = f'\033[91mInvalid\033[0m:\t{(", ".join(invalid)).title()}'
        gem_names = {
            "attraction_gem": "ATT",
            "attraction_catch-up": "C0-99",
            "attraction_node_#3": "AN-3",
            "innovation_node_#3" : "IN-3",
            "creation_node_#1": "CR-1",
            "creation_node_#2": "CR-2",
            "creation_node_#3": "CR-3",
        }
        gem_state = {
            0: u'\u2718',
            1: u'\u2714',
        }
        if not in_colour:
            c_on = c_off
        print(self)
        print('Stats {}:\t{} {} {}   {} {} {}   {} {} {}'.format(f'({c_on}l.{c_off}{self.meta["level"]:>3})', *self.base_stats.values()))
        print(f'Tal {tals}:\t' + ' '.join('[{}{}{}: {}]'.format(c_on, ''.join([l[0].upper() for l in k.split('_')]), c_off, v) for k, v in self.talents.items()))
        print(f'Att {attr}:\t' + ' '.join('[{}{}{}: {}]'.format(c_on, ''.join([l[0].upper() for l in k.split('_')]), c_off, v) for k, v in self.attributes.items()))
        print(f'Gems:\t\t' + ' '.join('[{}{}{}: {}]'.format(c_on, ''.join(gem_names[k]), c_off, gem_state[v] if k not in ['attraction_gem', 'attraction_catch-up'] else v) for k, v in self.gems.items()))
        print(f'Relics:\t\t' + ' '.join('[{}{}{}: {}]'.format(c_on, ''.join([l[0].upper() for l in k.split('_')]), c_off, v) for k, v in self.relics.items()))
        if invalid:
            print(invalid_out)
        print('\n'.join(['-'*120]))

    def __str__(self) -> str:
        """Prints the stats of this Hunter's instance.

        Returns:
            str: The stats as a formatted string.
        """
        return f'[{self.name:>{hunter_name_spacing}}]:\t[HP:{(str(round(self.hp, 2)) + "/" + str(round(self.max_hp, 2))):>18}] [AP:{self.power:>8.2f}] [Regen:{self.regen:>7.2f}] [DR: {self.damage_reduction:>6.2%}] [Evasion: {self.evade_chance:>6.2%}] [Effect: {self.effect_chance:>6.2%}] [SpC: {self.special_chance:>6.2%}] [SpD: {self.special_damage:>5.2f}] [Speed:{self.speed:>5.2f}] [LS: {self.lifesteal:>4.2%}]'


class Borge(Hunter):
    ### SETUP
    costs = {
        "talents": {
            "death_is_my_companion": { # +1 revive at 80% hp
                "cost": 1,
                "max": 2,
            },
            "life_of_the_hunt": { # chance on hit to heal for x0.06 damage dealt
                "cost": 1,
                "max": 5,
            },
            "unfair_advantage": { # chance to heal x0.02 max hp on kill
                "cost": 1,
                "max": 5,
            },
            "impeccable_impacts": { # chance to stun on hit, grants +2 attack power per point
                "cost": 1,
                "max": 10,
            },
            "omen_of_defeat": { # -0.08 enemy regen
                "cost": 1,
                "max": 10,
            },
            "call_me_lucky_loot": { # chance on kill to gain x0.2 increased loot per point
                "cost": 1,
                "max": 10,
            },
            "presence_of_god": { # -0.04 enemy starting hp per point
                "cost": 1,
                "max": 15,
            },
            "fires_of_war": { # chance on hit to double attack speed for 0.1 seconds per point
                "cost": 1,
                "max": 15,
            },
        },
        "attributes": {
            "soul_of_ares": { # x0.01 hp, x0.02 power
                "cost": 1,
                "max": float("inf"),
            },
            "essence_of_ylith": { # +0.04 regen, x0.009 hp
                "cost": 1,
                "max": float("inf"),
            },
            "spartan_lineage": { # +0.015 dr
                "cost": 2,
                "max": 6,
            },
            "timeless_mastery": { # +0.14 loot
                "cost": 3,
                "max": 5,
            },
            "helltouch_barrier": { # +0.08 reflected damage
                "cost": 2,
                "max": 10,
            },
            "lifedrain_inhalers": { # +0.0008 missing health regen
                "cost": 2,
                "max": 10,
            },
            "explosive_punches": { # +0.044 special chance, +0.08 special damage
                "cost": 3,
                "max": 6,
            },
            "book_of_baal": { # +0.0111 lifesteal
                "cost": 3,
                "max": 6,
            },
            "superior_sensors": { # +0.016 evade chance, +0.012 effect chance
                "cost": 2,
                "max": 6,
            },
            "atlas_protocol": { # +0.007 damage reduction, +0.014 effect chance, +0.025 special chance, x-0.04% speed
                "cost": 3,
                "max": 6,
            },
            "weakspot_analysis": { # -0.11 crit damage taken reduction
                "cost": 2,
                "max": 6,
            },
            "born_for_battle": { # +0.001 power per 1% missing hp
                "cost": 5,
                "max": 3,
            },
        },
        "inscryptions": {
            "i3": { # +6 hp
                "cost": 1,
                "max": 8,
            },
            "i4": { # +0.0065 crit chance
                "cost": 1,
                "max": 6,
            },
            "i11": { # +0.02 effect chance
                "cost": 1,
                "max": 3,
            },
            "i13": { # +8 power
                "cost": 1,
                "max": 8,
            },
            "i14": { # +1.1 loot
                "cost": 1,
                "max": 5,
            },
            "i23": { # -0.04 speed
                "cost": 1,
                "max": 5,
            },
            "i24": { # +0.004 damage reduction
                "cost": 1,
                "max": 8,
            },
            "i27": { # +24 hp
                "cost": 1,
                "max": 10,
            },
            "i44": { # +1.08 loot
                "cost": 1,
                "max": 10,
            },
            "i60": { # +0.03 hp, power, loot
                "cost": 1,
                "max": 10,
            },
        },
    }

    def __init__(self, config_dict: Dict):
        super(Borge, self).__init__(name='Borge')
        self.__create__(config_dict)

        # statistics
        # offence
        self.total_crits: int = 0
        self.total_extra_from_crits: float = 0
        self.total_helltouch: float = 0

        # sustain
        self.total_loth: float = 0
        self.total_potion: float = 0
        self.total_inhaler: float = 0

    def __create__(self, config_dict: Dict) -> None:
        """Create a Borge instance from a build config dict. Computes all final stats from stat growth formulae and additional
        power sources.

        Args:
            config_dict (dict): Build config dictionary object.
        """
        self.load_build(config_dict)
        # hp
        self.max_hp = (
            (
                43
                + (self.base_stats["hp"] * (2.50 + 0.01 * (self.base_stats["hp"] // 5)))
                + (self.inscryptions["i3"] * 6)
                + (self.inscryptions["i27"] * 24)
            )
            * (1 + (self.attributes["soul_of_ares"] * 0.01))
            * (1 + (self.inscryptions["i60"] * 0.03))
            * (1 + (self.relics["disk_of_dawn"] * 0.02))
            * (1 + (0.015 * (self.meta["level"] - 39)) * self.gems["creation_node_#3"])
            * (1 + (0.02 * self.gems["creation_node_#2"]))
            * (1 + (0.2 * self.gems["creation_node_#1"]))
        )
        self.hp = self.max_hp
        # power
        self.power = (
            (
                3
                + (self.base_stats["power"] * (0.5 + 0.01 * (self.base_stats["power"] // 10)))
                + (self.inscryptions["i13"] * 1)
                + (self.talents["impeccable_impacts"] * 2)
            )
            * (1 + (self.attributes["soul_of_ares"] * 0.002))
            * (1 + (self.inscryptions["i60"] * 0.03))
            * (1 + (self.relics["long_range_artillery_crawler"] * 0.02))
            * (1 + (0.01 * (self.meta["level"] - 39)) * self.gems["creation_node_#3"])
            * (1 + (0.02 * self.gems["creation_node_#2"]))
            * (1 + (0.03 * self.gems["innovation_node_#3"]))
        )
        # regen
        self.regen = (
            (
                0.02
                + (self.base_stats["regen"] * (0.03 + 0.01 * (self.base_stats["regen"] // 30)))
                + (self.attributes["essence_of_ylith"] * 0.04)
            )
            * (1 + (self.attributes["essence_of_ylith"] * 0.009))
            * (1 + (0.005 * (self.meta["level"] - 39)) * self.gems["creation_node_#3"])
            * (1 + (0.02 * self.gems["creation_node_#2"]))
        )
        # damage_reduction
        self.damage_reduction = (
            (
                0
                + (self.base_stats["damage_reduction"] * 0.0144)
                + (self.attributes["spartan_lineage"] * 0.015)
                + (self.inscryptions["i24"] * 0.004)
            )
            * (1 + (0.02 * self.gems["creation_node_#2"]))
        )
        # evade_chance
        self.evade_chance = (
            0.01
            + (self.base_stats["evade_chance"] * 0.0034)
            + (self.attributes["superior_sensors"] * 0.016)
        )
        # effect_chance
        self.effect_chance = (
            (
                0.04
                + (self.base_stats["effect_chance"] * 0.005)
                + (self.attributes["superior_sensors"] * 0.012)
                + (self.inscryptions["i11"] * 0.02)
                + (0.03 * self.gems["innovation_node_#3"])
            )
            * (1 + (0.02 * self.gems["creation_node_#2"]))
        )
        # special_chance
        self.special_chance = (
            (
                0.05
                + (self.base_stats["special_chance"] * 0.0018)
                + (self.attributes["explosive_punches"] * 0.044)
                + (self.inscryptions["i4"] * 0.0065)
            )
            * (1 + (0.02 * self.gems["creation_node_#2"]))
        )
        # special_damage
        self.special_damage = (
            1.30
            + (self.base_stats["special_damage"] * 0.01)
            + (self.attributes["explosive_punches"] * 0.08)
        )
        # speed
        self.speed = (
            5
            - (self.base_stats["speed"] * 0.03)
            - (self.inscryptions["i23"] * 0.04)
        )
        # lifesteal
        self.lifesteal = (self.attributes["book_of_baal"] * 0.0111)
        self.fires_of_war: float = 0

    @staticmethod
    def load_dummy() -> dict:
        """Create a dummy build dictionary with empty stats to compare against loaded configs.

        Returns:
            dict: The dummy build dict.
        """
        return {
            "meta": {
                "hunter": "Borge",
                "level": 0
            },
            "stats": {
                "hp": 0,
                "power": 0,
                "regen": 0,
                "damage_reduction": 0,
                "evade_chance": 0,
                "effect_chance": 0,
                "special_chance": 0,
                "special_damage": 0,
                "speed": 0,
            },
            "talents": {
                "death_is_my_companion": 0,
                "life_of_the_hunt": 0,
                "unfair_advantage": 0,
                "impeccable_impacts": 0,
                "omen_of_defeat": 0,
                "call_me_lucky_loot": 0,
                "presence_of_god": 0,
                "fires_of_war": 0
            },
            "attributes": {
                "soul_of_ares": 0,
                "essence_of_ylith": 0,
                "helltouch_barrier": 0,
                "book_of_baal": 0,
                "spartan_lineage": 0,
                "explosive_punches": 0,
                "lifedrain_inhalers": 0,
                "superior_sensors": 0,
                "born_for_battle": 0,
                "timeless_mastery": 0,
                "weakspot_analysis": 0,
                "atlas_protocol": 0,
            },
            "inscryptions": {
                "i3": 0,  # 6 borge hp
                "i4": 0,  # 0.0065 borge crit
                "i11": 0, # 0.02 borge effect chance
                "i13": 0, # 8 borge power
                "i14": 0, # 1.1 borge loot
                "i23": 0, # 0.04 borge speed
                "i24": 0, # 0.004 borge dr
                "i27": 0, # 24 borge hp
                "i44": 0, # 1.08 borge loot
                "i60": 0, # 0.03 borge hp, power, loot
            },
            "mods": {
                "trample": False,
            },
            "relics": {
                "disk_of_dawn": 0,
                "long_range_artillery_crawler": 0,
            },
            "gems": {
                "attraction_gem": 0,
                "attraction_catch-up": 0,
                "attraction_node_#3": 0,
                "innovation_node_#3" : 0,
                "creation_node_#1": 0,
                "creation_node_#2": 0,
                "creation_node_#3": 0,
            },
        }

    def attack(self, target) -> None:
        """Attack the enemy unit.

        Args:
            target (_type_): The enemy to attack.
        """
        if random.random() < self.special_chance:
            damage = self.power * self.special_damage
            self.total_crits += 1
            self.total_extra_from_crits += (damage - self.power)
            logging.debug(f"[{self.name:>{hunter_name_spacing}}][@{self.sim.elapsed_time:>5}]:\tATTACK\t{damage:>6.2f} (crit)")
        else:
            damage = self.power
            logging.debug(f"[{self.name:>{hunter_name_spacing}}][@{self.sim.elapsed_time:>5}]:\tATTACK\t{damage:>6.2f}")
        super(Borge, self).attack(target, damage)
        self.total_damage += damage
        self.total_attacks += 1

        #  on_attack() effects
        self.heal_hp(damage * self.lifesteal, 'steal')
        if random.random() < self.effect_chance and (LotH := self.talents["life_of_the_hunt"]):
            # Talent: Life of the Hunt
            LotH_healing = damage * LotH * 0.06
            self.heal_hp(LotH_healing, "loth")
            self.total_loth += LotH_healing
            self.total_effect_procs += 1
        if random.random() < self.effect_chance and self.talents["impeccable_impacts"]:
            # Talent: Impeccable Impacts, will call Hunter.apply_stun()
            hpush(self.sim.queue, (0, 0, 'stun'))
            self.total_effect_procs += 1
        if random.random() < self.effect_chance and self.talents["fires_of_war"]:
            # Talent: Fires of War
            self.apply_fow()
            self.total_effect_procs += 1

    def receive_damage(self, attacker, damage: float, is_crit: bool) -> None:
        """Receive damage from an attack. Accounts for damage reduction, evade chance and reflected damage.

        Args:
            attacker (Enemy): The unit that is attacking. Used to apply damage reflection.
            damage (float): The amount of damage to receive.
            is_crit (bool): Whether the attack was a critical hit or not.
        """
        if is_crit:
            reduced_crit_damage = damage * (1 - self.attributes["weakspot_analysis"] * 0.11)
            final_damage = super(Borge, self).receive_damage(reduced_crit_damage)
        else:
            final_damage = super(Borge, self).receive_damage(damage)
        if (not self.is_dead()) and final_damage > 0:
            helltouch_effect = (0.1 if (self.current_stage % 100 == 0 and self.current_stage > 0) else 1)
            reflected_damage = final_damage * self.attributes["helltouch_barrier"] * 0.08 * helltouch_effect
            self.total_helltouch += reflected_damage
            attacker.receive_damage(reflected_damage, is_reflected=True)

    def regen_hp(self) -> None:
        """Regenerates hp according to the regen stat, modified by the `Lifedrain Inhalers` attribute.
        """
        inhaler_contrib = ((self.attributes["lifedrain_inhalers"] * 0.0008) * self.missing_hp)
        regen_value = self.regen + inhaler_contrib
        self.total_inhaler += inhaler_contrib
        self.heal_hp(regen_value, 'regen')

    ### SPECIALS
    def on_kill(self) -> None:
        """Actions to take when the hunter kills an enemy. Loot is handled by the parent class.
        """
        super(Borge, self).on_kill()
        if random.random() < self.effect_chance and (ua := self.talents["unfair_advantage"]):
            # Talent: Unfair Advantage
            potion_healing = self.max_hp * (ua * 0.02)
            self.heal_hp(potion_healing, "potion")
            self.total_potion += potion_healing
            self.total_effect_procs += 1

    def apply_stun(self, enemy, is_boss: bool) -> None:
        """Apply a stun to an enemy.

        Args:
            enemy (Enemy): The enemy to stun.
        """
        stun_effect = 0.5 if is_boss else 1
        stun_duration = self.talents['impeccable_impacts'] * 0.1 * stun_effect
        enemy.stun(stun_duration)
        self.total_stuntime_inflicted += stun_duration

    def apply_pog(self, enemy) -> None:
        """Apply the Presence of a God effect to an enemy.

        Args:
            enemy (Enemy): The enemy to apply the effect to.
        """
        stage_effect = 0.5 if self.current_stage % 100 == 0 and self.current_stage > 0 else 1
        pog_effect = (self.talents["presence_of_god"] * 0.04) * stage_effect
        enemy.hp = enemy.max_hp * (1 - pog_effect)

    def apply_ood(self, enemy) -> None:
        """Apply the Omen of Defeat effect to an enemy.

        Args:
            enemy (Enemy): The enemy to apply the effect to.
        """
        stage_effect = 0.5 if self.current_stage % 100 == 0 and self.current_stage > 0 else 1
        ood_effect = self.talents["omen_of_defeat"] * 0.08 * stage_effect
        enemy.regen = enemy.regen * (1 - ood_effect)

    def apply_fow(self) -> None:
        """Apply the temporaryFires of War effect to Borge.
        """
        self.fires_of_war = self.talents["fires_of_war"] * 0.1
        logging.debug(f'[{self.name:>{hunter_name_spacing}}][@{self.sim.elapsed_time:>5}]:\t[FoW]]\t{self.fires_of_war:>6.2f} sec')

    def apply_trample(self, enemies: List) -> int:
        """Apply the Trample effect to a number of enemies.

        Args:
            enemies (List): The list of enemies to trample.

        Returns:
            int: The number of enemies killed by the trample effect.
        """
        alive_index = [i for i, e in enumerate(enemies) if not e.is_dead()]
        if not alive_index:
            return 0
        trample_kills = 0
        trample_power = min(int(self.power / enemies[0].max_hp), 10)
        if trample_power > 1:
            for i in alive_index[:trample_power]:
                enemies[i].kill()
                trample_kills += 1
        return trample_kills

    ### UTILITY
    @property
    def power(self) -> float:
        """Getter for the power attribute. Accounts for the Born for Battle effect.

        Returns:
            float: The power of the hunter.
        """
        return (
            self._power
            * (1 + (self.missing_hp_pct * self.attributes["born_for_battle"] * 0.001))
            * ((1.08 ** self.gems["attraction_catch-up"]) ** (1 + (self.gems["attraction_gem"] * 0.1) - 0.1) if self.catching_up else 1)
        )

    @power.setter
    def power(self, value: float) -> None:
        self._power = value

    @property
    def damage_reduction(self) -> float:
        """Getter for the damage_reduction attribute. Accounts for the Atlas Protocol attribute.

        Returns:
            float: The damage reduction of the hunter.
        """
        return (self._damage_reduction + self.attributes["atlas_protocol"] * 0.007) if (self.current_stage % 100 == 0 and self.current_stage > 0) else self._damage_reduction

    @damage_reduction.setter
    def damage_reduction(self, value: float) -> None:
        self._damage_reduction = value

    @property
    def effect_chance(self) -> float:
        """Getter for the effect_chance attribute. Accounts for the Atlas Protocol attribute.

        Returns:
            float: The effect chance of the hunter.
        """
        return (self._effect_chance + self.attributes["atlas_protocol"] * 0.014) if (self.current_stage % 100 == 0 and self.current_stage > 0) else self._effect_chance

    @effect_chance.setter
    def effect_chance(self, value: float) -> None:
        self._effect_chance = value

    @property
    def special_chance(self) -> float:
        """Getter for the special_chance attribute. Accounts for the Atlas Protocol attribute.

        Returns:
            float: The special chance of the hunter.
        """
        return (self._special_chance + self.attributes["atlas_protocol"] * 0.025) if (self.current_stage % 100 == 0 and self.current_stage > 0) else self._special_chance

    @special_chance.setter
    def special_chance(self, value: float) -> None:
        self._special_chance = value

    @property
    def speed(self) -> float:
        """Getter for the speed attribute. Accounts for the Fires of War effect and resets it afterwards.

        Returns:
            float: The speed of the hunter.
        """
        current_speed = (self._speed * (1 - self.attributes["atlas_protocol"] * 0.04)) if (self.current_stage % 100 == 0 and self.current_stage > 0) else self._speed
        current_speed /= (1.08 ** self.gems["attraction_catch-up"]) ** (1 + (self.gems["attraction_gem"] * 0.1) - 0.1) if self.catching_up else 1
        current_speed -= self.fires_of_war
        self.fires_of_war = 0
        return current_speed

    @speed.setter
    def speed(self, value: float) -> None:
        self._speed = value

    def get_results(self) -> List:
        """Fetch the hunter results for end-of-run statistics.

        Returns:
            List: List of all collected stats.
        """
        return super(Borge, self).get_results() | {
            'crits': self.total_crits,
            'extra_damage_from_crits': self.total_extra_from_crits,
            'helltouch_barrier': self.total_helltouch,
            'life_of_the_hunt_healing': self.total_loth,
            'unfair_advantage_healing': self.total_potion,
        }

class Ozzy(Hunter):
    ### SETUP
    costs = {
        "talents": {
            "death_is_my_companion": { # +1 revive, 80% of max hp
                "cost": 1,
                "max": 2,
            },
            "tricksters_boon": { # +1 trickster charge
                "cost": 1,
                "max": 1,
            },
            "unfair_advantage": { # chance to heal x0.02 max hp on kill
                "cost": 1,
                "max": 5,
            },
            "thousand_needles": { # -0.06 speed and chance to stun for 0.05s per point on hit
                "cost": 1,
                "max": 10,
            },
            "omen_of_decay": { # x0.08 enemy max hp per hit per point
                "cost": 1,
                "max": 10,
            },
            "call_me_lucky_loot": { # chance on kill to gain x0.2 increased loot per point
                "cost": 1,
                "max": 10,
            },
            "crippling_shots": { # chance on hit to deal x0.03 extra damage per point on the next hit
                "cost": 1,
                "max": 15,
            },
            "echo_bullets": { # chance on hit to deal x0.05 damage per point to enemy
                "cost": 1,
                "max": 15,
            },
        },
        "attributes": {
            "living_off_the_land": { # x0.02 hp, x0.02 regen
                "cost": 1,
                "max": float("inf"),
            },
            "exo_piercers": { # x0.012 power
                "cost": 1,
                "max": float("inf"),
            },
            "timeless_mastery": { # +0.16 loot
                "cost": 3,
                "max": 5,
            },
            "shimmering_scorpion": { # +0.033 lifesteal
                "cost": 3,
                "max": 5,
            },
            "wings_of_ibu": { # +0.026 dr, +0.005 evade chance
                "cost": 2,
                "max": 5,
            },
            "extermination_protocol": { # +0.028 effect chance
                "cost": 2,
                "max": 5,
            },
            "soul_of_snek": { # +0.088 enemy regen reduction
                "cost": 3,
                "max": 5,
            },
            "vectid_elixir": { # x0.15 regen after unfair advantage proc
                "cost": 2,
                "max": 10,
            },
            "cycle_of_death": { # +0.023 special chance, +0.02 special damage per revive used
                "cost": 3,
                "max": 5,
            },
            "gift_of_medusa": { # 0.05 hunter hp as enemy -regen
                "cost": 3,
                "max": 5,
            },
            "deal_with_death": { # x0.02 power, +0.016 dr per revive used
                "cost": 5,
                "max": 3,
            },
            "dance_of_dashes": { # 0.15 chance to gain trickster charge on evade
                "cost": 3,
                "max": 4,
            },
        },
        "inscryptions": {
            "i31": { # +0.006 ozzy effect chance
                "cost": 1,
                "max": 10,
            },
            "i32": { # x1.5 ozzy loot
                "cost": 1,
                "max": 8,
            },
            "i33": { # x1.75 ozzy xp
                "cost": 1,
                "max": 6,
            },
            "i36": { # -0.03 ozzy speed
                "cost": 1,
                "max": 5,
            },
            "i37": { # +0.0111 ozzy dr
                "cost": 1,
                "max": 7,
            },
            "i40": { # +0.005 ozzy multistrike chance
                "cost": 1,
                "max": 10,
            },
        },
    }

    def __init__(self, config_dict: Dict):
        super(Ozzy, self).__init__(name='Ozzy')
        self.__create__(config_dict)
        self.trickster_charges: int = 0
        self.crippling_on_target: int = 0
        self.empowered_regen: int = 0
        self.attack_queue: List = []

        # statistics
        # offence
        self.total_multistrikes: int = 0
        self.total_ms_extra_damage: float = 0
        self.total_decay_damage: float = 0
        self.total_cripple_extra_damage: float = 0

        # sustain
        self.total_potion: float = 0

        # defence
        self.total_trickster_evades: int = 0

        # effects
        self.total_echo: int = 0

    def __create__(self, config_dict: Dict) -> None:
        """Create an Ozzy instance from a build config dict. Computes all final stats from stat growth formulae and
        additional power sources.

        Args:
            config_dict (dict): Build config dictionary object.
        """
        self.load_build(config_dict)
        # hp
        self.max_hp = (
            (
                16
                + (self.base_stats["hp"] * (2 + 0.03 * (self.base_stats["hp"] // 5)))
            )
            * (1 + (self.attributes["living_off_the_land"] * 0.02))
            * (1 + (self.relics["disk_of_dawn"] * 0.02))
        )
        self.hp = self.max_hp
        # power
        self.power = (
            (
                2
                + (self.base_stats["power"] * (0.3 + 0.01 * (self.base_stats["power"] // 10)))
            )
            * (1 + (self.attributes["exo_piercers"] * 0.012))
            * (1 + (self.relics["bee-gone_companion_drone"] * 0.02))
            * (1 + (0.03 * self.gems["innovation_node_#3"]))
        )
        # regen
        self.regen = (
            (
                0.1
                + (self.base_stats["regen"] * (0.05 + 0.01 * (self.base_stats["regen"] // 30)))
            )
            * (1 + (self.attributes["living_off_the_land"] * 0.02))
        )
        self.damage_reduction = (
            0
            + (self.base_stats["damage_reduction"] * 0.0035)
            + (self.attributes["wings_of_ibu"] * 0.026)
            + (self.inscryptions["i37"] * 0.0111)
        )
        # evade_chance
        self.evade_chance = (
            0.05
            + (self.base_stats["evade_chance"] * 0.0062)
            + (self.attributes["wings_of_ibu"] * 0.005)
        )
        # effect_chance
        self.effect_chance = (
            0.04
            + (self.base_stats["effect_chance"] * 0.0035)
            + (self.attributes["extermination_protocol"] * 0.028)
            + (self.inscryptions["i31"] * 0.006)
        )
        # special_chance
        self.special_chance = (
            (
                0.05
                + (self.base_stats["special_chance"] * 0.0038)
                + (self.inscryptions["i40"] * 0.005)
                + (0.03 * self.gems["innovation_node_#3"])
            )
        )
        # special_damage
        self.special_damage = (
            0.25
            + (self.base_stats["special_damage"] * 0.01)
        )
        # speed
        self.speed = (
            4
            - (self.base_stats["speed"] * 0.02)
            - (self.talents["thousand_needles"] * 0.06)
            - (self.inscryptions["i36"] * 0.03)
        )
        # lifesteal
        self.lifesteal = (self.attributes["shimmering_scorpion"] * 0.033)

    @staticmethod
    def load_dummy() -> dict:
        """Create a dummy build dictionary with empty stats to compare against loaded configs.

        Returns:
            dict: The dummy build dict.
        """
        return {
            "meta": {
                "hunter": "Ozzy",
                "level": 0
            },
            "stats": {
                "hp": 0,
                "power": 0,
                "regen": 0,
                "damage_reduction": 0,
                "evade_chance": 0,
                "effect_chance": 0,
                "special_chance": 0,
                "special_damage": 0,
                "speed": 0,
            },
            "talents": {
                "death_is_my_companion": 0,
                "tricksters_boon": 0,
                "unfair_advantage": 0,
                "thousand_needles": 0,
                "omen_of_decay": 0,
                "call_me_lucky_loot": 0,
                "crippling_shots": 0,
                "echo_bullets": 0
            },
            "attributes": {
                "living_off_the_land": 0,
                "exo_piercers": 0,
                "wings_of_ibu": 0,
                "timeless_mastery": 0,
                "shimmering_scorpion": 0,
                "extermination_protocol": 0,
                "dance_of_dashes": 0,
                "gift_of_medusa": 0,
                "vectid_elixir": 0,
                "soul_of_snek": 0,
                "cycle_of_death": 0,
                "deal_with_death": 0,
            },
            "inscryptions": {
                "i31": 0, # 0.006 ozzy effect chance
                "i32": 0, # 1.5 ozzy loot
                "i33": 0, # 1.75 ozzy xp
                "i36": 0, # 0.03 ozzy speed
                "i37": 0, # 0.0111 ozzy dr
                "i40": 0, # 0.005 ozzy multistrike chance
            },
            "mods": {
            },
            "relics": {
                "disk_of_dawn": 0,
                "bee-gone_companion_drone": 0,
            },
            "gems": {
                "attraction_gem": 0,
                "attraction_catch-up": 0,
                "attraction_node_#3": 0,
                "innovation_node_#3" : 0,
            },
        }

    def attack(self, target) -> None:
        """Attack the enemy unit.

        Args:
            target (Enemy): The enemy to attack.
        """
        # method handles all attacks: normal and triggered
        if not self.attack_queue: # normal attacks
            if random.random() < (self.effect_chance / 2) and self.talents["tricksters_boon"]:
                # Talent: Trickster's Boon
                self.trickster_charges += 1
                self.total_effect_procs += 1
                logging.debug(f"[{self.name:>{hunter_name_spacing}}][@{self.sim.elapsed_time:>5}]:\tTRICKSTER")
            if random.random() < self.special_chance:
                # Stat: Multi-Strike
                self.attack_queue.append('(MS)')
                hpush(self.sim.queue, (0, 1, 'hunter_special'))
            if random.random() < self.effect_chance and self.talents["thousand_needles"]:
                # Talent: Thousand Needles, will call Hunter.apply_stun(). Only Ozzy's main attack can stun.
                hpush(self.sim.queue, (0, 0, 'stun'))
                self.total_effect_procs += 1
            if random.random() < (self.effect_chance / 2) and self.talents["echo_bullets"]:
                # Talent: Echo Bullets
                self.attack_queue.append('(ECHO)')
                hpush(self.sim.queue, (0, 2, 'hunter_special'))
            damage = self.power
            self.total_attacks += 1
            atk_type = ''
        else: # triggered attacks
            atk_type = self.attack_queue.pop(0)
            match atk_type:
                case '(MS)':
                    damage = self.power * self.special_damage
                    self.total_ms_extra_damage += damage
                    self.total_multistrikes += 1
                case '(ECHO)':
                    if random.random() < self.special_chance:
                        # Stat: Multi-Strike
                        self.attack_queue.append('(ECHO-MS)')
                        hpush(self.sim.queue, (0, 3, 'hunter_special'))
                    damage = self.power * (self.talents["echo_bullets"] * 0.05)
                    self.total_echo += 1
                case '(ECHO-MS)':
                    damage = self.power * self.special_damage
                    self.total_ms_extra_damage += damage
                    self.total_multistrikes += 1
                case _:
                    raise ValueError(f'Unknown attack type: {atk_type}')
        # omen of decay
        omen_effect = 0.1 if self.current_stage % 100 == 0 and self.current_stage > 0 else 1
        omen_damage = target.hp * (self.talents["omen_of_decay"] * 0.008) * omen_effect
        omen_final = damage + omen_damage
        # crippling shots
        cripple_damage = omen_final * (1 + (self.crippling_on_target * 0.03))
        self.crippling_on_target = 0
        logging.debug(f"[{self.name:>{hunter_name_spacing}}][@{self.sim.elapsed_time:>5}]:\tATTACK\t{cripple_damage:>6.2f} {atk_type} OMEN: {omen_damage:>6.2f}")
        super(Ozzy, self).attack(target, cripple_damage)
        self.total_decay_damage += omen_damage
        self.total_cripple_extra_damage += (cripple_damage - omen_final)
        if atk_type == '':
            self.total_damage += cripple_damage

        # on_attack() effects
        # crippling shots and omen of decay inflict _extra damage_ that does not count towards lifesteal
        self.heal_hp(damage * self.lifesteal, 'steal')
        if random.random() < self.effect_chance and (cs := self.talents["crippling_shots"]):
            # Talent: Crippling Shots, can proc on any attack
            self.crippling_on_target += cs
            logging.debug(f"[{self.name:>{hunter_name_spacing}}][@{self.sim.elapsed_time:>5}]:\tCRIPPLE\t+{cs}")
            self.total_effect_procs += 1
        if target.is_dead():
            self.on_kill()

    def receive_damage(self, _, damage: float, is_crit: bool) -> None:
        """Receive damage from an attack. Accounts for damage reduction, evade chance and trickster charges.

        Args:
            _ (Enemy): The unit that is attacking. Not used for Ozzy.
            damage (float): The amount of damage to receive.
            is_crit (bool): Whether the attack was a critical hit or not.
        """
        if self.trickster_charges:
            self.trickster_charges -= 1
            self.total_trickster_evades += 1
            logging.debug(f'[{self.name:>{hunter_name_spacing}}][@{self.sim.elapsed_time:>5}]:\tEVADE (TRICKSTER)')
        else:
            _ = super(Ozzy, self).receive_damage(damage)
            if is_crit:
                if (dod := self.attributes["dance_of_dashes"]) and random.random() < dod * 0.15:
                    # Talent: Dance of Dashes
                    self.trickster_charges += 1
                    self.total_effect_procs += 1

    def regen_hp(self) -> None:
        """Regenerates hp according to the regen stat, modified by the `Vectid Elixir` attribute.
        """
        regen_value = self.regen
        if self.empowered_regen > 0:
            regen_value *= 1 + (self.attributes["vectid_elixir"] * 0.15)
            self.empowered_regen -= 1
        self.heal_hp(regen_value, 'regen')

    ### SPECIALS
    def on_kill(self) -> None:
        """Actions to take when the hunter kills an enemy. Loot is handled by the parent class.
        """
        super(Ozzy, self).on_kill()
        if random.random() < self.effect_chance and (ua := self.talents["unfair_advantage"]):
            # Talent: Unfair Advantage
            potion_healing = self.max_hp * (ua * 0.02)
            self.heal_hp(potion_healing, "potion")
            self.total_potion += potion_healing
            self.total_effect_procs += 1
            # Attribute: Vectid Elixir
            self.empowered_regen += 5

    def apply_stun(self, enemy, is_boss: bool) -> None:
        """Apply a stun to an enemy.

        Args:
            enemy (Enemy): The enemy to stun.
        """
        stun_effect = 0.5 if is_boss else 1
        stun_duration = self.talents['thousand_needles'] * 0.05 * stun_effect
        enemy.stun(stun_duration)
        self.total_stuntime_inflicted += stun_duration

    def apply_snek(self, enemy) -> None:
        """Apply the Soul of Snek effect to an enemy.

        Args:
            enemy (Enemy): The enemy to apply the effect to.
        """
        ood_effect = self.attributes["soul_of_snek"] * 0.088
        enemy.regen = enemy.regen * (1 - ood_effect)

    def apply_medusa(self, enemy) -> None:
        """Apply the Gift of Medusa effect to an enemy.

        Args:
            enemy (Enemy): The enemy to apply the effect to.
        """
        enemy.regen -= self.regen * self.attributes["gift_of_medusa"] * 0.05

    @property
    def power(self) -> float:
        """Getter for the power attribute. Accounts for the Deal with Death effect.

        Returns:
            float: The power of the hunter.
        """
        return (
            self._power
            * (1 + (self.attributes["deal_with_death"] * 0.02 * self.times_revived))
            * ((1.08 ** self.gems["attraction_catch-up"]) ** (1 + (self.gems["attraction_gem"] * 0.1) - 0.1) if self.catching_up else 1)
        )

    @power.setter
    def power(self, value: float) -> None:
        self._power = value
    
    @property
    def damage_reduction(self) -> float:
        """Getter for the damage_reduction attribute. Accounts for the Deal with Death effect.

        Returns:
            float: The damage_reduction of the hunter.
        """
        return self._damage_reduction + (self.attributes["deal_with_death"] * 0.016 * self.times_revived)

    @damage_reduction.setter
    def damage_reduction(self, value: float) -> None:
        self._damage_reduction = value

    @property
    def special_chance(self) -> float:
        """Getter for the special_chance attribute. Accounts for the Cycle of Death effect.

        Returns:
            float: The special_chance of the hunter.
        """
        return self._special_chance + (self.times_revived * self.attributes["cycle_of_death"] * 0.023)

    @special_chance.setter
    def special_chance(self, value: float) -> None:
        self._special_chance = value

    @property
    def special_damage(self) -> float:
        """Getter for the special_damage attribute. Accounts for the Cycle of Death effect.

        Returns:
            float: The special_chance of the hunter.
        """
        return self._special_damage + (self.times_revived * self.attributes["cycle_of_death"] * 0.02)

    @special_damage.setter
    def special_damage(self, value: float) -> None:
        self._special_damage = value

    @property
    def speed(self) -> float:
        """Getter for the speed attribute. Accounts for the Attraction gem catch-up effect.

        Returns:
            float: The speed of the hunter.
        """
        return (
            self._speed
            / ((1.08 ** self.gems["attraction_catch-up"]) ** (1 + (self.gems["attraction_gem"] * 0.1) - 0.1) if self.catching_up else 1)
        )

    @speed.setter
    def speed(self, value: float) -> None:
        self._speed = value

    def get_results(self) -> List:
        """Fetch the hunter results for end-of-run statistics.

        Returns:
            List: List of all collected stats.
        """
        return super(Ozzy, self).get_results() | {
            'multistrikes': self.total_multistrikes,
            'extra_damage_from_ms': self.total_ms_extra_damage,
            'unfair_advantage_healing': self.total_potion,
            'trickster_evades': self.total_trickster_evades,
            'decay_damage': self.total_decay_damage,
            'extra_damage_from_crippling_strikes': self.total_cripple_extra_damage,
            'echo_bullets': self.total_echo,
        }


if __name__ == "__main__":
    h = Hunter.from_file('builds/current_ozzy.yaml')
    h.show_build()
    h.complete_stage(150)
    print(h)
