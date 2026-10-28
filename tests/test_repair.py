import unittest

from dreamteam.errors import AuthorizationError, PolicyViolation
from dreamteam.ledger import Ledger
from dreamteam.repair import Approval, Incident, MockEnvironment, RepairTeam


class TestRepair(unittest.TestCase):
    def _team(self) -> RepairTeam:
        return RepairTeam(Ledger())

    def test_r1_repair_recovers(self):
        team, env = self._team(), MockEnvironment({"svc": True})
        inc = Incident("i1", "mock", "down")
        team.diagnose(inc, env, ["svc"])
        team.plan_repair(inc, [{"name": "svc", "risk": "R1"}])
        team.apply_repair(inc, env, executor="exec")
        state = team.verify(inc, env, ["svc"], verifier="ver", executor="exec")
        self.assertEqual(state, "RECOVERED")

    def test_r2_requires_approval(self):
        team, env = self._team(), MockEnvironment({"svc": True})
        inc = Incident("i1", "mock", "down")
        team.diagnose(inc, env, ["svc"])
        team.plan_repair(inc, [{"name": "svc", "risk": "R2"}])
        with self.assertRaises(AuthorizationError):
            team.apply_repair(inc, env, executor="exec")
        self.assertEqual(inc.state, "AWAITING_APPROVAL")
        team.apply_repair(inc, env, executor="exec",
                          approval=Approval("ap-1", "lead", "fix svc"))
        state = team.verify(inc, env, ["svc"], verifier="ver", executor="exec")
        self.assertEqual(state, "RECOVERED")

    def test_verifier_must_differ_from_executor(self):
        team, env = self._team(), MockEnvironment({"svc": True})
        inc = Incident("i1", "mock", "down")
        team.diagnose(inc, env, ["svc"])
        team.plan_repair(inc, [{"name": "svc", "risk": "R1"}])
        team.apply_repair(inc, env, executor="same")
        with self.assertRaises(PolicyViolation):
            team.verify(inc, env, ["svc"], verifier="same", executor="same")

    def test_unrepaired_incident_not_recovered(self):
        team, env = self._team(), MockEnvironment({"svc": True})
        inc = Incident("i1", "mock", "down")
        team.diagnose(inc, env, ["svc"])
        team.plan_repair(inc, [{"name": "other", "risk": "R1"}])
        team.apply_repair(inc, env, executor="exec")
        state = team.verify(inc, env, ["svc"], verifier="ver", executor="exec")
        self.assertEqual(state, "FAILED_OR_ROLLED_BACK")


if __name__ == "__main__":
    unittest.main()
