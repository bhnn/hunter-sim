import logging
import math
import random
import statistics

import yaml


class Character:
    def __init__(self, name, hp, power, speed, regen, crit_chance, crit_damage):
        self.name = name
        self.max_hp = hp
        self.hp = hp
        self.speed = speed
        self.power = power
        self.regen = regen
        self.crit_chance = crit_chance
        self.crit_damage = crit_damage
        self.stun_duration = 0

        self.total_damage = 0
        self.total_regen = 0
        self.total_crits = 0
        self.total_kills = 0

        self.elapsed_time = 0
        # either 0 or 1e-10, 0 gives an extra tick at the start, 1e-10 causes issues if your elapsed time hits a full integer along the way
        # since regen at max health doesnt do anything, this might be better

    def __repr__(self) -> str:
        return f'Name:{self.name}, HP:{round(self.hp, 2)}/{self.max_hp}, AP:{self.power:}, Speed:{self.speed}, Regen:{self.regen}, CHC:{self.crit_chance}, CHD:{self.crit_damage}'

    def __str__(self) -> str:
        return f'Name:{self.name:>16}\nHP:{self.hp:>16}/{self.max_hp}\nAttack Power:{self.power:>8}\nHP Regen:{self.regen:>12.3}\nCrit Chance:{self.crit_chance:>11.4}\nCrit Power:{self.crit_damage:>9.2}'
    
    def quick_info(self):
        return f'Name:{self.name}, HP:{round(self.hp, 2)}/{self.max_hp}, AP:{self.power:}, Speed:{self.speed}, Regen:{self.regen}, CHC:{self.crit_chance}, CHD:{self.crit_damage}'

    def get_speed(self):
        if self.stun_duration > 0:
            return ((self.speed - self.stun_duration) + self.stun_duration * 2)
        return self.speed
    
    def get_missing_hp(self):
        return self.max_hp - self.hp

    def attack(self, target):
        if random.random() < self.crit_chance:
            damage = self.power * self.crit_damage
            self.total_crits += 1
            logging.info(f"[{self.name}]: attacks for {round(damage, 2)} (crit)")
        else:
            damage = self.power
            logging.info(f"[{self.name}]: attacks for {damage} damage")
        self.total_damage += damage
        target.receive_damage(self, damage)

    def receive_damage(self, _, damage):
        self.hp -= damage
        logging.info(f"[{self.name}]: takes {round(damage, 2)} damage, {round(self.hp, 2)} left")
        self.check_death()

    def __recursive_regen(self, ticks):
        if ticks > 0:
            regen_value = self.regen
            if (self.hp + regen_value) <= self.max_hp:
                self.hp += regen_value
                self.total_regen += regen_value
                logging.info(f'[{self.name}]: regen {round(regen_value, 2)} hp')
            else:
                logging.info(f'[{self.name}]: regen {round(self.max_hp - self.hp, 2)} hp (full)')
                self.total_regen += (self.max_hp - self.hp)
                self.hp = self.max_hp
            self.__recursive_regen(ticks-1)

    def regen_hp(self, opponent_attack_speed):
        ticks = len(range(math.ceil(self.elapsed_time), math.floor(self.elapsed_time + opponent_attack_speed)+1))
        self.elapsed_time += opponent_attack_speed
        self.__recursive_regen(ticks)

    def apply_stun(self, duration):
        self.stun_duration += duration

    def is_dead(self):
        return self.hp <= 0
    
    def check_death(self):
        if self.is_dead():
            logging.info(f'[{self.name}]: has died')

class Enemy(Character):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class Borge(Character):
    def __init__(self, file):
        with open(file, 'r') as f:
            cfg = yaml.safe_load(f)
        super().__init__(
            name=cfg["stats"]["name"],
            hp=cfg["stats"]["hp"],
            power=cfg["stats"]["power"],
            speed=cfg["stats"]["speed"],
            regen=cfg["stats"]["regen"],
            crit_chance=cfg["stats"]["crit_chance"],
            crit_damage=cfg["stats"]["crit_damage"]
        )
        self.damage_reduction = cfg["stats"]["damage_reduction"]
        self.evasion = cfg["stats"]["evade_chance"]
        self.effect_chance = cfg["stats"]["effect_chance"]

        self.lifedrain_inhaler = 4
        self.lifedrain_inhaler_effect = 0.0008

        self.helltouch_barrier = 1
        self.helltouch_barrier_effect = 0.08

        self.impeccable_impacts = 8
        self.impeccable_impacts_effect = 0.1

        self.rebirths = 2
        self.rebirths_effect = 0.8

    def __str__(self):
        return f'Name:{self.name:>16}\nHP:{self.hp:>16}/{self.max_hp}\nAttack Power:{self.power:>8}\nHP Regen:{self.regen:>12.3}\nDMG Reduction:{self.damage_reduction:>7.2}\nEvade Chance:{self.evasion:>10.3}\nEffect Chance:{self.effect_chance:>7.4}\nCrit Chance:{self.crit_chance:>11.4}\nCrit Power:{self.crit_damage:>9.2}'

    def attack(self, target):
        super().attack(target)
        if self.impeccable_impacts > 0 and random.random() < self.effect_chance:
            target.apply_stun(self.impeccable_impacts * self.impeccable_impacts_effect) # stun slows attacks by half

    def receive_damage(self, attacker, damage):
        if random.random() < self.evasion:
            logging.info(f'[{self.name}]: evades!')
        else:
            final_damage = damage * (1 - self.damage_reduction)
            super().receive_damage(attacker, final_damage)
            if self.helltouch_barrier > 0:
                # reflected damage from helltouch barrier
                attacker.receive_damage(None, final_damage * self.helltouch_barrier * self.helltouch_barrier_effect)

    def regen_hp(self, opponent_attack_speed):
        ticks = len(range(math.ceil(self.elapsed_time), math.floor(self.elapsed_time + opponent_attack_speed)+1))
        self.elapsed_time += opponent_attack_speed
        self.__recursive_regen(ticks)

    def __recursive_regen(self, ticks):
        if ticks > 0:
            regen_value = self.regen + ((self.lifedrain_inhaler * self.lifedrain_inhaler_effect) * self.get_missing_hp())
            if (self.hp + regen_value) <= self.max_hp:
                self.hp += regen_value
                self.total_regen += regen_value
                logging.info(f'[{self.name}]: regen {round(regen_value, 2)} hp')
            else:
                logging.info(f'[{self.name}]: regen {round(self.max_hp - self.hp, 2)} hp (full)')
                self.total_regen += (self.max_hp - self.hp)
                self.hp = self.max_hp
            self.__recursive_regen(ticks-1)

    def check_death(self):
        if self.is_dead():
            if self.rebirths > 0:
                self.rebirths -= 1
                self.hp = self.max_hp * self.rebirths_effect
            else:
                logging.info(f'[{self.name}]: has died')

    def get_results(self):
        return [self.total_damage, self.total_kills, self.total_crits, self.total_regen, self.hp]

def make_stage(stage):
    return [
        stage,
        9      + (stage * 4),
        2.5    + (stage * 0.7),
        4.53   - (stage * 0.006),
        0.00   + ((stage - 1) * 0.08) if stage > 1 else 0,
        0.0322 + (stage * 0.0004),
        1.21   + (stage * 0.008),
    ]

# TODO maybe round(x,2) + ceil for the inhaler regen, getting 1.63 instead of _1.64_

def simulate_combat(borge):
    current_stage = 0
    while not borge.is_dead():
        # TODO generate new enemies for stage
        enemies = [Enemy(f'Enemy_{i}', *make_stage(current_stage)[1:]) for i in range(10)]
        logging.info(f'Entering STAGE {current_stage}')
        for enemy in enemies:
            logging.info(borge.quick_info())
            logging.info(enemy.quick_info()) # TODO set each enemy to Enemy0-9 to identify from log
            while not enemy.is_dead():
                if borge.get_speed() <= enemy.get_speed():
                    faster = borge
                    slower = enemy
                else:
                    faster = enemy
                    slower = borge
                # faster character attacks slower one
                slower.regen_hp(faster.get_speed())
                faster.attack(slower)
                if borge.is_dead():
                    return
                if slower.is_dead(): # in case slower is the enemy
                    continue
                # slower character attacks faster one
                faster.regen_hp(slower.get_speed())
                slower.attack(faster)
                if borge.is_dead():
                    return
                if faster.is_dead():
                    continue
            borge.total_kills += 1
        current_stage += 1
    logging.warning('REACHED END OF AVAILABLE STAGES!')

def main():
    logging.basicConfig(
        filename='sanity2_log',
        filemode='a',
        level=logging.INFO,
    )
    logging.getLogger().setLevel(logging.INFO)

    stats = {
        'total_damage': [],
        'total_regen' : [],
        'total_crits': [],
        'total_kills': [],
        'last_hp': [],
        'survived': [],
        }
    for _ in range(20):
        borge = Borge('./borge-sim/builds/current.yaml')
        # borge.max_hp += 10 * 2.74
        # borge.power += 10 * 0.57
        # borge.regen += 10 * 0.05
        # borge.damage_reduction += 10 * 0.0144
        # borge.evasion += 10 * 0.0034
        # borge.effect_chance += 10 * 0.005
        # borge.crit_chance += 10 * 0.0018
        # borge.crit_damage += 10 * 0.0001
        # borge.speed -= 10 * 0.03
        simulate_combat(borge)
        total_dmg, total_kills, total_crits, total_regen, last_hp = borge.get_results()
        stats['total_damage'].append(total_dmg)
        stats['total_regen'].append(total_regen)
        stats['total_crits'].append(total_crits)
        stats['total_kills'].append(total_kills)
        stats['last_hp'].append(last_hp)
        stats['survived'].append(not borge.is_dead())
    
    print(borge.quick_info())
    if len(stats['last_hp']) > 1:
        print(f'Avg total damage: {statistics.fmean(stats["total_damage"]):>10.2f}\t(+/- {statistics.stdev(stats["total_damage"]):>7.2f})\n'
            + f'Avg total regen: {statistics.fmean(stats["total_regen"]):>11.2f}\t(+/- {statistics.stdev(stats["total_regen"]):>7.2f})\n'
            + f'Avg total crits: {statistics.fmean(stats["total_crits"]):>11.2f}\t(+/- {statistics.stdev(stats["total_crits"]):>7.2f})\n'
            + f'Avg total kills: {statistics.fmean(stats["total_kills"]):>11.2f}\t(+/- {statistics.stdev(stats["total_kills"]):>7.2f})\n'
            + f'Avg final hp: {statistics.fmean(stats["last_hp"]):>14.2f}\t(+/- {statistics.stdev(stats["last_hp"]):>7.2f})\n'
            + f'Survival %: {statistics.fmean(stats["survived"])*100:>16.2f}\t(+/- {statistics.stdev(stats["survived"])*100:>7.2f})')
    

if __name__ == "__main__":
    main()

# DR 450.5 > regen 406.9 > speed 404.5 > eva 384.1 > maxhp 383.2 > power 378.4 > effect 375.5 > CHC 374.6 > default 373.7 > CHD 373.5
# DR 601.0 > regen 529.0 > speed 516 > evasion 499.9 > hp 498.1 > power 495.6 > chd 491.5 > effect 490.2 > default/chc 488.7
'''
borge lvl13 current (max stage 54):
hp 370 (2.73, 2/5, 102 total, 6.92k)
power 72.76 (0.57, 3/10, 73 total, 4.52k)
hp regen 2.19 (0.04, 23/30, 53 total, 15.53k)
dr 33.10 (1.44, 20/50 total, 126.22k)
evade 7.12 (0.34, 18/50 total, 16.66k)
effect 18.5 (0.5, 17/50 total, 26.84k)
chc 11.78 (0.18, 16/100 total, 309)
chd 1.42 (0.01, 12/100 total, 167)
speed 4.55s (-0.03, 11/100 total, 1.91k)
--
2 rebirth
1 life of the hunt
10 impact
--
1 ares
1 ylith
1 spartan
5 timeless mastery
1 helltouch
9 inhaler
--
inscryption #23 3/5
inscryption #24 9/10

after reset:
hp 366
power 52.61
hp regen 2.14
dr 31.60
evade 7.12
effect 18.5
chc 11.78
chd 1.42
speed 4.55s

after 1 impact:
power 54.61

after 1 ares:
hp 370
power 54.72

after more impacts:
2: power 56.72
3: power 58.73
4: power 60.73
5: power 62.74
6: power 64.74
7: power 66.74

after superior sensors:
1: evade  8.72 effect 19.7
2: evade 10.32 effect 20.90
3: evade 11.92 effect 22.10
4: evade 13.52 effect 23.30
5: evade 15.12 effect 24.50

after 1 ylith:
regen: 2.19

after 1 spartan lineage:
dr: 33.10
----
power: (baseline + impact + ...) * ares
regen: (baseline + flat ylith) * % ylith
evade: (baseline + flat superior sensors)
effect:(baseline + flat superior sensors)
lifesteal: (damage * (life of the hunt + book of baal))
'''