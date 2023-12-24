import logging
import math
import random

import yaml


class Unit:
    def __init__(self, name: str, hp: float, power: float, speed: float, regen: float) -> None:
        self.name: str = name
        self.max_hp: float = float(hp)
        self.hp: float = self.max_hp
        self.speed: float = speed
        self.power: float = power
        self.regen: float = regen
        self.stun_duration: float = 0

        self.total_damage: float = 0
        self.total_regen: float = 0
        self.total_crits: int = 0
        self.total_kills: int = 0

        self.elapsed_time: float = 0
        # either 0 or 1e-10, 0 gives an extra tick at the start, 1e-10 causes issues if your elapsed time hits a full integer along the way
        # since regen at max health doesnt do anything, 0 might be better

    def __repr__(self) -> str:
        return f'Name:{self.name}, HP:{round(self.hp, 2)}/{self.max_hp}, AP:{self.power}, Speed:{self.speed}, Regen:{self.regen}'

    def __str__(self) -> str:
        return f'Name:{self.name:>16}\nHP:{self.hp:>16}/{self.max_hp}\nAttack Power:{self.power:>8}\nHP Regen:{self.regen:>12.3}'
    
    def quick_info(self) -> str:
        return f'Name:{self.name}, HP:{(str(round(self.hp, 2)) + "/" + str(self.max_hp)):>13}  AP:{self.power:>7.2f}  Speed:{self.speed:>6.2f}  Regen:{self.regen:>6.2f}'

    def get_speed(self) -> float:
        if self.stun_duration > 0:
            # stunned period took twice the time, plus the rest of the time outside of the stun
            return ((self.speed - self.stun_duration) + self.stun_duration * 2)
        return self.speed
    
    def get_missing_hp(self) -> float:
        return self.max_hp - self.hp

    def receive_damage(self, _, damage: float) -> None:
        self.hp -= damage
        self.stun_duration = 0
        logging.info(f"[{self.name}]:\tTAKE {damage:.2f} damage, {self.hp:.2f} left")
        self.check_death()

    def __recursive_regen(self, ticks: int) -> None:
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
        ticks = len(range(math.ceil(self.elapsed_time), math.floor(self.elapsed_time + opponent_attack_speed)+1))
        self.elapsed_time += opponent_attack_speed
        self.__recursive_regen(ticks)

    def apply_stun(self, duration: float) -> None:
        self.stun_duration += duration

    def is_dead(self) -> bool:
        return self.hp <= 0
    
    def check_death(self) -> None:
        if self.is_dead():
            logging.info(f'[{self.name}]:\tDIED')

class Crit_Unit(Unit):
    def __init__(self, name: str, hp: float, power: float, speed: float, regen: float, special_chance: float, special_damage: float):
        super().__init__(name, hp, power, speed, regen)
        self.special_chance: float = special_chance
        self.special_damage: float = special_damage

    def __repr__(self) -> str:
        return f'Name:{self.name}, HP:{round(self.hp, 2)}/{self.max_hp}, AP:{self.power}, Speed:{self.speed}, Regen:{self.regen}, SC:{self.special_chance}, SD:{self.special_damage}'

    def __str__(self) -> str:
        return f'Name:{self.name:>16}\nHP:{self.hp:>16}/{self.max_hp}\nAttack Power:{self.power:>8}\nHP Regen:{self.regen:>12.3}\nSpecial Chance:{self.special_chance:>11.4}\nSpecial Damage:{self.special_damage:>9.2}'
    
    def quick_info(self) -> str:
        return f'Name:{self.name:<8} HP:{(str(round(self.hp, 2)) + "/" + str(self.max_hp)):>13}  AP:{self.power:>7.2f}  Speed:{self.speed:>6.2f}  Regen:{self.regen:>6.2f}  CHC:{self.special_chance:>7.4f}  CHD:{self.special_damage:>6.2f}'

    def attack(self, target: Unit) -> None:
        if random.random() < self.special_chance:
            damage = self.power * self.special_damage
            self.total_crits += 1
            logging.info(f"[{self.name}]:\tATTACK {damage:.2f} (crit)")
        else:
            damage = self.power
            logging.info(f"[{self.name}]:\tATTACK {damage:.2f} damage")
        self.total_damage += damage
        target.receive_damage(self, damage)

class Defence_Unit(Crit_Unit):
    def __init__(self, name: str, hp: float, power: float, speed: float, regen: float, special_chance: float, special_damage: float, damage_reduction: float, evade_chance: float):
        super().__init__(name, hp, power, speed, regen, special_chance, special_damage)
        self.damage_reduction: float = damage_reduction
        self.evade_chance: float = evade_chance

    def __repr__(self) -> str:
        return f'Name:{self.name}, HP:{round(self.hp, 2)}/{self.max_hp}, AP:{self.power}, Speed:{self.speed}, Regen:{self.regen}, DR:{self.damage_reduction}, Evasion:{self.evade_chance}'

    def __str__(self) -> str:
        return f'Name:{self.name:>16}\nHP:{self.hp:>16}/{self.max_hp}\nAttack Power:{self.power:>8}\nHP Regen:{self.regen:>12.3}\nDR:{self.damage_reduction:>11.4}\nEvasion:{self.evade_chance:>9.2}'
    
    def quick_info(self) -> str:
        return f'Name:{self.name}, HP:{round(self.hp, 2)}/{self.max_hp}, AP:{self.power}, Speed:{self.speed}, Regen:{self.regen}, DR:{self.damage_reduction}, Evasion:{self.evade_chance}'

    def receive_damage(self, attacker, damage) -> float:
        if random.random() < self.evade_chance:
            logging.info(f'[{self.name}]:\tEVADE')
            return 0
        else:
            final_damage = damage * (1 - self.damage_reduction)
            super().receive_damage(attacker, final_damage)
            return final_damage

class Enemy(Crit_Unit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class Boss(Defence_Unit):
    def __init__(self, name: str, hp: float, power: float, speed: float, regen: float, special_chance: float, special_damage: float, damage_reduction: float, evade_chance: float):
        super().__init__(name, hp, power, speed, regen, special_chance, special_damage, damage_reduction, evade_chance)

class Borge(Defence_Unit):
    def __init__(self, file_path: str):
        with open(file_path, 'r') as f:
            cfg = yaml.safe_load(f)
        super().__init__(
            cfg["stats"]["name"],
            cfg["stats"]["hp"],
            cfg["stats"]["power"],
            cfg["stats"]["speed"],
            cfg["stats"]["regen"],
            special_chance=cfg["stats"]["special_chance"],
            special_damage=cfg["stats"]["special_damage"],
            damage_reduction=cfg["stats"]["damage_reduction"],
            evade_chance=cfg["stats"]["evade_chance"],
        )
        self.effect_chance: float = cfg["stats"]["effect_chance"]
        self.lifesteal: float = 0
        self.leftover_attackspeed: float = 0
        self.stat_stripped = False

        # talents
        self.death_is_my_companion: int = cfg["talents"]["death_is_my_companion"]
        self.death_is_my_companion_effect: float = 0.8 # 80% revive

        self.life_of_the_hunt: int = cfg["talents"]["life_of_the_hunt"]
        self.life_of_the_hunt_effect: float = 0.06

        self.unfair_advantage: int = cfg["talents"]["unfair_advantage"]
        self.unfair_advantage_effect: float = 0.02

        self.impeccable_impacts: int = cfg["talents"]["impeccable_impacts"]
        self.impeccable_impacts_effect_stun: float = 0.1
        self.impeccable_impacts_effect_power: int = 2

        self.omen_of_defeat: int = cfg["talents"]["omen_of_defeat"]
        self.omen_of_defeat_effect: float = 0.08

        self.call_me_lucky_loot: int = cfg["talents"]["call_me_lucky_loot"]
        self.call_me_lucky_loot_effect: float = 0.2

        self.presence_of_god: int = cfg["talents"]["presence_of_god"]
        self.presence_of_god_effect: float = 0.04

        self.fires_of_war: int = cfg["talents"]["fires_of_war"]
        self.fires_of_war_effect: float = 0.1

        # attributes
        self.soul_of_ares: int = cfg["attributes"]["soul_of_ares"]
        self.soul_of_ares_effect_life: float = 0.01
        self.soul_of_ares_effect_power: float = 0.002

        self.essence_of_ylith: int = cfg["attributes"]["essence_of_ylith"]
        self.essence_of_ylith_effect_pct: float = 0.0075
        self.essence_of_ylith_effect_flat: float = 0.03

        self.helltouch_barrier: int = cfg["attributes"]["helltouch_barrier"]
        self.helltouch_barrier_effect: float = 0.08
        
        self.lifedrain_inhalers: int = cfg["attributes"]["lifedrain_inhalers"]
        self.lifedrain_inhalers_effect: float = 0.0008

        self.spartan_lineage: int = cfg["attributes"]["spartan_lineage"]
        self.spartan_lineage_effect: float = 0.015

        self.explosive_punches: int = cfg["attributes"]["explosive_punches"]
        self.explosive_punches_effect_chc: float = 0.044
        self.explosive_punches_effect_chd: float = 0.0008

        self.timeless_mastery: int = cfg["attributes"]["timeless_mastery"]
        self.timeless_mastery_effect: float = 0.14

        self.book_of_baal: int = cfg["attributes"]["book_of_baal"]
        self.book_of_baal_effect: float = 0.0111

        self.superior_sensors: int = cfg["attributes"]["superior_sensors"]
        self.superior_sensors_effect_evade: float = 0.016
        self.superior_sensors_effect_effect: float = 0.012

        # mods
        self.trample = cfg["mods"]["trample"]

    def __str__(self):
        return f'Name:{self.name:>16}\nHP:{self.hp:>16}/{self.max_hp}\nAttack Power:{self.power:>8}\nHP Regen:{self.regen:>12.3}\nDMG Reduction:{self.damage_reduction:>7.2}\nEvade Chance:{self.evasion:>10.3}\nEffect Chance:{self.effect_chance:>7.4}\nCrit Chance:{self.special_chance:>11.4}\nCrit Power:{self.special_damage:>9.2}'
    
    def __repr__(self) -> str:
        return f'Name:{self.name}, HP:{round(self.hp, 2)}/{self.max_hp}, AP:{self.power}, Speed:{self.speed}, Regen:{self.regen}, DR:{self.damage_reduction}, Evasion:{self.evade_chance}, Effect Chance:{self.effect_chance}, CHC:{self.special_chance}, CHD:{self.special_damage}'
    
    def quick_info(self) -> str:
        return f'Name:{self.name:<8} HP:{(str(round(self.hp, 2)) + "/" + str(self.max_hp)):>13}  AP:{self.power:>7.2f}  Speed:{self.get_speed():>6.2f}  Regen:{self.regen:>6.2f}  DR:{self.damage_reduction:>8.4f}  Evasion:{self.evade_chance:>8.4f}  Effect:{self.effect_chance:>8.4f}  CHC:{self.special_chance:>8.4f}  CHD:{self.special_damage:>6.2f}  LS:{self.lifesteal:>6.2f}'

    def get_speed(self) -> float:
        if self.leftover_attackspeed > 0:
            leftover_windup = abs(self.leftover_attackspeed - self.speed)
            # if (self.speed - leftover_windup) < 0:
                # logging.warning(f'--- Negative attack speed! Regular: {self.speed}, leftover wind-up: {self.leftover_attackspeed} (={leftover_windup})')
            return self.speed - leftover_windup
        return self.speed

    def attack(self, target: Unit) -> None:
        super().attack(target)
        self.leftover_attackspeed = 0 # reset leftover wind-up time after successful attack
        if self.impeccable_impacts > 0 and random.random() < self.effect_chance:
            stun_duration = self.impeccable_impacts * self.impeccable_impacts_effect_stun
            target.apply_stun(stun_duration) # stun slows attacks by half
            logging.info(f'[{target.name}]:\tSTUNNED {stun_duration} sec')


    def receive_damage(self, attacker: Unit, damage: float) -> None:
        final_damage = super().receive_damage(attacker, damage)
        if self.helltouch_barrier > 0 and final_damage > 0 and not self.is_dead():
            # reflected damage from helltouch barrier
            attacker.receive_damage(None, final_damage * self.helltouch_barrier * self.helltouch_barrier_effect)
            if attacker.is_dead():
                # attacker died from helltouck backlash while we were winding up an attack
                self.leftover_attackspeed = attacker.get_speed()
                logging.info(f'[{self.name}]:\tWIND-UP -{self.leftover_attackspeed - self.speed:.3f} sec')

    def regen_hp(self, opponent_attack_speed: float) -> None:
        ticks = len(range(math.ceil(self.elapsed_time), math.floor(self.elapsed_time + opponent_attack_speed)+1))
        self.elapsed_time += opponent_attack_speed
        self.__recursive_regen(ticks)

    def __recursive_regen(self, ticks: int) -> None:
        if ticks > 0:
            regen_value = self.regen + ((self.lifedrain_inhalers * self.lifedrain_inhalers_effect) * self.get_missing_hp())
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
        if self.presence_of_god > 0:
            enemy.hp = enemy.max_hp * self.presence_of_god * self.presence_of_god_effect
            logging.info(f'[{self.name}]:\tUSE {(self.presence_of_god * self.presence_of_god_effect)*100:.0f}% [Presence of a God]')

    def apply_trample(self, enemies):
        if len(enemies) < 10:
            return 0 # cant trample bosses
        trample_power = self.power // enemies[0].max_hp
        trample_kills = 0
        if trample_power > 1:
            for enemy in enemies:
                if not enemy.is_dead() and trample_kills < trample_power:
                    enemy.hp = 0
                    trample_kills += 1
        return trample_kills

    def check_death(self) -> None:
        if self.is_dead():
            if self.death_is_my_companion > 0:
                self.death_is_my_companion -= 1
                self.hp = self.max_hp * self.death_is_my_companion_effect
            else:
                logging.info(f'[{self.name}]:\tDIED')

    def get_results(self):
        return [self.total_damage, self.total_kills, self.total_crits, self.total_regen, self.hp]

    def strip_stats(self):
        self.max_hp *= (1 - self.soul_of_ares * self.soul_of_ares_effect_life)
        self.max_hp = round(self.max_hp, 0)
        self.hp = self.max_hp
        self.power = self.power * (1 - self.soul_of_ares * self.soul_of_ares_effect_power) - (self.impeccable_impacts * self.impeccable_impacts_effect_power)
        self.regen = self.regen * (1 - self.essence_of_ylith * self.essence_of_ylith_effect_pct) - (self.essence_of_ylith * self.essence_of_ylith_effect_flat)
        self.special_chance -= (self.explosive_punches * self.explosive_punches_effect_chc)
        self.special_damage -= (self.explosive_punches * self.explosive_punches_effect_chd)
        self.damage_reduction -= (self.spartan_lineage * self.spartan_lineage_effect)
        self.evade_chance -= (self.superior_sensors * self.superior_sensors_effect_evade)
        self.effect_chance -= (self.superior_sensors * self.superior_sensors_effect_effect)
        if self.lifesteal > 0:
            self.lifesteal -= (self.life_of_the_hunt * self.life_of_the_hunt_effect) - (self.book_of_baal * self.book_of_baal_effect)
        self.stat_stripped = True

    def apply_stats(self):
        self.max_hp *= (1 + self.soul_of_ares * self.soul_of_ares_effect_life)
        self.max_hp = round(self.max_hp, 0)
        self.hp = self.max_hp
        self.power = (self.power + (self.impeccable_impacts * self.impeccable_impacts_effect_power)) * (1 + self.soul_of_ares * self.soul_of_ares_effect_power)
        self.regen = (self.regen + (self.essence_of_ylith * self.essence_of_ylith_effect_flat)) * (1 + self.essence_of_ylith * self.essence_of_ylith_effect_pct)
        self.special_chance += (self.explosive_punches * self.explosive_punches_effect_chc)
        self.special_damage += (self.explosive_punches * self.explosive_punches_effect_chd)
        self.damage_reduction += (self.spartan_lineage * self.spartan_lineage_effect)
        self.evade_chance += (self.superior_sensors * self.superior_sensors_effect_evade)
        self.effect_chance += (self.superior_sensors * self.superior_sensors_effect_effect)
        self.lifesteal += (self.life_of_the_hunt * self.life_of_the_hunt_effect) + (self.book_of_baal * self.book_of_baal_effect)
        self.stat_stripped = False
