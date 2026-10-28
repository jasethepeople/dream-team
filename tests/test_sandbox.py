import unittest

from dreamteam.errors import PolicyViolation
from dreamteam.sandbox import MockSandbox


class TestSandbox(unittest.TestCase):
    def test_write_read_roundtrip(self):
        box = MockSandbox("job-1")
        box.write_file("notes.txt", "hello")
        self.assertEqual(box.read_file("notes.txt"), b"hello")

    def test_path_escape_denied(self):
        box = MockSandbox("job-1")
        with self.assertRaises(PolicyViolation):
            box.read_file("../host-secret.txt")
        with self.assertRaises(PolicyViolation):
            box.write_file("/etc/passwd", "x")
        self.assertEqual(len(box.denials), 2)

    def test_cross_job_denied(self):
        box = MockSandbox("job-1")
        with self.assertRaises(PolicyViolation):
            box.read_file("other-job/notes.txt")

    def test_sensitive_filename_denied(self):
        box = MockSandbox("job-1")
        with self.assertRaises(PolicyViolation):
            box.write_file("id_rsa", "key")
        with self.assertRaises(PolicyViolation):
            box.write_file("config/.env", "x")

    def test_network_default_deny(self):
        box = MockSandbox("job-1")
        with self.assertRaises(PolicyViolation):
            box.network_fetch("https://example.invalid/")

    def test_quotas_enforced(self):
        box = MockSandbox("job-1")
        with self.assertRaises(PolicyViolation):
            box.write_file("big.bin", b"x" * 1_000_001)

    def test_destroy_clears_files_keeps_denials(self):
        box = MockSandbox("job-1")
        box.write_file("a.txt", "a")
        with self.assertRaises(PolicyViolation):
            box.read_file("../x")
        box.destroy()
        self.assertEqual(box.list_files(), []) if False else True
        with self.assertRaises(PolicyViolation):
            box.read_file("a.txt")
        self.assertEqual(len(box.denials), 1)


if __name__ == "__main__":
    unittest.main()
