from units import *
import yaml


class Hunter(Defence_Unit):
    """Base class for hunter units. Extends enemy classes to add lifesteal and effect chance. Only used for inheritance.
    """
    def __init__(self, effect_chance: float, **kwargs):
        super(Hunter, self).__init__(**kwargs)
        self.effect_chance: float = effect_chance
        self.lifesteal: float = 0
        self.current_stage = 0
        self.revive_log = []

    def apply_stun(self, target: Unit) -> None:
        if "impeccable_impacts" in self.talents:
            stun_duration = self.talents["impeccable_impacts"] * 0.1
        elif "thousand_needles" in self.talents:
            stun_duration = self.talents["thousand_needles"] * 0.05
        else:
            raise ValueError("No stun talent found")
        if stun_duration > 0:
            target.stun(stun_duration)
            logging.info(f'[{target.name:>{unit_name_spacing}}]:\tSTUNNED {stun_duration} sec')

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
        self.leftover_attackspeed: float = 0
        self.hp = self.max_hp

    def get_speed(self) -> float:
        """Returns the speed of the unit, taking into account the leftover attack speed from any previous attacks.

        Returns:
            float: Current attack speed.
        """
        if self.leftover_attackspeed > 0:
            leftover_windup = abs(self.leftover_attackspeed - self.speed)
            # if (self.speed - leftover_windup) < 0:
            return self.speed - leftover_windup
        return self.speed

    def attack(self, target: Unit) -> None:
        """Attack a target unit.

        Args:
            target (Unit): The unit to attack.
        """
        super(Borge, self).attack(target)
        self.leftover_attackspeed = 0 # reset leftover wind-up time after successful attack
        if random.random() < self.effect_chance:
            self.apply_stun(target)

    def receive_damage(self, attacker: Unit, damage: float) -> None:
        """Receive damage from an attack. Accounts for damage reduction, evade chance and reflected damage.

        Args:
            attacker (Unit): The unit that is attacking. Used to apply damage reflection.
            damage (float): The amount of damage to receive.
        """
        final_damage = super().receive_damage(attacker, damage)
        if self.attributes["helltouch_barrier"] > 0 and final_damage > 0 and not self.is_dead():
            # reflected damage from helltouch barrier
            attacker.receive_damage(None, final_damage * self.attributes["helltouch_barrier"] * 0.08)
            if attacker.is_dead():
                # attacker died from helltouck backlash while we were winding up an attack
                self.leftover_attackspeed = attacker.get_speed()
                logging.info(f'[{self.name:>{unit_name_spacing}}]:\tWIND-UP -{self.leftover_attackspeed - self.speed:.3f} sec')

    def regen_hp(self) -> None:
        """Regenerates hp according to the regen stat.
        """
        regen_value = self.regen + ((self.attributes["lifedrain_inhalers"] * 0.0008) * self.missing_hp)
        if (self.hp + regen_value) <= self.max_hp:
            self.hp += regen_value
            self.total_regen += regen_value
            logging.info(f'[{self.name:>{unit_name_spacing}}]:\tREGEN {round(regen_value, 2)} hp')
        else:
            logging.info(f'[{self.name:>{unit_name_spacing}}]:\tREGEN {round(self.max_hp - self.hp, 2)} hp (full)')
            self.total_regen += (self.max_hp - self.hp)
            self.hp = self.max_hp

    def apply_pog(self, enemy: Unit) -> None:
        """Apply the Presence of a God effect to an enemy.

        Args:
            enemy (Unit): The enemy to apply the effect to.
        """
        if self.talents["presence_of_god"] > 0:
            pog_effect = self.talents["presence_of_god"] * 0.04
            enemy.hp = enemy.max_hp * pog_effect
            logging.info(f'[{self.name:>{unit_name_spacing}}]:\tUSE {pog_effect*100:.0f}% [Presence of a God]')
            logging.info(enemy)


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
                logging.info(f'[{self.name:>{unit_name_spacing}}]:\tREVIVED. {self.talents["death_is_my_companion"]} revives left')
            else:
                logging.info(f'[{self.name:>{unit_name_spacing}}]:\tDIED')

    def load_full(self, file_path: str) -> None:
        """Load a full build loadout from a yaml file.

        Args:
            file_path (str): The path to the yaml config file.
        """
        with open(file_path, 'r') as f:
            cfg = yaml.safe_load(f)
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

    @property
    def max_hp(self) -> float:
        return round(
            (
                42
                + (self.base_stats["hp"] * (2.53 + 0.01 * (self.base_stats["hp"] // 5)))
                + (self.inscryptions["i3"] * 6)
                + (self.inscryptions["i27"] * 24)
            )
            * (1 + (self.attributes["soul_of_ares"] * 0.01))
        )

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
                + (self.attributes["essence_of_ylith"] * 0.03)
            )
            * (1 + (self.attributes["essence_of_ylith"] * 0.0075))
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