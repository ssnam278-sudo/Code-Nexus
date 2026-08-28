"""Offline tests for DEM terrain metrics and the landslide inventory index."""

import unittest

from backend.landslide_inventory import INVENTORY, history_index
from backend.terrain import GRID_RADIUS, terrain_indices, terrain_metrics


def _flat_grid(value=100.0):
    side = 2 * GRID_RADIUS + 1
    return [value] * (side * side)


def _tilted_grid(rise_per_cell=40.0):
    """Elevation increasing west->east: a uniform slope."""
    side = 2 * GRID_RADIUS + 1
    return [col * rise_per_cell for _ in range(side) for col in range(side)]


class TerrainMetricTests(unittest.TestCase):
    def test_flat_ground_is_low_everything(self):
        m = terrain_metrics(26.0, _flat_grid())
        self.assertAlmostEqual(m["slope_deg"], 0.0, places=3)
        self.assertEqual(m["local_relief_m"], 0.0)
        i = terrain_indices(m)
        self.assertLess(i["slope"], 5)
        self.assertLess(i["susceptibility"], 10)

    def test_tilted_ground_has_slope_and_relief(self):
        m = terrain_metrics(26.0, _tilted_grid(120.0))
        self.assertGreater(m["slope_deg"], 3)
        self.assertGreater(m["local_relief_m"], 0)
        i = terrain_indices(m)
        self.assertGreater(i["slope"], 3)
        self.assertLessEqual(i["slope"], 100)
        self.assertLessEqual(i["susceptibility"], 100)

    def test_indices_are_bounded(self):
        m = terrain_metrics(26.0, _tilted_grid(400.0))   # absurdly steep
        i = terrain_indices(m)
        self.assertLessEqual(i["slope"], 100)
        self.assertLessEqual(i["susceptibility"], 100)


class InventoryTests(unittest.TestCase):
    def test_inventory_entries_are_well_formed(self):
        for ev in INVENTORY:
            self.assertTrue(-90 <= ev["lat"] <= 90 and 60 <= ev["lon"] <= 100)
            self.assertRegex(ev["date"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertIn("source", ev)

    def test_on_a_known_event_scores_higher_than_far_away(self):
        near = history_index(24.68, 93.66)["history"]      # on Tupul
        far = history_index(15.0, 78.0)["history"]         # peninsular India
        self.assertGreater(near, far)
        self.assertEqual(far, 0.0)

    def test_score_is_bounded_and_lists_nearby(self):
        r = history_index(25.30, 91.70)                    # Sohra
        self.assertGreaterEqual(r["history"], 0.0)
        self.assertLessEqual(r["history"], 100.0)
        self.assertGreater(r["events_within_range"], 0)
        self.assertTrue(r["nearby_events"])


if __name__ == "__main__":
    unittest.main()
