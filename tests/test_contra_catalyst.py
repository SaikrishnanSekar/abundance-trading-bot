"""Tests for the skip_contra_catalyst experiment logic."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import exp_contra_catalyst as E


class ContraLogic(unittest.TestCase):
    def test_long_into_negative_is_contra(self):
        self.assertTrue(E.is_contra("LONG", "negative"))

    def test_short_into_positive_is_contra(self):
        self.assertTrue(E.is_contra("SHORT", "positive"))

    def test_supportive_not_contra(self):
        self.assertFalse(E.is_contra("LONG", "positive"))
        self.assertFalse(E.is_contra("SHORT", "negative"))

    def test_neutral_not_contra(self):
        self.assertFalse(E.is_contra("LONG", "none"))
        self.assertFalse(E.is_contra("SHORT", "none"))


if __name__ == "__main__":
    unittest.main()
