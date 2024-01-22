import logging
import random

from typing import List

unit_name_spacing: int = 7

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

        self.sim_queue_entry: tuple = None

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

    def receive_damage(self, _, damage: float, __: bool) -> float:
        """Receive damage from an attack.

        Args:
            _ (NoneType): Child classes use this to pass in the attacker to apply damage reflection.
            damage (float): The amount of damage to receive. Child classes have ways to mitigate this damage.
            __ (bool): Child classes use this to handle on-crit behaviour.

        Returns:
            float: The amount of damage received.
        """
        self.hp -= damage
        self.stun_duration = 0
        logging.debug(f"[{self.name:>{unit_name_spacing}}]:\tTAKE\t{damage:>6.2f}, {self.hp:.2f} left")
        self.check_death()
        return damage

    def heal_hp(self, value: float, source: str) -> None:
        """Applies healing to hp from different sources. Accounts for overhealing.

        Args:
            value (float): The amount of hp to heal.
            source (str): The source of the healing. Valid: regen, lifesteal, life_of_the_hunt
        """
        effective_value = min(value, self.missing_hp)
        self.hp += effective_value
        logging.debug(f'[{self.name:>{unit_name_spacing}}]:\t{source.upper().replace("_", " ")}\t{effective_value:>6.2f}')
        if source.casefold() == 'regen'.casefold():
            self.total_regen += effective_value

    def regen_hp(self) -> None:
        """Regenerates hp according to the regen stat.
        """
        regen_value = self.regen
        self.heal_hp(regen_value, 'regen')

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
            logging.debug(f'[{self.name:>{unit_name_spacing}}]:\tDIED')

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
        out = f'[{self.name:>{unit_name_spacing}}]:\t[HP:{(str(round(self.hp, 2)) + "/" + str(round(self.max_hp, 2))):>16}] [AP:{self.power:>7.2f}] [Speed:{self.get_speed():>5.2f}] [Regen:{self.regen:>6.2f}]'
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

    def attack(self, target: Unit) -> float:
        """Attack a target unit.

        Args:
            target (Unit): The unit to attack.

        Returns:
            float: The amount of damage dealt.
        """
        if random.random() < self.special_chance: # basic critical attack for extra damage
            damage = self.power * self.special_damage
            self.total_crits += 1
            is_crit = True
            logging.debug(f"[{self.name:>{unit_name_spacing}}]:\tATTACK\t{damage:>6.2f} (crit)")
        else:
            damage = self.power
            is_crit = False
            logging.debug(f"[{self.name:>{unit_name_spacing}}]:\tATTACK\t{damage:>6.2f}")
        self.total_damage += damage
        target.receive_damage(self, damage, is_crit)
        return damage

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

    def receive_damage(self, _, damage, is_crit: bool) -> float:
        """Receive damage from an attack. Accounts for damage reduction and evade chance.

        Args:
            _ (NoneType): The unit that is attacking. Used by child classes to apply damage reflection.
            damage (float): The amount of damage to receive.
            is_crit (bool): Child classes use this to handle on-crit behaviour.

        Returns:
            float: The amount of damage received after damage reduction, or 0 if the attack was evaded.
        """
        if random.random() < self.evade_chance:
            logging.debug(f'[{self.name:>{unit_name_spacing}}]:\tEVADE')
            return 0
        else:
            final_damage = damage * (1 - self.damage_reduction)
            super(Defence_Unit, self).receive_damage(None, final_damage, is_crit)
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

class Enemy(Defence_Unit):
    """Standard enemy unit. Used for regular stage enemies of Exon-12 and Endo Prime.
    """
    def __init__(self, name: str, hp: float, power: float, speed: float, regen: float, special_chance: float, special_damage: float, damage_reduction: float, evade_chance: float) -> None:
        super(Enemy, self).__init__(name=name, hp=hp, power=power, speed=speed, regen=regen, special_chance=special_chance, special_damage=special_damage, damage_reduction=damage_reduction, evade_chance=evade_chance)

class Boss(Defence_Unit):
    """Boss unit. Used for Exon-12 and Endo Prime.
    """
    def __init__(self, name: str, hp: float, power: float, speed: float, regen: float, special_chance: float, special_damage: float, damage_reduction: float, evade_chance: float) -> None:
        super(Boss, self).__init__(name=name, hp=hp, power=power, speed=speed, regen=regen, special_chance=special_chance, special_damage=special_damage, damage_reduction=damage_reduction, evade_chance=evade_chance)
        self.enrage_stacks = 0

    def get_speed(self) -> float:
        """Returns the speed of the unit, taking into account stun duration and enrage stacks. Enrage stacks are limited to 199 to maintain speed of >0.

        Returns:
            float: The speed of the unit.
        """
        # boss attack speed increases by 0.0475 every attack
        return (self.speed - 0.0475 * min(self.enrage_stacks, 199)) + self.stun_duration

    def attack(self, target: Unit) -> None:
        super(Boss, self).attack(target)
        self.enrage_stacks += 1
        logging.debug(f"[{self.name:>{unit_name_spacing}}]:\tENRAGE\t{self.enrage_stacks:>6.2f} stacks")


class Void:
    @staticmethod
    def __spawn(planet: int, stage: int) -> List:
        if planet == 0: # Exon-12
            if stage % 100 != 0 or stage == 0:
                return [
                    Enemy,
                    (9      + (stage * 4)) * (1 + ((stage // 100) * 1.85)),
                    (2.5    + (stage * 0.7)) * (1 + ((stage // 100) * 1.85)),
                    (4.53   - (stage * 0.006)),
                    (0.00   + ((stage - 1) * 0.08) if stage > 1 else 0) + ((stage // 100) * 0.42),
                    (0.0322 + (stage * 0.0004)),
                    (1.21   + (stage * 0.008025)),
                    (0),
                    (0      + ((stage // 100) * 0.0004)),
                ]
            else:
                return [
                    Boss,
                    36810,
                    263.18,
                    9.5,
                    15.21,
                    0.1122,
                    2.26,
                    0.05,
                    0.004,
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
        return [unit_stats[0](f'E{stage:>3}{i+1:>3}', *unit_stats[1:]) for i in range(unit_count)]

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
        return [unit_stats[0](f'E{stage:>3}{i+1:>3}', *unit_stats[1:]) for i in range(unit_count)]


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
