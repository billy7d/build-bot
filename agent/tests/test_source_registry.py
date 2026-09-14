import unittest

from agent.data.source_registry import descriptor_for


class SourceRegistryTests(unittest.TestCase):
    def test_strategy_is_not_guessed_for_other_or_unversioned_artifacts(self):
        self.assertEqual(
            descriptor_for("outputs/presets/80_v63_forward_demo.set").strategy_version,
            "V63",
        )
        self.assertIsNone(
            descriptor_for("outputs/presets/77_v30_long_sleeve.set").strategy_version
        )
        self.assertIsNone(
            descriptor_for("outputs/forward_demo_runbook.md").strategy_version
        )


if __name__ == "__main__":
    unittest.main()
