import unittest

from bpcontrol.effects import EFFECTS, q15_from_db, db_from_q15


class TestEffects(unittest.TestCase):
    def test_six_effects(self):
        self.assertEqual(len(EFFECTS), 6)
        self.assertEqual(EFFECTS["guitar_chorus"].command, 0x8F)
        self.assertEqual(EFFECTS["pitch_shifter_pro"].get_param("pitch").index, 1)
        self.assertFalse(EFFECTS["guitar_pingpong"].get_param("max_delay").writable)

    def test_q15(self):
        self.assertEqual(q15_from_db(-6), 16422)
        self.assertEqual(q15_from_db(-7), 14636)
        self.assertEqual(q15_from_db(-8), 13045)
        self.assertAlmostEqual(db_from_q15(16422), -6, places=2)
        with self.assertRaises(ValueError):
            q15_from_db(3)


if __name__ == "__main__":
    unittest.main()
