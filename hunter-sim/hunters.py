import logging
import random
from heapq import heappush as hpush
from typing import List

import yaml

hunter_name_spacing: int = 7

# TODO: add Lucky Loot mechanics
# TODO: maybe find a better way to trample()

class Hunter:
    ### SETUP
    def __init__(self, name: str) -> None:
        self.name = name
        self.missing_hp: float
        self.sim = None

        # statistics
        # main
        self.current_stage = 0
        self.total_kills: int = 0
        self.revive_log = []
        self.enrage_log = []

        # offence
        self.total_attacks: int = 0
        self.total_damage: float = 0
        self.total_crits: int = 0
        self.total_extra_from_crits: float = 0

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
        # TODO include loot

    def load_dummy(self) -> dict:
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
        if not self.validate_config(cfg):
            raise ValueError("Invalid config file")
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
        return cfg.keys() == self.load_dummy().keys() and all(cfg[k].keys() == self.load_dummy()[k].keys() for k in cfg.keys())

    def attack(self, target) -> float:
        """Attack the enemy unit.

        Args:
            target (Enemy): The enemy to attack.

        Returns:
            float: The damage dealt.
        """
        if random.random() < self.special_chance:
            damage = self.power * self.special_damage
            self.total_crits += 1
            self.total_extra_from_crits += (damage - self.power)
            logging.debug(f"[{self.name:>{hunter_name_spacing}}]:\tATTACK\t{damage:>6.2f} (crit)")
        else:
            damage = self.power
            logging.debug(f"[{self.name:>{hunter_name_spacing}}]:\tATTACK\t{damage:>6.2f}")
        target.receive_damage(damage)
        self.total_damage += damage
        self.total_attacks += 1
        return damage

    def receive_damage(self, damage: float) -> float:
        """Receive damage from an attack. Accounts for damage reduction, evade chance and reflected damage.

        Args:
            damage (float): The amount of damage to receive.
        """
        if random.random() < self.evade_chance:
            self.total_evades += 1
            logging.debug(f'[{self.name:>{hunter_name_spacing}}]:\tEVADE')
            return 0
        else:
            mitigated_damage = damage * (1 - self.damage_reduction)
            self.hp -= mitigated_damage
            self.total_taken += mitigated_damage
            self.total_mitigated += (damage - mitigated_damage)
            self.total_attacks_suffered += 1
            logging.debug(f"[{self.name:>{hunter_name_spacing}}]:\tTAKE\t{mitigated_damage:>6.2f}, {self.hp:.2f} HP left")
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
        logging.debug(f'[{self.name:>{hunter_name_spacing}}]:\t{source.upper().replace("_", " ")}\t{effective_heal:>6.2f} (+{overhealing:>6.2f} OVERHEAL)')
        match source.lower():
            case 'regen':
                self.total_regen += effective_heal
            case 'steal':
                self.total_lifesteal += effective_heal
            case 'loth':
                self.total_loth += effective_heal
            case 'potion':
                self.unfair_advantage += effective_heal
            case _:
                raise ValueError(f'Unknown heal source: {source}')

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
        if len(self.revive_log) < self.talents["death_is_my_companion"]:
            self.hp = self.max_hp * 0.8
            self.revive_log.append((self.current_stage, self.total_kills))
            logging.debug(f'[{self.name:>{hunter_name_spacing}}]:\tREVIVED, {self.talents["death_is_my_companion"]} left')
        else:
            logging.debug(f'[{self.name:>{hunter_name_spacing}}]:\tDIED\n')


    ### UTILITY
    @property
    def missing_hp(self) -> float:
        return self.max_hp - self.hp

    def __str__(self) -> str:
        """Prints the stats of this Hunter's instance.

        Returns:
            str: The stats as a formatted string.
        """
        return f'[{self.name:>{hunter_name_spacing}}]:\t[HP:{(str(round(self.hp, 2)) + "/" + str(round(self.max_hp, 2))):>16}] [AP:{self.power:>7.2f}] [Speed:{self.speed:>5.2f}] [Regen:{self.regen:>6.2f}] [CHC: {self.special_chance:>6.4f}] [CHD: {self.special_damage:>5.2f}] [DR: {self.damage_reduction:>6.4f}] [Evasion: {self.evade_chance:>6.4f}] [Effect: {self.effect_chance:>6.4f}] [LS: {self.lifesteal:>4.2f}]'


class Borge(Hunter):
    ### SETUP
    def __init__(self, config_path: str):
        super(Borge, self).__init__(name='Borge')
        self.__create__(config_path)

        # statistics
        # offence
        self.total_helltouch: float = 0

        # sustain
        self.total_loth: float = 0
        self.total_potion: float = 0

    def __create__(self, config_path: str) -> None:
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
        damage = super(Borge, self).attack(target)
        self.heal_hp(damage * self.lifesteal, 'steal')
        if random.random() < self.effect_chance and (LotH := self.talents["life_of_the_hunt"]):
            # Talent: Life of the Hunt
            LotH_healing = damage * LotH * 0.06
            self.heal_hp(LotH_healing, "loth")
            self.total_loth += LotH_healing
            self.total_effect_procs += 1
        if random.random() < self.effect_chance and self.talents["impeccable_impacts"]:
            # Talent: Impeccable Impacts, will call apply_stun()
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
            attacker (Unit): The unit that is attacking. Used to apply damage reflection.
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
            attacker.receive_damage(reflected_damage)

    def regen_hp(self) -> None:
        """Regenerates hp according to the regen stat, modified by the `Lifedrain Inhalers` attribute.
        """
        regen_value = self.regen + ((self.attributes["lifedrain_inhalers"] * 0.0008) * self.missing_hp)
        self.heal_hp(regen_value, 'regen')

    ### SPECIALS
    def on_kill(self) -> None:
        if random.random() < self.effect_chance and (ua := self.talents["unfair_advantage"]):
            # Talent: Unfair Advantage
            potion_healing = self.max_hp * (ua * 0.02)
            self.heal_hp(potion_healing, "potion")
            self.total_potion += potion_healing
            self.total_effect_procs += 1
        if random.random() < self.effect_chance and (LL := self.talents["call_me_lucky_loot"]):
            # Talent: Call Me Lucky Loot
            # 1 + (0.2 x LL) extra loot
            self.total_effect_procs += 1
            pass

    def apply_stun(self, enemy) -> None:
        """Apply a stun to an enemy.

        Args:
            enemy (Enemy): The enemy to stun.
        """
        stun_duration = self.talents['impeccable_impacts'] * 0.1
        enemy.stun(stun_duration)

    def apply_pog(self, enemy) -> None:
        """Apply the Presence of a God effect to an enemy.

        Args:
            enemy (Unit): The enemy to apply the effect to.
        """
        stage_effect = 0.5 if self.current_stage % 100 == 0 and self.current_stage > 0 else 1
        pog_effect = (self.talents["presence_of_god"] * 0.04) * stage_effect
        enemy.hp = enemy.max_hp * (1 - pog_effect)

    def apply_fow(self) -> None:
        """Apply the temporaryFires of War effect to Borge.
        """
        self.fires_of_war = self.talents["fires_of_war"] * 0.1
        logging.debug(f'[{self.name:>{hunter_name_spacing}}]:\t[FoW]]\t{self.fires_of_war:>6.2f} sec')

    def apply_trample(self, enemies: List) -> int:
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
    def speed(self) -> float:
        """Getter for the speed attribute. Accounts for the Fires of War effect and resets it afterwards.

        Returns:
            float: The speed of the hunter.
        """
        current_speed = self._speed - self.fires_of_war
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
        return {
            'total_damage': self.total_damage,
            'total_kills': self.total_kills,
            'total_crits': self.total_crits,
            'total_regen': self.total_regen,
            'total_lifesteal': self.total_lifesteal,
            'total_taken': self.total_taken,
            'total_loth': self.total_loth,
            'total_potion': self.total_potion,
            'revive_log': self.revive_log,
            'final_hp': self.hp,
            'survived': not self.is_dead(),
            'elapsed_time': self.elapsed_time,
            'final_stage': self.current_stage,
        }

class Ozzy(Hunter):
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

if __name__ == "__main__":
    b = Borge('./builds/current.yaml')
    print(b)