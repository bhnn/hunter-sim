import logging
import random
from heapq import heapify
from heapq import heappush as hpush

from hunters import Borge, Hunter, Ozzy

unit_name_spacing: int = 7

# TODO: Verify whether Gothmogor's secondary attack contributes to enrage stacks

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
        """Fetches the stats of the enemy.

        Args:
            hunter (Hunter): The hunter that this enemy will be fighting, for enemy type selection.
            stage (int): The stage of the enemy, for stat selection.

        Raises:
            ValueError: If the hunter is not a valid hunter.

        Returns:
            dict: The stats of the enemy.
        """
        if isinstance(hunter, Borge):
            return {
                'hp': (
                    (9 + (stage * 4))
                    * (2.85 if stage > 100 else 1)
                    * (1 + ((stage // 150) * (stage-149) * (0.006 + 0.006 * (stage-150) // 50)) if stage >= 150 else 1)
                ),
                'power': (
                    (2.5 + (stage * 0.7))
                    * (2.85 if stage > 100 else 1)
                    * (1 + ((stage-149) * (0.006 + 0.006 * (stage-150) // 50)) if stage >= 150 else 1)
                ),
                'regen': (
                    (0.00 + ((stage - 1) * 0.08) if stage > 1 else 0)
                    * (1.052 if stage > 100 else 1)
                    * (1 + ((stage-149) * (0.006 + 0.006 * (stage-150) // 50)) if stage >= 150 else 1)
                ),
                'special_chance': (0.0322 + (stage * 0.0004)),
                'special_damage': (1.21 + (stage * 0.008025)),
                'damage_reduction': (0),
                'evade_chance': (
                    0
                    + (0.004 if stage > 100 else 0)
                ),
                'speed':(4.53 - (stage * 0.006)),
            }
        elif isinstance(hunter, Ozzy):
            return {
                'hp': (
                    (11 + (stage * 6))
                    * (2.9 if stage > 100 else 1)
                    * (1 + ((stage // 150) * (stage-149) * (0.006 + 0.006 * (stage-150) // 50)) if stage >= 150 else 1)
                ),
                'power': (
                    (1.35 + (stage * 0.75))
                    * (2.7 if stage > 100 else 1)
                    * (1 + ((stage-149) * (0.006 + 0.006 * (stage-150) // 50)) if stage >= 150 else 1)
                ),
                'regen': (
                    (0.02 + ((stage-1) * 0.1) if stage > 0 else 0)
                    * (1.25 if stage > 100 else 1)
                    * (1 + ((stage-149) * (0.006 + 0.006 * (stage-150) // 50)) if stage >= 150 else 1)
                ),
                'special_chance': 0.0994 + (stage * 0.0006),
                'special_damage': 1.03 + (stage * 0.008),
                'damage_reduction': 0,
                'evade_chance': (
                    0
                    + (0.01 if stage > 100 else 0)
                ),
                'speed': 3.20 - (stage * 0.004),
            }
        else:
            raise ValueError(f'Unknown hunter: {hunter}')

    def __create__(self, name: str, hp: float, power: float, regen: float, damage_reduction: float, evade_chance: float, 
                 special_chance: float, special_damage: float, speed: float, **kwargs) -> None:
        """Creates an Enemy instance.

        Args:
            name (str): Name of the enemy. Usually `E{stage}{number}`.
            hp (float): Max HP value of the enemy.
            power (float): Power value of the enemy.
            regen (float): Regen value of the enemy.
            damage_reduction (float): Damage reduction value of the enemy.
            evade_chance (float): Evade chance value of the enemy.
            special_chance (float): Special chance (for now crit-only) value of the enemy.
            special_damage (float): Special damage value of the enemy.
            speed (float): Speed value of the enemy.
            **kwargs: Optional arguments for special attacks and secondary speeds.
                special (str): Name of the special attack of the enemy.
                speed2 (float): Speed of the secondary attack of the enemy.
        """
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
        self.has_special = False
        if isinstance(self, Boss): # regular boss enrage effect
            self.enrage_effect = kwargs['enrage_effect']
        if isinstance(self, Boss) and 'special' in kwargs: # boss enrage effect for secondary moves
            self.secondary_attack: str = kwargs['special']
            self.speed2: float = kwargs['speed2']
            self.enrage_effect2 = kwargs['enrage_effect2']
            self.has_special: bool = True
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
        if 'gift_of_medusa' in hunter.attributes:
            hunter.apply_medusa(self)

    ### CONTENT
    def queue_initial_attack(self) -> None:
        """Queue the initial attacks of the enemy.
        """
        hpush(self.sim.queue, (round(self.sim.elapsed_time + self.speed, 3), 2, 'enemy'))
        if self.has_special:
            hpush(self.sim.queue, (round(self.sim.elapsed_time + self.speed2, 3), 2, 'enemy_special'))

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
        # handle death from Ozzy's Gift of Medusa
        if self.is_dead():
            self.on_death()

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
        return f'[{self.name:>{unit_name_spacing}}]:\t[HP:{(str(round(self.hp, 2)) + "/" + str(round(self.max_hp, 2))):>18}] [AP:{self.power:>7.2f}] [Regen:{self.regen:>6.2f}] [DR: {self.damage_reduction:>6.4f}] [Evasion: {self.evade_chance:>6.4f}] [Effect: ------] [CHC: {self.special_chance:>6.4f}] [CHD: {self.special_damage:>5.2f}] [Speed:{self.speed:>5.2f}]{(f" [Speed2:{self.speed2:>6.2f}]") if self.has_special else ""}'


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
        self.max_enrage: bool = False

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
            if stage == 100:
                return {
                    'hp': 36810,
                    'power': 263.18,
                    'regen': 15.21,
                    'special_chance': 0.1122,
                    'special_damage': 2.26,
                    'damage_reduction': 0.05,
                    'evade_chance': 0.004,
                    'speed': 9.50,
                    'enrage_effect': 0.0475,
                    'enrage_effect2': 0,
                }
            elif stage == 200:
                return {
                    'hp': 272250,
                    'power': 1930,
                    'regen': 42.19,
                    'special_chance': 0.1522,
                    'special_damage': 2.50,
                    'damage_reduction': 0.09,
                    'evade_chance': 0.004,
                    'speed': 8.05,
                    'speed2': 14.49,
                    'special': 'gothmorgor',
                    'enrage_effect': 0.04,
                    'enrage_effect2': 0.0725,
                }
            else:
                raise ValueError(f'Invalid stage for boss creation: {stage}')
        elif isinstance(hunter, Ozzy):
            if stage == 100:
                return {
                    'hp': 29328,
                    'power': 229.05,
                    'regen': 59.52,
                    'special_chance': 0.3094,
                    'special_damage': 1.83,
                    'damage_reduction': 0.05,
                    'evade_chance': 0.01,
                    'speed': 6.87,
                    'enrage_effect': 0.033658536585365856,
                    'enrage_effect2': 0,
                }
            elif stage == 200:
                return {
                    'hp': 221170,
                    'power': 1610,
                    'regen': 196.01,
                    'special_chance': 0.25,
                    'special_damage': 2.50,
                    'damage_reduction': 0.09,
                    'evade_chance': 0.01,
                    'speed': 5.89,
                    'speed2': 25.4,
                    'special': 'exoscarab',
                    'enrage_effect': 0.029,
                    'enrage_effect2': 0,
                }
            else:
                raise ValueError(f'Invalid stage for boss creation: {stage}')
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
        if self.enrage_stacks >= 200 and not self.max_enrage:
            self.max_enrage = True
            self.power *= 3
            self.special_chance = 1
            logging.debug(f"[{self.name:>{unit_name_spacing}}][@{self.sim.elapsed_time:>5}]:\tMAX ENRAGE (x3 damage, 100% crit chance)")

    def attack_special(self, hunter: Hunter) -> None:
        """Attack the hunter with a special attack.

        Args:
            hunter (Hunter): The hunter to attack.
        """
        if self.secondary_attack == 'gothmorgor':
            if random.random() < self.special_chance:
                damage = self.power * self.special_damage
                is_crit = True
                logging.debug(f"[{self.name:>{unit_name_spacing}}][@{self.sim.elapsed_time:>5}]:\tATTACK\t{damage:>6.2f} SECONDARY (crit)")
            else:
                damage = self.power
                is_crit = False
                logging.debug(f"[{self.name:>{unit_name_spacing}}][@{self.sim.elapsed_time:>5}]:\tATTACK\t{damage:>6.2f} SECONDARY")
            hunter.receive_damage(self, damage, is_crit)
            self.enrage_stacks += 1
        elif self.secondary_attack == 'exoscarab':
            self.enrage_stacks += 5
        else:
            raise ValueError(f'Unknown special attack: {self.secondary_attack}')

    def on_death(self) -> None:
        """Extends the Enemy::enrage() method to log enrage stacks on death.
        """
        super(Boss, self).on_death()
        self.sim.hunter.enrage_log.append(self.enrage_stacks)

    @property
    def speed(self) -> float:
        """Calculates the speed of the boss, taking enrage stacks into account.
        """
        return max((self._speed - self.enrage_effect * self.enrage_stacks), 0.5)

    @speed.setter
    def speed(self, value: float) -> None:
        """Sets the speed of the boss.

        Args:
            value (float): The speed of the boss.
        """
        self._speed = value

    @property
    def speed2(self) -> float:
        """Calculates the speed2 of the boss, taking enrage stacks into account.
        """
        return max((self._speed2 - self.enrage_effect2 * self.enrage_stacks), 0.5)

    @speed2.setter
    def speed2(self, value: float) -> None:
        """Sets the speed2 of the boss.

        Args:
            value (float): The speed2 of the boss.
        """
        self._speed2 = value


if __name__ == "__main__":
    b = Borge('./builds/current_borge.yaml')
    b.complete_stage(200)
    boss = Boss('E200', b, 200, None) 
    print(boss)
    boss.enrage_stacks = 11
    print(boss)
    e = Enemy('E199', b, 199, None)
    print(e)
