import os
import unittest

from dreamteam.backends import (
    DockerMiddlewareBackend, MockBackend, StubBackend,
    backend_from_env, validate_job,
)
from dreamteam.errors import BlockedError

GOOD_JOB = {"job_id": "j1", "image": "python:3.12-slim",
            "argv": ["echo"], "timeout": 60, "network_policy": "none"}


class TestBackends(unittest.TestCase):
    def test_stub_reports_blocked(self):
        result = StubBackend().run(GOOD_JOB)
        self.assertEqual(result.status, "blocked")
        self.assertIn("no real backend", result.blocked_reason)

    def test_mock_runs_registered_handler_only(self):
        backend = MockBackend({"echo": lambda job: "hello"})
        result = backend.run(GOOD_JOB)
        self.assertEqual((result.status, result.output), ("completed", "hello"))
        self.assertEqual(backend.status("j1").status, "completed")

    def test_mock_unknown_handler_fails_closed(self):
        result = MockBackend().run(GOOD_JOB)
        self.assertEqual(result.status, "failed")

    def test_validate_job_rejects_bad_image(self):
        with self.assertRaises(ValueError):
            validate_job({**GOOD_JOB, "image": "evil:latest"})

    def test_validate_job_rejects_shell_string(self):
        with self.assertRaises(ValueError):
            validate_job({**GOOD_JOB, "argv": "echo hi"})

    def test_validate_job_rejects_long_timeout(self):
        with self.assertRaises(ValueError):
            validate_job({**GOOD_JOB, "timeout": 9999})

    def test_validate_job_rejects_privileged(self):
        with self.assertRaises(ValueError):
            validate_job({**GOOD_JOB, "privileged": True})

    def test_middleware_blocked_by_default(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("DREAMTEAM_T340_VERIFIED", "DREAMTEAM_T340_TOKEN")}
        old = dict(os.environ)
        try:
            os.environ.clear()
            os.environ.update(env)
            result = DockerMiddlewareBackend(base_url="http://127.0.0.1:9/").run(GOOD_JOB)
        finally:
            os.environ.clear()
            os.environ.update(old)
        self.assertEqual(result.status, "blocked")
        self.assertIn("not yet independently verified", result.blocked_reason)

    def test_backend_from_env_unknown_refuses(self):
        old = os.environ.get("BACKEND")
        os.environ["BACKEND"] = "mystery"
        try:
            with self.assertRaises(BlockedError):
                backend_from_env()
        finally:
            if old is None:
                del os.environ["BACKEND"]
            else:
                os.environ["BACKEND"] = old

    def test_backend_default_is_stub(self):
        old = os.environ.pop("BACKEND", None)
        try:
            self.assertIsInstance(backend_from_env(), StubBackend)
        finally:
            if old is not None:
                os.environ["BACKEND"] = old


if __name__ == "__main__":
    unittest.main()
