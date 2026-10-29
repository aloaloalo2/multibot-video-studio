import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent_estimate
import store


class AgentEstimateTest(unittest.TestCase):
    def test_estimates_images_and_agent_separately_and_keeps_unknown_costs(self):
        plan = {"frames": [{"format": "stock_video"}, {"format": "generated_photo"}, {"format": "generated_photo"}, {"format": "generated_video"}]}
        prices = {"token_rates": [(0.000001, 0.000002), (0.000002, 0.000004)], "image_rate": .01}
        costs = {"messages": [], "costs": [{"amount_usd": .05}, {"amount_usd": None}]}
        with patch.object(agent_estimate.store, "load_project_plan", return_value=plan), patch.object(agent_estimate.agent_storage, "get_conversation", return_value=costs):
            result = agent_estimate.estimate("test", prices)
        self.assertEqual(result["image_count"], 2)
        self.assertEqual(result["generated_video_count"], 1)
        self.assertAlmostEqual(result["images_usd"], .02)
        self.assertAlmostEqual(result["agent_min_usd"], .0044)
        self.assertAlmostEqual(result["agent_max_usd"], .0088)
        self.assertAlmostEqual(result["subtotal_min_usd"], .0244)
        self.assertEqual(result["actual"]["known_total_usd"], .05)
        self.assertEqual(result["actual"]["unknown_count"], 1)

    def test_plan_is_required(self):
        with patch.object(agent_estimate.store, "load_project_plan", return_value=None):
            with self.assertRaises(store.StudioError):
                agent_estimate.estimate("test", {"token_rates": [(1, 1)], "image_rate": 1})

    def test_unavailable_prices_do_not_produce_zero_estimate(self):
        with patch.object(agent_estimate, "_cached", None), patch.object(agent_estimate, "get_json", side_effect=OSError("offline")):
            with self.assertRaises(store.StudioError):
                agent_estimate.rates()


if __name__ == "__main__":
    unittest.main()
