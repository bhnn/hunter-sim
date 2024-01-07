import unittest

from units import Borge, Boss, Enemy, Unit, Void


class TestUnits(unittest.TestCase):
    def setUp(self):
        pass

    def test_unit_is_dead(self):
        basic_stats = [9, 2.5, 4.53, 0.0]
        u = Unit('Basic_Unit', *basic_stats)
        self.assertFalse(u.is_dead())

    def test_enemy_is_dead(self):
        crit_stats = [9, 2.5, 4.53, 0.0, 0.25, 1.5]
        e = Enemy('Enemy_Unit', *crit_stats)
        self.assertFalse(e.is_dead())

    def test_boss_is_dead(self):
        def_stats = [9, 2.5, 4.53, 0.0, 0.25, 1.5, 0.33, 0.2]
        b = Boss('Boss_Unit', *def_stats)
        self.assertFalse(b.is_dead())

    def test_borge_is_dead(self):
        b = Borge('./hunter-sim/builds/current.yaml')
        self.assertFalse(b.is_dead())

    def test_get_speed(self):
        basic_stats = [9, 2.5, 4.53, 0.0]
        u = Unit('Basic_Unit', *basic_stats)
        self.assertEqual(u.get_speed(), 4.53)

    def test_stun(self):
        basic_stats = [9, 2.5, 4.53, 0.0]
        u = Unit('Basic_Unit', *basic_stats)
        u.stun(0.7)
        self.assertEqual(u.stun_duration, 0.7)
        self.assertEqual(u.get_speed(), 5.23)

    def test_missing_hp(self):
        basic_stats = [9, 2.5, 4.53, 0.0]
        u = Unit('Basic_Unit', *basic_stats)
        self.assertEqual(u.hp, 9)
        u.receive_damage(None, 5)
        self.assertEqual(u.missing_hp, 5)
        self.assertEqual(u.hp, 4)

    def test_regen_basic(self):
        basic_stats = [405, 71.8, 3.9360, 7.84]
        u = Unit('Basic_Unit', *basic_stats)
        self.assertEqual(u.hp, 405)
        u.receive_damage(None, 200)
        self.assertEqual(u.hp, 205)
        self.assertEqual(u.missing_hp, 200)
        u.regen_hp(4.53)
        self.assertEqual(round(u.hp, 4), 205 + (5 * 7.84))

    def test_unit_is_really_dead(self):
        basic_stats = [9, 2.5, 4.53, 0.0]
        u = Unit('Basic_Unit', *basic_stats)
        self.assertFalse(u.is_dead())
        u.receive_damage(None, 9)
        self.assertTrue(u.is_dead())

    def test_crit_chance(self):
        crit_stats = [405, 71.8, 3.9360, 7.84, 0.0718, 2.002]
        e = Enemy('Unit', *crit_stats)
        dummy = Unit('Dummy', 0, 0, 0, 0)
        # TODO: find good test for crit chance

    def test_receive_damage_basic(self):
        # no evade to prevent the test from failing randomly
        boss_stats = [36810, 275.5, 7.85, 15.44, 0.1222, 2.26, 0.05, 0.0]
        b = Boss('Boss_Unit', *boss_stats)
        b.receive_damage(None, 1000)
        self.assertEqual(b.hp, 35860)
        self.assertEqual(b.missing_hp, 950)

    def test_unit_spawn_amount(self):
        enemies = Void.spawn_exon12(1)
        self.assertEqual(len(enemies), 10)
        enemies = Void.spawn_exon12(100)
        self.assertEqual(len(enemies), 1)
        enemies = Void.spawn_endoprime(1)
        self.assertEqual(len(enemies), 10)
        enemies = Void.spawn_endoprime(100)
        self.assertEqual(len(enemies), 1)


if __name__ == '__main__':
    unittest.main()