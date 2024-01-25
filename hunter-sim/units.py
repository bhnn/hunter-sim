import logging
import random
from heapq import heapify
from heapq import heappush as hpush

from hunters import Borge, Hunter, Ozzy

unit_name_spacing: int = 7

# TODO: reverse Benchy attack speed. 6.73 in-game, then maybe different decrement?

class Enemy:
    ### CREATION
    def __init__(self, name: str, hunter: Hunter, stage: int, sim) -> None:
        """Creates an Enemy instance.

        Args:
            name (str): Name of the enemy. Usually `E{stage}{number}`.
            hunter (Hunter): The hunter that this enemy is fighting.
            stage (int): The stage of the enemy, for stat selection.
            sim (Simulation): The simulation that this enemy is a part of.
        """
        self.__create__(name=name, **self.fetch_stats(hunter, stage))
        self.sim = sim
        self.on_create(hunter)

    def fetch_stats(self, hunter: Hunter, stage: int) -> dict:
        if isinstance(hunter, Borge):
            return {
                'hp':               (9      + (stage * 4)) * (1 + ((stage // 100) * 1.85)),
                'power':            (2.5    + (stage * 0.7)) * (1 + ((stage // 100) * 1.85)),
                'regen':            (0.00   + ((stage - 1) * 0.08) if stage > 1 else 0) + ((stage // 100) * 0.42),
                'special_chance':   (0.0322 + (stage * 0.0004)),
                'special_damage':   (1.21   + (stage * 0.008025)),
                'damage_reduction': (0),
                'evade_chance':     (0      + ((stage // 100) * 0.0004)),
                'speed':            (4.53   - (stage * 0.006)),
            }
        elif isinstance(hunter, Ozzy):
            return {
                'hp':               11     + (stage * 6),
                'power':            1.35   + (stage * 0.75),
                'regen':            0.02   + ((stage-1) * 0.1) if stage >= 1 else 0,
                'special_chance':   0.0994 + (stage * 0.0006),
                'special_damage':   1.03   + (stage * 0.008),
                'damage_reduction': 0,
                'evade_chance':     0,
                'speed':            3.20   - (stage * 0.004),
            }
        else:
            raise ValueError(f'Unknown hunter: {hunter}')

    def __create__(self, name: str, hp: float, power: float, regen: float, damage_reduction: float, evade_chance: float, 
                 special_chance: float, special_damage: float, speed: float) -> None:
        self.name: str = name
        self.hp: float = float(hp)
        self.max_hp: float = float(hp)
        self.power: float = power
        self.regen: float = regen
        self.damage_reduction: float = damage_reduction
        self.evade_chance: float = evade_chance
        # patch 2024-01-24: enemies cant exceed 25% crit chance and 250% crit damage
        self.special_chance: float = min(special_chance, 0.25)
        self.special_damage: float = min(special_damage, 2.5)
        self.speed: float = speed
        self.stun_duration: float = 0
        self.missing_hp: float

    def on_create(self, hunter: Hunter) -> None:
        """Executes on creation effects such as Presence of God, Omen of Defeat, and Soul of Snek.

        Args:
            hunter (Hunter): The hunter that this enemy is fighting.
        """
        if 'presence_of_god' in hunter.talents:
            hunter.apply_pog(self)
        if 'omen_of_defeat' in hunter.talents:
            hunter.apply_ood(self)
        if 'soul_of_snek' in hunter.attributes:
            hunter.apply_snek(self)


    ### CONTENT
    def attack(self, hunter: Hunter) -> None:
        """Attack the hunter.

        Args:
            hunter (Hunter): The hunter to attack.
        """
        if random.random() < self.special_chance:
            damage = self.power * self.special_damage
            is_crit = True
            logging.debug(f"[{self.name:>{unit_name_spacing}}][@{self.sim.elapsed_time:>5}]:\tATTACK\t{damage:>6.2f} (crit)")
        else:
            damage = self.power
            is_crit = False
            logging.debug(f"[{self.name:>{unit_name_spacing}}][@{self.sim.elapsed_time:>5}]:\tATTACK\t{damage:>6.2f}")
        hunter.receive_damage(self, damage, is_crit)

    def receive_damage(self, damage: float, is_reflected: bool = False) -> None:
        """Receive damage from an attack. Accounts for damage reduction and evade chance.

        Args:
            damage (float): Damage to receive.
        """
        if not is_reflected and random.random() < self.evade_chance:
            logging.debug(f"[{self.name:>{unit_name_spacing}}][@{self.sim.elapsed_time:>5}]:\tEVADE")
        else:
            mitigated_damage = damage * (1 - self.damage_reduction)
            self.hp -= mitigated_damage
            logging.debug(f"[{self.name:>{unit_name_spacing}}][@{self.sim.elapsed_time:>5}]:\tTAKE\t{mitigated_damage:>6.2f}, {self.hp:.2f} HP left")
            if self.is_dead():
                self.on_death()

    def heal_hp(self, value: float, source: str) -> None:
        """Applies healing to hp from different sources. Accounts for overhealing.

        Args:
            value (float): The amount of hp to heal.
            source (str): The source of the healing. Valid: regen, lifesteal, life_of_the_hunt
        """
        effective_heal = min(value, self.missing_hp)
        self.hp += effective_heal
        logging.debug(f"[{self.name:>{unit_name_spacing}}][@{self.sim.elapsed_time:>5}]:\t{source.upper().replace('_', ' ')}\t{effective_heal:>6.2f}")

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
        qe = [(p1, p2, u) for p1, p2, u in self.sim.queue if u == 'enemy'][0]
        self.sim.queue.remove(qe)
        hpush(self.sim.queue, (qe[0] + duration, qe[1], qe[2]))
        logging.debug(f"[{self.name:>{unit_name_spacing}}][@{self.sim.elapsed_time:>5}]:\tSTUNNED\t{duration:>6.2f} sec")

    def is_dead(self) -> bool:
        """Check if the unit is dead.

        Returns:
            bool: True if the unit is dead, False otherwise.
        """
        return self.hp <= 0

    def on_death(self) -> None:
        """Executes on death effects. For enemy units, that is mostly just removing them from the sim queue and incrementing hunter kills.
        """
        self.sim.hunter.total_kills += 1
        logging.debug(f"[{self.name:>{unit_name_spacing}}][@{self.sim.elapsed_time:>5}]:\tDIED")
        self.sim.queue = [(p1, p2, u) for p1, p2, u in self.sim.queue if u != 'enemy']
        heapify(self.sim.queue)

    def kill(self) -> None:
        """Kills the unit.
        """
        self.hp = 0
        # not sure about this one yet
        # self.on_death()

    ### UTILITY

    @property
    def missing_hp(self) -> float:
        """Calculates the missing hp of the unit.

        Returns:
            float: The missing hp of the unit.
        """
        return self.max_hp - self.hp

    def __str__(self) -> str:
        """Prints the stats of this Enemy's instance.

        Returns:
            str: The stats as a formatted string.
        """
        return f'[{self.name:>{unit_name_spacing}}]:\t[HP:{(str(round(self.hp, 2)) + "/" + str(round(self.max_hp, 2))):>16}] [AP:{self.power:>7.2f}] [Speed:{self.speed:>5.2f}] [Regen:{self.regen:>6.2f}] [CHC: {self.special_chance:>6.4f}] [CHD: {self.special_damage:>5.2f}] [DR: {self.damage_reduction:>6.4f}] [Evasion: {self.evade_chance:>6.4f}]'


class Boss(Enemy):
    ### CREATION
    def __init__(self, name: str, hunter: Hunter, stage: int, sim) -> None:
        """Creates a Boss instance.

        Args:
            name (str): Name of the boss. Usually `E{stage}{number}`.
            hunter (Hunter): The hunter that this boss is fighting.
            stage (int): The stage of the boss, for stat selection.
            sim (Simulation): The simulation that this enemy is a part of.
        """
        super(Boss, self).__init__(name, hunter, stage, sim)
        self.enrage_stacks: int = 0
        if isinstance(hunter, Borge):
            self.enrage_effect = 0.0475
        elif isinstance(hunter, Ozzy):
            self.enrage_effect = 0.033658536585365856
        else:
            raise ValueError(f'Unknown hunter: {hunter}')

    def fetch_stats(self, hunter: Hunter, stage: int) -> dict:
        """Fetches the stats of the boss.

        Args:
            hunter (Hunter): The hunter that this boss is fighting.
            stage (int): The stage of the boss, for stat selection.

        Raises:
            ValueError: If the hunter is not a valid hunter.

        Returns:
            dict: The stats of the boss.
        """
        if isinstance(hunter, Borge):
            return {
                'hp': 36810,
                'power': 263.18,
                'regen': 15.21,
                'special_chance': 0.1122,
                'special_damage': 2.26,
                'damage_reduction': 0.05,
                'evade_chance': 0.004,
                'speed': 9.50,
            }
        elif isinstance(hunter, Ozzy):
            return {
                'hp': 29330,
                'power': 229.05,
                'regen': 85.7,
                'special_chance': 0.3094,
                'special_damage': 1.83,
                'damage_reduction': 0,
                'evade_chance': 0,
                'speed': 6.75, # 6.73 base in-game
            }
        else:
            raise ValueError(f'Unknown hunter: {hunter}')

    def attack(self, hunter: Hunter) -> None:
        """Attack the hunter.

        Args:
            hunter (Hunter): The hunter to attack.
        """
        super(Boss, self).attack(hunter)
        self.enrage_stacks += 1
        logging.debug(f"[{self.name:>{unit_name_spacing}}][@{self.sim.elapsed_time:>5}]:\tENRAGE\t{self.enrage_stacks:>6.2f} stacks")

    # def receive_damage(self, damage: float) -> None:
    #     """Receive damage from an attack. Accounts for damage reduction and evade chance.

    #     Args:
    #         damage (float): Damage to receive.
    #     """
    #     super(Boss, self).receive_damage(damage)
    #     if self.is_dead():
    #         self.on_death()

    def on_death(self) -> None:
        """Extends the Enemy::enrage() method to log enrage stacks on death.
        """
        super(Boss, self).on_death()
        self.sim.hunter.enrage_log.append(self.enrage_stacks)

    @property
    def speed(self) -> float:
        """Calculates the speed of the boss, taking enrage stacks into account.
        """
        return (self._speed - 0.0475 * min(self.enrage_stacks, 199))

    @speed.setter
    def speed(self, value: float) -> None:
        """Sets the speed of the boss.

        Args:
            value (float): The speed of the boss.
        """
        self._speed = value


if __name__ == "__main__":
    h = Borge('./builds/current.yaml')
    e = Enemy("Enemy", h, 99, None)
    h.current_stage = 100
    b = Boss("Boss", h, 100, None)
    print(e)
    print(b)
