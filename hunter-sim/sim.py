import logging
import statistics

from units import Borge, Enemy, Boss


def make_stage(stage):
    if stage % 100 != 0 or stage == 0:
        return [
            stage,
            9      + (stage * 4),
            2.5    + (stage * 0.7),
            4.53   - (stage * 0.006),
            0.00   + ((stage - 1) * 0.08) if stage > 1 else 0,
            0.0322 + (stage * 0.0004),
            1.21   + (stage * 0.008),
        ]
    else: # bosses, currently only stage 100 known
        return [
            stage,
            40900,
            290.0,
            7.85,
            15.84,
            0.1222,
            2.26,
            0.05,
            0.005,
        ]

# TODO maybe round(x,2) + ceil for the inhaler regen, getting 1.63 instead of _1.64_

def simulate_combat(borge):
    current_stage = 0
    while not borge.is_dead():
        enemies = [Enemy(f'Enemy_{i}', *make_stage(current_stage)[1:]) for i in range(10)]
        logging.info(f'Entering STAGE {current_stage}')
        for enemy in enemies:
            if enemy.is_dead():
                continue
            logging.info(borge.quick_info())
            logging.info(enemy.quick_info())
            if borge.trample:
                trample_kills = borge.apply_trample(enemies)
                if trample_kills > 0:
                    logging.info(f'[{borge.name}]:\tTRAMPLE {trample_kills} enemies')
                    continue
            if borge.presence_of_god > 0:
                borge.apply_pog(enemy)
                logging.info(enemy.quick_info())
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

def simulate_combat_2(hunter: Borge) -> None:
    current_stage = 0
    while not hunter.is_dead():
        if current_stage % 100 != 0 or current_stage == 0:
            enemies = [Enemy(f'Enemy_{i}', *make_stage(current_stage)[1:]) for i in range(10)]
        else:
            enemies = [Boss(f'Boss_{i}', *make_stage(current_stage)[1:]) for i in range(1)]
        logging.info(f'Entering STAGE {current_stage}')
        for enemy in enemies:
            if enemy.is_dead():
                continue
            logging.info("")
            logging.info(hunter.quick_info())
            logging.info(enemy.quick_info())
            if hunter.trample:
                trample_kills = hunter.apply_trample(enemies)
                if trample_kills > 0:
                    logging.info(f'[{hunter.name}]:\tTRAMPLE {trample_kills} enemies')
                    hunter.total_kills += trample_kills
                    continue
            if hunter.presence_of_god > 0:
                hunter.apply_pog(enemy)
                logging.info(enemy.quick_info())
            while not enemy.is_dead() and not hunter.is_dead():
                if hunter.get_speed() <= enemy.get_speed(): # hunter goes first
                    enemy.regen_hp(hunter.get_speed())
                    hunter.attack(enemy)
                    if enemy.is_dead():
                        hunter.regen_hp(hunter.get_speed())
                        continue
                    hunter.regen_hp(enemy.get_speed())
                    enemy.attack(hunter)
                    if hunter.is_dead():
                        return current_stage
                else: # enemy goes first
                    hunter.regen_hp(enemy.get_speed())
                    enemy.attack(hunter)
                    if enemy.is_dead():
                        continue
                    if hunter.is_dead():
                        return current_stage
                    enemy.regen_hp(hunter.get_speed())
                    hunter.attack(enemy)
            hunter.total_kills += 1
        current_stage += 1
    return current_stage


def main():
    logging.basicConfig(
        # filename='sanity2_log',
        # filemode='a',
        # level=logging.INFO,
    )
    logging.getLogger().setLevel(logging.WARNING)

    stats = {
        'total_damage': [],
        'total_regen' : [],
        'total_crits': [],
        'total_kills': [],
        'last_hp': [],
        'survived': [],
        'elapsed_time': [],
        'final_stage': [],
        }
    for _ in range(200):
        borge = Borge('./hunter-sim/builds/current.yaml')
        # borge.max_hp += 10 * 2.74
        # borge.power += 10 * 0.57
        # borge.regen += 10 * 0.05
        # borge.damage_reduction += 10 * 0.0144
        # borge.evade_chance += 10 * 0.0034
        # borge.effect_chance += 10 * 0.005
        # borge.special_chance += 10 * 0.0018
        # borge.special_damage += 10 * 0.0001
        # borge.speed -= 10 * 0.03
        final_stage = simulate_combat_2(borge)
        total_dmg, total_kills, total_crits, total_regen, last_hp = borge.get_results()
        stats['total_damage'].append(total_dmg)
        stats['total_regen'].append(total_regen)
        stats['total_crits'].append(total_crits)
        stats['total_kills'].append(total_kills)
        stats['last_hp'].append(last_hp)
        stats['survived'].append(not borge.is_dead())
        stats['elapsed_time'].append(borge.elapsed_time)
        stats['final_stage'].append(final_stage)

    if len(stats['last_hp']) > 1:
        print(f'Average over {len(stats["last_hp"])} runs:')
        print(f'Avg total damage: {statistics.fmean(stats["total_damage"]):>10.2f}\t(+/- {statistics.stdev(stats["total_damage"]):>7.2f})\n'
            + f'Avg total regen: {statistics.fmean(stats["total_regen"]):>11.2f}\t(+/- {statistics.stdev(stats["total_regen"]):>7.2f})\n'
            + f'Avg total crits: {statistics.fmean(stats["total_crits"]):>11.2f}\t(+/- {statistics.stdev(stats["total_crits"]):>7.2f})\n'
            + f'Avg total kills: {statistics.fmean(stats["total_kills"]):>11.2f}\t(+/- {statistics.stdev(stats["total_kills"]):>7.2f})\n'
            + f'Avg final hp: {statistics.fmean(stats["last_hp"]):>14.2f}\t(+/- {statistics.stdev(stats["last_hp"]):>7.2f})\n'
            + f'Elapsed time: {statistics.fmean(stats["elapsed_time"])/60:>14.2f}min\t(+/- {statistics.stdev(stats["elapsed_time"])/60:>7.2f})\n'
            + f'Survival %: {statistics.fmean(stats["survived"])*100:>16.2f}\t(+/- {statistics.stdev(stats["survived"])*100:>7.2f})\n'
            + f'# Stage 100 reached: {stats["final_stage"].count(100):>7.2f}')
    print(borge.quick_info())


if __name__ == "__main__":
    main()

# TODO: not sure when to remove stuns. currently removed on receiving damage but no idea how to handle multiple stuns during the same attack wind-up
# or what would happen if a hunter's attack speed would be more than twice as fast than an enemy and it would attack twice in that time