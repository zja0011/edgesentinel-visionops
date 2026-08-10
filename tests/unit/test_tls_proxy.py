import os
import stat
import tempfile
import unittest
from unittest import mock

from apps.tls_proxy import filtered_headers, validate_tls_file


class TlsProxyTests(unittest.TestCase):
    def test_filters_hop_by_hop_and_spoofed_forwarding_headers(self):
        headers = filtered_headers(
            [
                ("Accept", "application/json"),
                ("Connection", "keep-alive"),
                ("Transfer-Encoding", "chunked"),
                ("X-Forwarded-Proto", "http"),
                ("X-Forwarded-For", "attacker"),
                ("Server", "upstream-version"),
                ("Cookie", "redacted-at-transport"),
            ]
        )
        names = [name.lower() for name, unused in headers]

        self.assertIn("accept", names)
        self.assertIn("cookie", names)
        self.assertNotIn("connection", names)
        self.assertNotIn("transfer-encoding", names)
        self.assertNotIn("x-forwarded-proto", names)
        self.assertNotIn("x-forwarded-for", names)

        response_names = [
            name.lower()
            for name, unused in filtered_headers(
                [("Server", "upstream"), ("Content-Type", "text/plain")],
                response=True,
            )
        ]
        self.assertNotIn("server", response_names)
        self.assertIn("content-type", response_names)

    def test_private_key_must_be_regular_and_owner_only(self):
        metadata = mock.Mock()
        metadata.st_mode = stat.S_IFREG | 0o600
        metadata.st_size = 128
        with mock.patch("apps.tls_proxy.os.lstat", return_value=metadata):
            self.assertEqual(
                validate_tls_file("server.key", private=True),
                os.path.abspath("server.key"),
            )
            metadata.st_mode = stat.S_IFREG | 0o644
            with self.assertRaises(ValueError):
                validate_tls_file("server.key", private=True)

    def test_rejects_symlinked_key(self):
        with tempfile.TemporaryDirectory() as directory:
            target = os.path.join(directory, "target")
            link = os.path.join(directory, "link")
            with open(target, "wb") as output:
                output.write(b"key")
            try:
                os.symlink(target, link)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaises(ValueError):
                validate_tls_file(link, private=True)


if __name__ == "__main__":
    unittest.main()
