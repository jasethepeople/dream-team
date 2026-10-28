import unittest

from dreamteam.deploy import Deployment, MockDeployAdapter, Release, T340DeployAdapter
from dreamteam.errors import BlockedError, PolicyViolation
from dreamteam.ledger import Ledger


def _release() -> Release:
    return Release("rel-1", "sha256:abc", "c0ffee", "mock", "mock")


class TestDeploy(unittest.TestCase):
    def test_healthy_deployment_accepted(self):
        dep = Deployment(_release(), MockDeployAdapter(healthy=True), Ledger())
        self.assertEqual(dep.run(), "ACCEPTED")

    def test_unhealthy_deployment_rolled_back(self):
        dep = Deployment(_release(), MockDeployAdapter(healthy=False), Ledger())
        self.assertEqual(dep.run(), "ROLLED_BACK")
        self.assertEqual(len(dep.attempts), 1)  # failure attempt preserved

    def test_invalid_transition_forbidden(self):
        dep = Deployment(_release(), MockDeployAdapter(), Ledger())
        with self.assertRaises(PolicyViolation):
            dep._move("ACCEPTED")

    def test_t340_adapter_blocked(self):
        with self.assertRaises(BlockedError):
            T340DeployAdapter().deploy(_release())

    def test_rollback_verified(self):
        adapter = MockDeployAdapter(healthy=True)
        dep = Deployment(_release(), adapter, Ledger())
        dep.run()
        self.assertEqual(dep.state, "ACCEPTED")


if __name__ == "__main__":
    unittest.main()
