import logging
import random
from heapq import heappush as hpush
from typing import List

import yaml
from util.exceptions import BuildConfigError

hunter_name_spacing: int = 7

# TODO: maybe find a better way to trample()
# TODO: validate vectid elixir
# TODO: Ozzy: move @property code to on_death() to speed things up?
# TODO: Borge: move @property code as well?

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

        # loot
        self.total_loot: float = 0

    def get_results(self) -> List:
        """Fetch the hunter results for end-of-run statistics.

        Returns:
            List: List of all collected stats.
        """
        return {
            'final_stage': self.current_stage,
            'total_kills': self.total_kills,
            'revive_log': self.revive_log,
            'enrage_log': self.enrage_log,
            'total_attacks': self.total_attacks,
            'total_damage': self.total_damage,
            'total_taken': self.total_taken,
            'total_regen': self.total_regen,
            'total_attacks_suffered': self.total_attacks_suffered,
            'total_lifesteal': self.total_lifesteal,
            'total_evades': self.total_evades,
            'total_mitigated': self.total_mitigated,
            'total_effect_procs': self.total_effect_procs,
            'total_loot': self.total_loot,
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

    def load_build(self, config_path: str) -> None:
        """Load a build config from a yaml file, validate it and assign the stats to the hunter's internal dictionaries.

        Args:
            config_path (str): The path to the config file.

        Raises:
            ValueError: If the config file is invalid.
        """
        with open(config_path, 'r') as f:
            cfg = yaml.safe_load(f)
        if not (invalid_keys := self.validate_config(cfg)) == set():
            raise BuildConfigError(invalid_keys)
        self.base_stats = cfg["stats"]
        self.talents = cfg["talents"]
        self.attributes = cfg["attributes"]
        self.mods = cfg["mods"]
        self.inscryptions = cfg["inscryptions"]
        self.relics = cfg["relics"]

    def validate_config(self, cfg: dict) -> bool:
        """Validate a build config dict against a perfect dummy build to see if they have identical keys in themselves and all value entries.

        Args:
            cfg (dict): The build config

        Returns:
            bool: Whether the configs contain identical keys.
        """
        return (set(cfg.keys()) ^ set(self.load_dummy().keys())) | set().union(*cfg.values()) ^ set().union(*self.load_dummy().values())

    def attack(self, target, damage: float) -> None:
        """Attack the enemy unit.

        Args:
            target (Enemy): The enemy to attack.
            damage (float): The amount of damage to deal.
        """
        target.receive_damage(damage)
        self.total_damage += damage
        self.total_attacks += 1

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
        if random.random() < self.effect_chance and (LL := self.talents["call_me_lucky_loot"]):
            # Talent: Call Me Lucky Loot
            loot *= 1 + (self.talents["call_me_lucky_loot"] * 0.2)
            self.total_effect_procs += 1
        self.total_loot += loot

    def compute_loot(self) -> float:
        """Compute the amount of loot gained from a kill. Affected by stage loot bonus, talents and attributes.

        Returns:
            float: The amount of loot gained.
        """
        stage_mult = (1.05 ** (self.current_stage+1)) * (self.current_stage // 100 * 5.0)
        if isinstance(self, Borge):
            base_loot = 1.0 if self.current_stage != 100 else (700 + 500 + 60 + 50)
            timeless_mastery = 1 + self.attributes["timeless_mastery"] * 0.14
        elif isinstance(self, Ozzy):
            base_loot = 1.0 if self.current_stage != 100 else (400 + 300 + 60 + 50)
            timeless_mastery = 1 + (self.attributes["timeless_mastery"] * 0.16)
        return base_loot * stage_mult + timeless_mastery

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

    def __str__(self) -> str:
        """Prints the stats of this Hunter's instance.

        Returns:
            str: The stats as a formatted string.
        """
        return f'[{self.name:>{hunter_name_spacing}}]:\t[HP:{(str(round(self.hp, 2)) + "/" + str(round(self.max_hp, 2))):>16}] [AP:{self.power:>7.2f}] [Regen:{self.regen:>6.2f}] [DR: {self.damage_reduction:>6.4f}] [Evasion: {self.evade_chance:>6.4f}] [Effect: {self.effect_chance:>6.4f}] [SpC: {self.special_chance:>6.4f}] [SpD: {self.special_damage:>5.2f}] [Speed:{self.speed:>5.2f}] [LS: {self.lifesteal:>4.3f}]'


class Borge(Hunter):
    ### SETUP
    def __init__(self, config_path: str):
        super(Borge, self).__init__(name='Borge')
        self.__create__(config_path)

        # statistics
        # offence
        self.total_crits: int = 0
        self.total_extra_from_crits: float = 0
        self.total_helltouch: float = 0

        # sustain
        self.total_loth: float = 0
        self.total_potion: float = 0
        self.total_inhaler: float = 0

    def __create__(self, config_path: str) -> None:
        """Create a Borge instance from a build config file. Computes all final stats from stat growth formulae and additional
        power sources.

        Args:
            config_path (str): The path to the build config file.
        """
        self.load_build(config_path)
        # hp
        self.max_hp = (
            (
                43
                + (self.base_stats["hp"] * (2.50 + 0.01 * (self.base_stats["hp"] // 5)))
                + (self.inscryptions["i3"] * 6)
                + (self.inscryptions["i27"] * 24)
            )
            * (1 + (self.attributes["soul_of_ares"] * 0.01))
            * (1 + (self.relics["disk_of_dawn"] * 0.02))
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
        )
        # regen
        self.regen = (
            (
                0.02
                + (self.base_stats["regen"] * (0.03 + 0.01 * (self.base_stats["regen"] // 30)))
                + (self.attributes["essence_of_ylith"] * 0.04)
            )
            * (1 + (self.attributes["essence_of_ylith"] * 0.009))
        )
        # damage_reduction
        self.damage_reduction = (
            0
            + (self.base_stats["damage_reduction"] * 0.0144)
            + (self.attributes["spartan_lineage"] * 0.015)
            + (self.inscryptions["i24"] * 0.004)
        )
        # evade_chance
        self.evade_chance = (
            0.01
            + (self.base_stats["evade_chance"] * 0.0034)
            + (self.attributes["superior_sensors"] * 0.016)
        )
        # effect_chance
        self.effect_chance = (
            0.04
            + (self.base_stats["effect_chance"] * 0.005)
            + (self.attributes["superior_sensors"] * 0.012)
            + (self.inscryptions["i11"] * 0.02)
        )
        # special_chance
        self.special_chance = (
            0.05
            + (self.base_stats["special_chance"] * 0.0018)
            + (self.attributes["explosive_punches"] * 0.044)
            + (self.inscryptions["i4"] * 0.0065)
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
                "hunter": "_",
                "build_only": False,
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
            },
            "mods": {
                "trample": False
            },
            "relics": {
                "disk_of_dawn": 0
            }
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
        if target.is_dead():
            self.on_kill()

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
        # 100 * (1 + 0.5 (1 + 1 * 0.001))
        # return self._power * ((1 + self.get_missing_pct) * (1 + self.attributes["born_for_battle"] * 0.001))
        return self._power * (1 + (self.missing_hp_pct * self.attributes["born_for_battle"] * 0.001))

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
            'total_crits': self.total_crits,
            'total_extra_from_crits': self.total_extra_from_crits,
            'total_helltouch': self.total_helltouch,
            'total_loth': self.total_loth,
            'total_potion': self.total_potion,
        }

class Ozzy(Hunter):
    ### SETUP
    def __init__(self, config_path: str):
        super(Ozzy, self).__init__(name='Ozzy')
        self.__create__(config_path)
        self.trickster_charges: int = 0
        self.crippling_on_target: int = 0
        self.empowered_regen: int = 0
        self.attack_queue: List = []

        # statistics
        # offence
        self.total_multistrikes: int = 0
        self.total_ms_extra_damage: float = 0

        # sustain
        self.total_potion: float = 0

        # defence
        self.total_trickster_evades: int = 0

    def __create__(self, config_path: str) -> None:
        """Create an Ozzy instance from a build config file. Computes all final stats from stat growth formulae and
        additional power sources.

        Args:
            config_path (str): The path to the build config file.
        """
        self.load_build(config_path)
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
            0.05
            + (self.base_stats["special_chance"] * 0.0038)
            + (self.inscryptions["i40"] * 0.005)
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
                "hunter": "_",
                "build_only": False,
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
                "disk_of_dawn": 0
            }
        }

    def attack(self, target) -> None:
        """Attack the enemy unit.

        Args:
            target (Enemy): The enemy to attack.
        """
        # method handles all attacks: normal and triggered
        if not self.attack_queue: # normal attacks
            if random.random() < self.special_chance:
                # Stat: Multi-Strike
                self.attack_queue.append('(MS)')
                self.total_multistrikes += 1
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
            atk_type = ''
        else: # triggered attacks
            atk_type = self.attack_queue.pop(0)
            match atk_type:
                case '(MS)':
                    damage = self.power * self.special_damage
                    self.total_ms_extra_damage += damage
                case '(ECHO)':
                    if random.random() < self.special_chance:
                        # Stat: Multi-Strike
                        self.attack_queue.append('(ECHO-MS)')
                        self.total_multistrikes += 1
                        hpush(self.sim.queue, (0, 3, 'hunter_special'))
                    damage = self.power * (self.talents["echo_bullets"] * 0.05)
                case '(ECHO-MS)':
                    damage = self.power * self.special_damage
                    self.total_ms_extra_damage += damage
                case _:
                    raise ValueError(f'Unknown attack type: {atk_type}')
        # omen of decay
        omen_effect = 0.1 if self.current_stage % 100 == 0 and self.current_stage > 0 else 1
        omen_damage = target.hp * (self.talents["omen_of_decay"] * 0.008) * omen_effect
        damage += omen_damage
        # crippling shots
        cripple_damage = damage * (1 + (self.crippling_on_target * 0.03))
        self.crippling_on_target = 0
        logging.debug(f"[{self.name:>{hunter_name_spacing}}][@{self.sim.elapsed_time:>5}]:\tATTACK\t{cripple_damage:>6.2f} {atk_type} OMEN: {omen_damage:>6.2f}")
        super(Ozzy, self).attack(target, cripple_damage)

        # on_attack() effects
        # crippling shots inflicts _extra damage_ that does not count towards lifesteal
        self.heal_hp(damage * self.lifesteal, 'steal')
        if random.random() < self.effect_chance and self.talents["tricksters_boon"]:
            # Talent: Trickster's Boon
            self.trickster_charges += 1
            self.total_effect_procs += 1
        if random.random() < self.effect_chance and (cs := self.talents["crippling_shots"]):
            # Talent: Crippling Shots
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
        return self._power * (1 + (self.attributes["deal_with_death"] * 0.02 * self.times_revived))

    @power.setter
    def power(self, value: float) -> None:
        self._power = value
    
    @property
    def damage_reduction(self) -> float:
        """Getter for the damage_reduction attribute. Accounts for the Deal with Death effect.

        Returns:
            float: The damage_reduction of the hunter.
        """
        return self._damage_reduction * (1 + (self.attributes["deal_with_death"] * 0.016 * self.times_revived))

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

    def get_results(self) -> List:
        """Fetch the hunter results for end-of-run statistics.

        Returns:
            List: List of all collected stats.
        """
        return super(Ozzy, self).get_results() | {
            'total_multistrikes': self.total_multistrikes,
            'total_ms_extra_damage': self.total_ms_extra_damage,
            'total_potion': self.total_potion,
            'total_trickster_evades': self.total_trickster_evades,
        }


if __name__ == "__main__":
    b = Borge('./builds/sanity_bfb_atlas.yaml')
    print(b)
    b.hp = 577
    print(b)
    print(b.missing_hp_pct)