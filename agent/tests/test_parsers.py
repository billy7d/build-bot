import unittest
from pathlib import Path

from agent.data.episodes.builder import build_bundle
from agent.data.parsers import v81_stddev, v82_blocked_signal


FIXTURES = Path(__file__).parent / "fixtures"


class ParserTests(unittest.TestCase):
    def test_v81_feature_mapping_and_flat_candidate(self):
        events = v81_stddev.parse(FIXTURES / "v81_sample.csv", source_key="fixture-v81", source_timezone="UTC")
        self.assertEqual(len(events), 1)
        bundle = build_bundle(events[0], source_artifact_id=1, experiment_id="V81-2025", preset_id="p", ordinal=1)
        self.assertEqual(bundle.episode["episode_kind"], "FLAT_CANDIDATE")
        self.assertEqual(bundle.features["return_std_rank"], 80.0)
        self.assertEqual(bundle.features["spread_r"], 0.2)
        self.assertEqual(bundle.outcome["forward_return_24h"], 0.3)

    def test_v82_epoch_and_opportunity_mapping(self):
        events = v82_blocked_signal.parse(FIXTURES / "v82_sample.csv", source_key="fixture-v82", source_timezone="UTC")
        self.assertEqual(events[0].event_time_utc, "2025-01-01T00:00:00Z")
        bundle = build_bundle(events[0], source_artifact_id=1, experiment_id="V82-2025", preset_id="p", ordinal=1)
        self.assertEqual(bundle.episode["episode_kind"], "BLOCKED_OPPORTUNITY")
        self.assertEqual(bundle.opportunity_context["blocked_side"], "SHORT")
        self.assertEqual(bundle.opportunity_outcome["shadow_return_48bar_r"], 0.5)
        self.assertEqual(bundle.features["spread_r"], 0.3)


if __name__ == "__main__":
    unittest.main()
