import copy
import importlib.util
import json
import unittest
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("loot_odds", ROOT / "tools/loot_odds.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MonsteyLootOddsTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / "examples/loot-pools.json").read_text(encoding="utf-8"))

    def test_branch_share_is_divided_between_members(self):
        out = MODULE.Monstey_distribution(self.data)
        self.assertEqual(out["existing_reward_group"], Fraction(9, 10))
        self.assertEqual(out["Example_EmberSword"], Fraction(1, 30))
        self.assertEqual(sum(out.values()), 1)

    def test_more_items_do_not_increase_branch_share(self):
        self.data["pools"]["imported_swords"].append({"item": "Example_FourthSword", "weight": 1})
        out = MODULE.Monstey_distribution(self.data)
        self.assertEqual(out["Example_EmberSword"], Fraction(1, 40))
        self.assertEqual(out["existing_reward_group"], Fraction(9, 10))

    def test_same_leaf_through_multiple_branches_accumulates(self):
        self.data["pools"]["reward"] = [
            {"pool": "imported_swords", "weight": 1},
            {"item": "Example_EmberSword", "weight": 1},
        ]
        out = MODULE.Monstey_distribution(self.data)
        self.assertEqual(out["Example_EmberSword"], Fraction(2, 3))
        self.assertEqual(sum(out.values()), 1)

    def test_root_override_is_conditional(self):
        out = MODULE.Monstey_distribution(self.data, "imported_swords")
        self.assertEqual(out["Example_EmberSword"], Fraction(1, 3))

    def test_rejects_cycles_even_on_zero_weight_edges(self):
        self.data["pools"]["imported_swords"].append({"pool": "reward", "weight": 0})
        with self.assertRaisesRegex(ValueError, "Cycle"):
            MODULE.Monstey_distribution(self.data)

    def test_rejects_missing_target_and_ambiguous_edge(self):
        for replacement in (
            {"pool": "missing", "weight": 1},
            {"item": "a", "pool": "imported_swords", "weight": 1},
        ):
            with self.subTest(replacement=replacement):
                data = copy.deepcopy(self.data)
                data["pools"]["reward"] = [replacement]
                with self.assertRaises(ValueError):
                    MODULE.Monstey_distribution(data)

    def test_rejects_invalid_weights(self):
        for value in (-1, True, "1", None, float("nan"), float("inf")):
            with self.subTest(value=value):
                data = copy.deepcopy(self.data)
                data["pools"]["reward"][0]["weight"] = value
                with self.assertRaises(ValueError):
                    MODULE.Monstey_distribution(data)

    def test_rejects_all_zero_pool(self):
        self.data["pools"]["reward"] = [{"item": "zero", "weight": 0}]
        with self.assertRaisesRegex(ValueError, "positive"):
            MODULE.Monstey_distribution(self.data)

    def test_duplicate_json_keys_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            json.loads('{"root":"a","root":"b"}', object_pairs_hook=MODULE.Monstey_unique_object)


if __name__ == "__main__":
    unittest.main()
