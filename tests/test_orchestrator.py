import unittest

from dreamteam.errors import AuthorizationError, PolicyViolation
from dreamteam.ledger import Ledger
from dreamteam.orchestrator import Orchestrator, Play, RunConfig


class TestOrchestrator(unittest.TestCase):
    def test_plan_only_creates_no_patches(self):
        result = Orchestrator(Ledger()).run(
            RunConfig("goal", ["own-repo"], autonomy="plan_only"))
        self.assertEqual(result["detail"]["IMPLEMENT"]["patches"], 0)
        self.assertFalse(result["detail"]["DELIVER"]["push_performed"])

    def test_implement_with_review_creates_patch_records(self):
        result = Orchestrator(Ledger()).run(
            RunConfig("goal", ["own-repo"], autonomy="implement_with_review"))
        self.assertEqual(result["detail"]["IMPLEMENT"]["patches"], 1)
        self.assertFalse(result["detail"]["DELIVER"]["push_performed"])

    def test_no_push_method_exists(self):
        self.assertFalse(hasattr(Orchestrator(Ledger()), "push"))
        self.assertFalse(hasattr(Orchestrator(Ledger()), "commit"))

    def test_repository_bounds(self):
        with self.assertRaises(PolicyViolation):
            RunConfig("goal", [])
        with self.assertRaises(PolicyViolation):
            RunConfig("goal", [f"r{i}" for i in range(26)])

    def test_automated_steps_require_approval(self):
        with self.assertRaises(AuthorizationError):
            RunConfig("goal", ["r"], autonomy="automated_approved_steps")
        RunConfig("goal", ["r"], autonomy="automated_approved_steps",
                  approval_id="ap-1")

    def test_play_promotion_needs_evidence_and_reviewer(self):
        orch = Orchestrator(Ledger())
        play = Play("p1", "trigger", "procedure")
        orch.add_play(play)
        with self.assertRaises(PolicyViolation):
            play.promote("VALIDATED", reviewer="author", author="author")
        play.evidence.append("build-1")
        with self.assertRaises(PolicyViolation):
            play.promote("VALIDATED", reviewer="author", author="author")
        play.promote("VALIDATED", reviewer="reviewer", author="author")
        self.assertEqual(play.state, "VALIDATED")

    def test_pipeline_stages_complete(self):
        result = Orchestrator(Ledger()).run(RunConfig("goal", ["own-repo"]))
        self.assertEqual(result["stages"],
                         ["DISCOVER", "SPECIFY", "PLAN", "IMPLEMENT",
                          "CHALLENGE", "VERIFY", "DELIVER", "LEARN"])


if __name__ == "__main__":
    unittest.main()
