import yaml
from units import *


class Hunter(Defence_Unit):
    """Base class for hunter units. Extends enemy classes to add effect chance. Only used for inheritance.
    """
    def __init__(self, effect_chance: float, **kwargs):
        super(Hunter, self).__init__(**kwargs)
        self.effect_chance: float = effect_chance
        self.current_stage = 0
        self.revive_log = []

    def apply_stun(self, target: Unit) -> float:
        """Apply a stun effect to a target unit.

        Args:
            target (Unit): The unit to stun.

        Raises:
            ValueError: If no stun talent is found.

        Returns:
            float: The duration of the stun.
        """
        if "impeccable_impacts" in self.talents:
            stun_duration = self.talents["impeccable_impacts"] * 0.1
        elif "thousand_needles" in self.talents:
            stun_duration = self.talents["thousand_needles"] * 0.05
        else:
            raise ValueError("No stun talent found")
        if stun_duration > 0:
            stun_duration = stun_duration * (0.5 if isinstance(target, Boss) else 1)
            target.stun(stun_duration)
            logging.debug(f'[{target.name:>{unit_name_spacing}}]:\tSTUNNED\t{stun_duration:>6.2f} sec')
        return stun_duration

    def get_results(self) -> List:
        """Get the results of the simulation: Total damage, kills, crits, regen and final hp.

        Returns:
            List: List of all collected stats.
        """
        return {
            'total_damage': self.total_damage,
            'total_kills': self.total_kills,
            'total_crits': self.total_crits,
            'total_regen': self.total_regen,
            'final_hp': self.hp,
            'survived': not self.is_dead(),
            'elapsed_time': self.elapsed_time,
            'final_stage': self.total_kills // 10,
        }

class Ozzy(Hunter):
    pass

class Borge(Hunter):
    def __init__(self, file_path: str):
        self.load_full(file_path)
        super(Borge, self).__init__(name="Borge", **self.base_stats)
        self.hp = self.max_hp

    def get_speed(self) -> float:
        """Returns the speed of the unit, taking into account Fires of War.

        Returns:
            float: Current attack speed.
        """
        return self.speed

    def attack(self, target: Unit) -> dict:
        """Attack a target unit.

        Args:
            target (Unit): The unit to attack.

        Returns:
            dict: A dictionary of events the attack caused.
        """
        events = dict()
        damage = super(Borge, self).attack(target)
        events["damage"] = damage
        if self.lifesteal > 0 and self.missing_hp > 0:
            self.heal_hp(damage * self.lifesteal, "steal")
        if random.random() < self.effect_chance:
            events["stun"] = True
        if random.random() < self.special_chance and self.talents["life_of_the_hunt"] and self.missing_hp > 0:
            self.heal_hp(damage * self.talents["life_of_the_hunt"] * 0.06, "[LOTH]")
        return events


    def receive_damage(self, attacker: Unit, damage: float, is_crit) -> None:
        """Receive damage from an attack. Accounts for damage reduction, evade chance and reflected damage.

        Args:
            attacker (Unit): The unit that is attacking. Used to apply damage reflection.
            damage (float): The amount of damage to receive.
            is_crit (bool): Whether the attack was a critical hit or not.
        """
        if is_crit:
            reduced_crit_damage = damage * (1 - self.attributes["weakspot_analysis"] * 0.11)
            final_damage = super(Borge, self).receive_damage(attacker, reduced_crit_damage, is_crit)
        else:
            final_damage = super(Borge, self).receive_damage(attacker, damage, is_crit)
        if self.attributes["helltouch_barrier"] > 0 and final_damage > 0 and not self.is_dead():
            # reflected damage from helltouch barrier
            reflected_damage = final_damage * self.attributes["helltouch_barrier"] * 0.08 * (0.1 if isinstance(attacker, Boss) else 1)
            attacker.receive_damage(None, reflected_damage, False)


    def regen_hp(self) -> None:
        """Regenerates hp according to the regen stat, modified by the `Lifedrain Inhalers` attribute.
        """
        regen_value = self.regen + ((self.attributes["lifedrain_inhalers"] * 0.0008) * self.missing_hp)
        self.heal_hp(regen_value, 'regen')

    def apply_pog(self, enemy: Unit) -> None:
        """Apply the Presence of a God effect to an enemy.

        Args:
            enemy (Unit): The enemy to apply the effect to.
        """
        if self.talents["presence_of_god"] > 0:
            pog_effect = (self.talents["presence_of_god"] * 0.04) * (0.5 if isinstance(enemy, Boss) else 1)
            enemy.hp = enemy.max_hp * (1 - pog_effect)
            logging.debug(f'[{self.name:>{unit_name_spacing}}]:\t[PRESENCE OF A GOD] {pog_effect*100:.0f}%')
            logging.debug(enemy)


    def apply_trample(self, enemies: List[Enemy]) -> int:
        """Apply the Trample effect to a list of enemies.

        Args:
            enemies (List[Enemy]): The list of enemies to apply the effect to. Should not be applied to bosses.

        Returns:
            int: The number of enemies killed by the trample effect.
        """
        if not enemies:
            return 0
        if self.mods["trample"] == 0:
            return 0 # no trample mod

        trample_power = self.power // enemies[0].max_hp
        trample_kills = 0
        if trample_power > 1:
            for enemy in enemies:
                if not enemy.is_dead() and trample_kills < trample_power:
                    enemy.hp = 0
                    trample_kills += 1
        return trample_kills

    def check_death(self) -> None:
        """Check if the unit is dead and log it if it is. If the unit has the Death is my Companion talent, it will revive with a percentage of its max hp instead.
        """
        if self.is_dead():
            if self.talents["death_is_my_companion"] > 0:
                self.talents["death_is_my_companion"] -= 1
                self.hp = self.max_hp * 0.8
                self.revive_log.append((self.current_stage, self.total_kills))
                logging.debug(f'[{self.name:>{unit_name_spacing}}]:\tREVIVED, {self.talents["death_is_my_companion"]} left')
            else:
                logging.debug(f'[{self.name:>{unit_name_spacing}}]:\tDIED')

    def load_full(self, file_path: str) -> None:
        """Load a full build loadout from a yaml file.

        Args:
            file_path (str): The path to the yaml config file.
        """
        with open(file_path, 'r') as f:
            cfg = yaml.safe_load(f)
        if not self.validate_config(cfg):
            raise ValueError("Invalid config file")
        self.load_base_stats(cfg)
        self.load_build(cfg)

    def load_base_stats(self, cfg: dict) -> None:
        """Load the base stats from a yaml config file.

        Args:
            cfg (dict): The yaml config file.
        """
        # self.base_stats = self.calc_base_stats(cfg["meta"]["hunter"], **cfg["stats"])
        self.base_stats = cfg["stats"]

    def load_build(self, cfg: dict) -> None:
        """Load only the build (talents, attributes, mods, inscryptions) from a yaml config file.

        Args:
            cfg (dict): The yaml config file.
        """
        self.talents = cfg["talents"]
        self.attributes = cfg["attributes"]
        self.mods = cfg["mods"]
        self.inscryptions = cfg["inscryptions"]

    def calc_base_stats(self, hunter_type: str, hp: int, power: int, regen: int, damage_reduction: int, evade_chance: int, effect_chance: int, special_chance: int, special_damage: int, speed: int) -> dict:
        """Calculate the base stats of a hunter.

        Args:
            hunter_type (str): The type of hunter to calculate the base stats for.
            hp (int): Level of the hp upgrade.
            power (int): Level of the power upgrade.
            regen (int): Level of the regen upgrade.
            damage_reduction (int): Level of the damage reduction upgrade.
            evade_chance (int): Level of the evade chance upgrade.
            effect_chance (int): Level of the effect chance upgrade.
            special_chance (int): Level of the special chance upgrade.
            special_damage (int): Level of the special damage upgrade.
            speed (int): Level of the speed upgrade.

        Returns:
            dict: The base stats of the hunter.
        """
        if hunter_type == 'Ozzy':
            return {
                "hp": round(16 + hp * (2 + 0.03 * (hp // 5))),
                "power": round(2 + power * (0.3 + 0.01 * (power // 10)), 2),
                "regen": round(0.1 + regen * (0.05 + 0.01 * (regen // 30)), 2),
                "damage_reduction": round(damage_reduction * 0.0035, 4),
                "evade_chance": round(0.05 + evade_chance * 0.0062, 4),
                "effect_chance": round(0.04 + effect_chance * 0.0035, 4),
                "special_chance": round(0.05 + 0.0038 * special_chance, 4),
                "special_damage": round(0.25 + 0.01 * special_damage, 4),
                "speed": 4 - 0.02 * speed,
            }
        elif hunter_type == 'Borge':
            return {
                "hp": hp * (2.53 + 0.01 * (hp // 5)),
                "power": power * (0.5 + 0.01 * (power // 10)) * (1 + 0.002) + (0 * 1) + (0 * 2),
                "regen": regen * (0.03 + 0.01 * (regen // 30)), #
                "damage_reduction": damage_reduction * 0.0144, #
                "evade_chance": evade_chance * 0.0034, #
                "effect_chance": effect_chance * 0.005, #
                "special_chance": 0.0018 * special_chance, #
                "special_damage": 0.01 * special_damage, #
                "speed": 0.03 * speed, #
            }
        else:
            raise ValueError("Invalid hunter type")

    def validate_config(self, cfg: dict) -> bool:
        """Validate a build config dict against a perfect dummy build to see if they have identical keys in themselves and all value entries.

        Args:
            cfg (dict): The build config

        Returns:
            bool: Whether the configs contain identical keys.
        """
        return cfg.keys() == self.load_dummy().keys() and all(cfg[k].keys() == self.load_dummy()[k].keys() for k in cfg.keys())

    def load_dummy(self) -> dict:
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
                "lifedrain_inhalers": 0,
                "spartan_lineage": 0,
                "explosive_punches": 0,
                "timeless_mastery": 0,
                "book_of_baal": 0,
                "superior_sensors": 0,
                "atlas_protocol": 0,
                "weakspot_analysis": 0,
                "born_for_battle": 0
            },
            "inscryptions": {
                "i3": 0,
                "i4": 0,
                "i11": 0,
                "i13": 0,
                "i14": 0,
                "i23": 0,
                "i24": 0,
                "i27": 0,
                "i31": 0,
                "i32": 0,
                "i33": 0,
                "i40": 0,
                "i44": 0,
            },
            "mods": {
                "trample": False
            },
            "relics": {
                "disk_of_dawn": 0
            }
        }

    @property
    def max_hp(self) -> float:
        return round(
            (
                43
                + (self.base_stats["hp"] * (2.50 + 0.01 * (self.base_stats["hp"] // 5)))
                + (self.inscryptions["i3"] * 6)
                + (self.inscryptions["i27"] * 24)
            )
            * (1 + (self.attributes["soul_of_ares"] * 0.01))
        , 2)
        # borge hp before relic: 871, after relic: 888
    

    @max_hp.setter
    def max_hp(self, value: float) -> None:
        self._max_hp = value

    @property
    def hp(self) -> float:
        return self._hp

    @hp.setter
    def hp(self, value: float) -> None:
        self._hp = value

    @property
    def power(self) -> float:
        return (
            (
                3
                + (self.base_stats["power"] * (0.5 + 0.01 * (self.base_stats["power"] // 10)))
                + (self.inscryptions["i13"] * 1)
                + (self.talents["impeccable_impacts"] * 2)
            )
            * (1 + (self.attributes["soul_of_ares"] * 0.002))
        )

    @power.setter
    def power(self, value: float) -> None:
        self._power = value

    @property
    def regen(self) -> float:
        return (
            (
                0.02
                + (self.base_stats["regen"] * (0.03 + 0.01 * (self.base_stats["regen"] // 30)))
                + (self.attributes["essence_of_ylith"] * 0.04)
            )
            * (1 + (self.attributes["essence_of_ylith"] * 0.009))
        )

    @regen.setter
    def regen(self, value: float) -> None:
        self._regen = value

    @property
    def damage_reduction(self) -> float:
        return (
            0
            + (self.base_stats["damage_reduction"] * 0.0144)
            + (self.attributes["spartan_lineage"] * 0.015)
            + (self.inscryptions["i24"] * 0.004)
        )

    @damage_reduction.setter
    def damage_reduction(self, value: float) -> None:
        self._damage_reduction = value

    @property
    def evade_chance(self) -> float:
        return (
            0.01
            + (self.base_stats["evade_chance"] * 0.0034)
            + (self.attributes["superior_sensors"] * 0.016)
        )

    @evade_chance.setter
    def evade_chance(self, value: float) -> None:
        self._evade_chance = value

    @property
    def effect_chance(self) -> float:
        return (
            0.04
            + (self.base_stats["effect_chance"] * 0.005)
            + (self.attributes["superior_sensors"] * 0.012)
            + (self.inscryptions["i11"] * 0.02)
        )

    @effect_chance.setter
    def effect_chance(self, value: float) -> None:
        self._effect_chance = value

    @property
    def special_chance(self) -> float:
        return (
            0.05
            + (self.base_stats["special_chance"] * 0.0018)
            + (self.attributes["explosive_punches"] * 0.044)
            + (self.inscryptions["i4"] * 0.0065)
        )

    @special_chance.setter
    def special_chance(self, value: float) -> None:
        self._special_chance = value

    @property
    def special_damage(self) -> float:
        return (
            1.30
            + (self.base_stats["special_damage"] * 0.01)
            + (self.attributes["explosive_punches"] * 0.08)
        )

    @special_damage.setter
    def special_damage(self, value: float) -> None:
        self._special_damage = value

    @property
    def speed(self) -> float:
        return (
            5
            - (self.base_stats["speed"] * 0.03)
            - (self.inscryptions["i23"] * 0.04)
        )

    @speed.setter
    def speed(self, value: float) -> None:
        self._speed = value

    @property
    def lifesteal(self) -> float:
        return self.attributes["book_of_baal"] * 0.0111

    @lifesteal.setter
    def lifesteal(self, value: float) -> None:
        self._lifesteal = value