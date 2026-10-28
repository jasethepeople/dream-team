import unittest

from dreamteam.anvil import Authorization
from dreamteam.engine import (
    Engine, Intent, OperatorCredentials, self_repair_own_parser,
)
from dreamteam.errors import AuthorizationError
from dreamteam.sandbox import MockSandbox


def _intent(**overrides):
    base = dict(goal="read rows", target="own-system",
                authorization=Authorization("auth-1", "own-system", "read", "lead"),
                success_criteria=["rows_read"])
    base.update(overrides)
    return Intent(**base)


class TestEngine(unittest.TestCase):
    def _engine(self) -> Engine:
        engine = Engine(MockSandbox("eng-1"))
        engine.registry.register("mock-store", ["read"], needs_auth=True)
        return engine

    def test_intent_requires_authorization(self):
        with self.assertRaises(AuthorizationError):
            _intent(authorization=Authorization("", "t", "s", ""))

    def test_missing_credentials_stops_at_manual_assist(self):
        result = self._engine().run(_intent(), OperatorCredentials(supplied=False))
        self.assertEqual(result["status"], "manual_assist")

    def test_no_credentials_supplied_at_all_stops(self):
        result = self._engine().run(_intent(), None)
        self.assertEqual(result["status"], "manual_assist")

    def test_supplied_credentials_prove_run(self):
        result = self._engine().run(_intent(), OperatorCredentials(supplied=True))
        self.assertEqual(result["status"], "proven")

    def test_no_credential_guessing_api_exists(self):
        # The re-scope deletes guessing: no such method may exist anywhere
        # on the engine or the connector registry.
        engine = self._engine()
        for obj in (engine, engine.registry):
            for name in dir(obj):
                self.assertNotIn("guess", name.lower())
        self.assertFalse(hasattr(engine.registry, "guess_credentials"))
        self.assertFalse(hasattr(engine, "guess"))

    def test_no_goal_autonomy_api_exists(self):
        engine = self._engine()
        for name in dir(engine):
            self.assertNotIn("autonom", name.lower())
            self.assertNotIn("spawn_engagement", name.lower())
        self.assertFalse(hasattr(engine, "spawn_engagement"))

    def test_consequential_run_requires_approval(self):
        with self.assertRaises(AuthorizationError):
            self._engine().run(_intent(read_only=False), OperatorCredentials(True))

    def test_self_repair_only_own_parser(self):
        self.assertTrue(self_repair_own_parser(lambda s: s.upper(), ["a"], ["A"]))
        self.assertFalse(self_repair_own_parser(lambda s: s.upper(), ["a"], ["b"]))


if __name__ == "__main__":
    unittest.main()
