import logging
import math
import random

from typing import List

import yaml


class Unit:
    """A basic unit class that can be used to create enemies, bosses, and hunters. Only used for inheritance.
    """
    def __init__(self, name: str, hp: float, power: float, speed: float, regen: float) -> None:
        self.name: str = name
        self.max_hp: float = float(hp)
        self.hp: float = float(hp)
        self.speed: float = speed
        self.power: float = power
        self.regen: float = regen
        self.stun_duration: float = 0
        self.missing_hp: float

        self.total_damage: float = 0
        self.total_regen: float = 0
        self.total_crits: int = 0
        self.total_kills: int = 0

        # either 0 or 1e-10, 0 gives an extra tick at the start, 1e-10 causes issues if your elapsed time hits a full integer along the way
        # since regen at max health doesnt do anything, 0 might be better
        self.elapsed_time: float = 0

    def get_speed(self) -> float:
        """Returns the speed of the unit, taking into account the stun duration.

        Returns:
            float: The speed of the unit.
        """
        if self.stun_duration > 0:
            # stunned period took twice the time, plus the rest of the time outside of the stun
            return ((self.speed - self.stun_duration) + self.stun_duration * 2)
        return self.speed

    def receive_damage(self, _, damage: float) -> None:
        """Receive damage from an attack.

        Args:
            _ (NoneType): Child classes use this to pass in the attacker to apply damage reflection.
            damage (float): The amount of damage to receive. Child classes have ways to mitigate this damage.
        """
        self.hp -= damage
        self.stun_duration = 0
        logging.info(f"[{self.name}]:\tTAKE {damage:.2f} damage, {self.hp:.2f} left")
        self.check_death()

    def __recursive_regen(self, ticks: int) -> None:
        """Recursively regen hp over time.

        Args:
            ticks (int): The number of ticks to regen hp. Decrements by 1 each recursive call.
        """
        if ticks > 0:
            regen_value = self.regen
            if (self.hp + regen_value) <= self.max_hp:
                self.hp += regen_value
                self.total_regen += regen_value
                logging.info(f'[{self.name}]:\tREGEN {regen_value:.2f} hp')
            else:
                logging.info(f'[{self.name}]:\tREGEN {self.max_hp - self.hp:.2f} hp (full)')
                self.total_regen += (self.max_hp - self.hp)
                self.hp = self.max_hp
            self.__recursive_regen(ticks-1)

    def regen_hp(self, opponent_attack_speed: float) -> None:
        """Regen hp over time.

        Args:
            opponent_attack_speed (float): The attack speed of the opponent.
        """
        ticks = len(range(math.ceil(self.elapsed_time), math.floor(self.elapsed_time + opponent_attack_speed)+1))
        self.elapsed_time += opponent_attack_speed
        self.__recursive_regen(ticks)

    def stun(self, duration: float) -> None:
        """Apply a stun to the unit.

        Args:
            duration (float): The duration of the stun.
        """
        self.stun_duration += duration

    def is_dead(self) -> bool:
        """Check if the unit is dead.

        Returns:
            bool: True if the unit is dead, False otherwise.
        """
        return self.hp <= 0
    
    def check_death(self) -> None:
        """Check if the unit is dead and log it if it is.
        """
        if self.is_dead():
            logging.info(f'[{self.name}]:\tDIED')

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError("Name must be a string")
        self._name = value

    @property
    def max_hp(self) -> float:
        return self._max_hp

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
    def speed(self) -> float:
        return self._speed

    @speed.setter
    def speed(self, value: float) -> None:
        self._speed = value

    @property
    def power(self) -> float:
        return self._power

    @power.setter
    def power(self, value: float) -> None:
        self._power = value

    @property
    def regen(self) -> float:
        return self._regen

    @regen.setter
    def regen(self, value: float) -> None:
        self._regen = value

    @property
    def stun_duration(self) -> float:
        return self._stun_duration

    @stun_duration.setter
    def stun_duration(self, value: float) -> None:
        self._stun_duration = value

    @property
    def missing_hp(self) -> float:
        return self.max_hp - self.hp

    def __str__(self) -> str:
        out = f'[{self.name:>6}] [HP:{(str(round(self.hp, 2)) + "/" + str(self.max_hp)):>14}] [AP:{self.power:>7.2f}] [Speed:{self.get_speed():>5.2f}] [Regen:{self.regen:>6.2f}]'
        if hasattr(self, 'special_chance'):
            out += f' [CHC: {self.special_chance:>6.4f}]'
        if hasattr(self, 'special_damage'):
            out += f' [CHD: {self.special_damage:>5.2f}]'
        if hasattr(self, 'damage_reduction'):
            out += f' [DR: {self.damage_reduction:>6.4f}]'
        if hasattr(self, 'evade_chance'):
            out += f' [Evasion: {self.evade_chance:>6.4f}]'
        if hasattr(self, 'effect_chance'):
            out += f' [Effect: {self.effect_chance:>6.4f}]'
        if hasattr(self, 'lifesteal'):
            out += f' [LS: {self.lifesteal:>4.2f}]'
        return out

class Crit_Unit(Unit):
    """Extends the base Unit class to add critical chance and critical damage. Only used for inheritance.
    """
    def __init__(self, special_chance: float, special_damage: float, **kwargs):
        super(Crit_Unit, self).__init__(**kwargs)
        self.special_chance: float = special_chance
        self.special_damage: float = special_damage

    def attack(self, target: Unit) -> None:
        """Attack a target unit.

        Args:
            target (Unit): The unit to attack.
        """
        if random.random() < self.special_chance: # basic critical attack for extra damage
            damage = self.power * self.special_damage
            self.total_crits += 1
            logging.info(f"[{self.name}]:\tATTACK {damage:.2f} (crit)")
        else:
            damage = self.power
            logging.info(f"[{self.name}]:\tATTACK {damage:.2f} damage")
        self.total_damage += damage
        target.receive_damage(self, damage)

    @property
    def special_chance(self) -> float:
        return self._special_chance

    @special_chance.setter
    def special_chance(self, value: float) -> None:
        self._special_chance = value

    @property
    def special_damage(self) -> float:
        return self._special_damage

    @special_damage.setter
    def special_damage(self, value: float) -> None:
        self._special_damage = value

class Defence_Unit(Crit_Unit):
    """Extends the base Unit class to add damage reduction and evade chance. Only used for inheritance.
    """
    def __init__(self, damage_reduction: float, evade_chance: float, **kwargs):
        super(Defence_Unit, self).__init__(**kwargs)
        self.damage_reduction: float = damage_reduction
        self.evade_chance: float = evade_chance

    def receive_damage(self, _, damage) -> float:
        """Receive damage from an attack. Accounts for damage reduction and evade chance.

        Args:
            _ (NoneType): The unit that is attacking. Used by child classes to apply damage reflection.
            damage (float): The amount of damage to receive.

        Returns:
            float: The amount of damage received after damage reduction, or 0 if the attack was evaded.
        """
        if random.random() < self.evade_chance:
            logging.info(f'[{self.name}]:\tEVADE')
            return 0
        else:
            final_damage = damage * (1 - self.damage_reduction)
            super().receive_damage(None, final_damage)
            return final_damage

    @property
    def damage_reduction(self) -> float:
        return self._damage_reduction

    @damage_reduction.setter
    def damage_reduction(self, value: float) -> None:
        self._damage_reduction = value

    @property
    def evade_chance(self) -> float:
        return self._evade_chance

    @evade_chance.setter
    def evade_chance(self, value: float) -> None:
        self._evade_chance = value

class Enemy(Crit_Unit):
    """Standard enemy unit. Used for regular stage enemies of Exon-12 and Endo Prime.
    """
    def __init__(self, name: str, hp: float, power: float, speed: float, regen: float, special_chance: float, special_damage: float) -> None:
        super(Enemy, self).__init__(name=name, hp=hp, power=power, speed=speed, regen=regen, special_chance=special_chance, special_damage=special_damage)

class Boss(Defence_Unit):
    """Boss unit. Used for Exon-12 and Endo Prime.
    """
    def __init__(self, name: str, hp: float, power: float, speed: float, regen: float, special_chance: float, special_damage: float, damage_reduction: float, evade_chance: float) -> None:
        super(Boss, self).__init__(name=name, hp=hp, power=power, speed=speed, regen=regen, special_chance=special_chance, special_damage=special_damage, damage_reduction=damage_reduction, evade_chance=evade_chance)

    def attack(self, target: Unit) -> None:
        super().attack(target)
        self.speed -= 0.035 # boss attack speed increases by 0.035 every attack

class Hunter(Defence_Unit):
    """Base class for hunter units. Extends enemy classes to add lifesteal and effect chance. Only used for inheritance.
    """
    def __init__(self, effect_chance: float, **kwargs):
        super(Hunter, self).__init__(**kwargs)
        self.effect_chance: float = effect_chance
        self.lifesteal: float = 0

    def apply_stun(self, target: Unit) -> None:
        if "impeccable_impacts" in self.talents:
            stun_duration = self.talents["impeccable_impacts"] * 0.1
        elif "thousand_needles" in self.talents:
            stun_duration = self.talents["thousand_needles"] * 0.05
        else:
            raise ValueError("No stun talent found")
        if stun_duration > 0:
            target.stun(stun_duration)
            logging.info(f'[{target.name}]:\tSTUNNED {stun_duration} sec')

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
                logging.info(f'[{self.name}]:\tWIND-UP -{self.leftover_attackspeed - self.speed:.3f} sec')

    def regen_hp(self, opponent_attack_speed: float) -> None:
        """Regen hp over time.

        Args:
            opponent_attack_speed (float): The attack speed of the opponent.
        """
        ticks = len(range(math.ceil(self.elapsed_time), math.floor(self.elapsed_time + opponent_attack_speed)+1))
        self.elapsed_time += opponent_attack_speed
        self.__recursive_regen(ticks)

    def __recursive_regen(self, ticks: int) -> None:
        """Recursively regen hp over time.

        Args:
            ticks (int): The number of ticks to regen hp. Decrements by 1 each call.
        """
        if ticks > 0:
            regen_value = self.regen + ((self.attributes["lifedrain_inhalers"] * 0.0008) * self.missing_hp)
            if (self.hp + regen_value) <= self.max_hp:
                self.hp += regen_value
                self.total_regen += regen_value
                logging.info(f'[{self.name}]:\tREGEN {round(regen_value, 2)} hp')
            else:
                logging.info(f'[{self.name}]:\tREGEN {round(self.max_hp - self.hp, 2)} hp (full)')
                self.total_regen += (self.max_hp - self.hp)
                self.hp = self.max_hp
            self.__recursive_regen(ticks-1)

    def apply_pog(self, enemy: Unit) -> None:
        """Apply the Presence of a God effect to an enemy.

        Args:
            enemy (Unit): The enemy to apply the effect to.
        """
        if self.talents["presence_of_god"] > 0:
            pog_effect = self.talents["presence_of_god"] * 0.04
            enemy.hp = enemy.max_hp * pog_effect
            logging.info(f'[{self.name}]:\tUSE {pog_effect*100:.0f}% [Presence of a God]')
            logging.info(enemy)


    def apply_trample(self, enemies: List[Enemy]) -> int:
        """Apply the Trample effect to a list of enemies.

        Args:
            enemies (List[Enemy]): The list of enemies to apply the effect to.

        Returns:
            int: The number of enemies killed by the trample effect.
        """
        if len(enemies) < 10:
            return 0 # cant trample bosses
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
                logging.info(f'[{self.name}]:\tREVIVED. {self.talents["death_is_my_companion"]} revives left')
            else:
                logging.info(f'[{self.name}]:\tDIED')

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
                (self.base_stats["hp"] * (2.53 + 0.01 * (self.base_stats["hp"] // 5)))
                + (self.inscryptions["i3"] * 6)
                + (self.inscryptions["i27"] * 24)
                + 42
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
            (self.base_stats["damage_reduction"] * 0.0144)
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

class Void:
    @staticmethod
    def __spawn(planet: int, stage: int) -> List:
        if planet == 0: # Exon-12
            if stage % 100 != 0 or stage == 0:
                return [
                    Enemy,
                    9      + (stage * 4),
                    2.5    + (stage * 0.7),
                    4.53   - (stage * 0.006),
                    0.00   + ((stage - 1) * 0.08) if stage > 1 else 0,
                    0.0322 + (stage * 0.0004),
                    1.21   + (stage * 0.008),
                ]
            else:
                return [
                    Boss,
                    36810,
                    275.5,
                    7.85,
                    15.44,
                    0.1222,
                    2.26,
                    0.05,
                    0.005,
                ]
        elif planet == 1: # Endo Prime
            if stage % 100 != 0 or stage == 0:
                return [
                    Enemy,
                    11     + (stage * 6),
                    1.35   + (stage * 0.75),
                    3.20   - (stage * 0.004),
                    0.02   + ((stage-1) * 0.1) if stage >= 1 else 0,
                    0.0994 + (stage * 0.0006),
                    1.03   + (stage * 0.008),
                ]
            else:
                return [
                    Boss,
                    30550,
                    305.40,
                    5.61,
                    79.36,
                    0.3594,
                    1.83,
                    0.0,
                    0.0,
                ]
        else:
            raise ValueError("Invalid planet")

    @staticmethod
    def spawn_exon12(stage: int) -> List[Unit]:
        """Spawns units from Exon-12 and stage.

        Args:
            stage (int): The stage to spawn units from.

        Returns:
            List[Unit]: The list of spawned units. Either 10 regular units or 1 boss, depending on the stage.
        """
        unit_stats = Void.__spawn(0, stage)
        unit_count = 1 if stage % 100 == 0 and stage > 0 else 10
        return [unit_stats[0](f'E{stage:>3}{i+1:>2}', *unit_stats[1:]) for i in range(unit_count)]

    @staticmethod
    def spawn_endoprime(stage: int) -> Unit:
        """Spawns units from Exon-12 and stage.

        Args:
            stage (int): The stage to spawn units from.

        Returns:
            List[Unit]: The list of spawned units. Either 10 regular units or 1 boss, depending on the stage.
        """
        unit_stats = Void.__spawn(1, stage)
        unit_count = 1 if stage % 100 == 0 and stage > 0 else 10
        return [unit_stats[0](f'E{stage:>3}{i+1:>2}', *unit_stats[1:]) for i in range(unit_count)]


if __name__ == '__main__':
    # upg = calculate_upgrades(hunter_type=Borge, hp_lvl=152, power_lvl=127, regen_lvl=90, dr_level=27, evade_level=28, effect_lvl=29, special_chance_lvl=35, special_damage_lvl=31, speed_lvl=19)
    # upg = calculate_upgrades(hunter_type=Borge, hp_lvl=56, power_lvl=41, regen_lvl=17, dr_level=12, evade_level=9, effect_lvl=8, special_chance_lvl=9, special_damage_lvl=7, speed_lvl=9)
    # upg = calculate_upgrades(hunter_type=Borge, hp_lvl=155, power_lvl=127, regen_lvl=90, dr_level=27, evade_level=28, effect_lvl=29, special_chance_lvl=35, special_damage_lvl=31, speed_lvl=19)
    b = Borge('./hunter-sim/builds/new_stats_test.yaml')
    print(b)
    # e = Void.spawn_exon12(99)
    # print(e[0])

# on bosses
# PoG is 50% effective
# Omen is 50% effective
# Reflect is 10% effective
