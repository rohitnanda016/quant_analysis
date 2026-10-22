import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.nse_action_payload_archive import archive_http_response, write_manifest


class FakeResponse:
    def __init__(self, body, status_code=200, content_type="application/json"):
        self.content = body
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}
        self.url = "https://www.nseindia.com/api/corporates-corporateActions?index=equities"
        self.text = body.decode("utf-8", errors="replace")


class NSEActionPayloadArchiveTests(unittest.TestCase):
    def test_archives_exact_body_with_hash_before_parsing(self):
        body = b'{"data":[{"symbol":"TATACHEM","exDate":"04-Mar-2020"}]}'
        with tempfile.TemporaryDirectory() as directory:
            record = archive_http_response(
                FakeResponse(body), directory, 1, "2020-03-01", "2020-03-31",
                1, requested_at_utc="2026-10-20T14:00:00+00:00"
            )
            stored = Path(directory) / record["response_body_file"]
            sidecar = json.loads((Path(directory) / record["metadata_file"]).read_text())
            self.assertEqual(stored.read_bytes(), body)
            self.assertEqual(record["response_body_sha256"], hashlib.sha256(body).hexdigest())
            self.assertEqual(sidecar["response_body_sha256"], record["response_body_sha256"])
            self.assertEqual(record["http_status"], 200)

    def test_archives_non_200_body_for_failure_diagnostics(self):
        body = b"<html>temporary rejection</html>"
        with tempfile.TemporaryDirectory() as directory:
            record = archive_http_response(
                FakeResponse(body, 403, "text/html"), directory, 2,
                "2021-01-01", "2021-03-31", 1
            )
            self.assertTrue(record["response_body_file"].endswith(".body"))
            self.assertEqual((Path(directory) / record["response_body_file"]).read_bytes(), body)
            self.assertEqual(record["http_status"], 403)

    def test_manifest_records_response_hashes_and_completion_state(self):
        body = b'{"data":[]}'
        with tempfile.TemporaryDirectory() as directory:
            record = archive_http_response(
                FakeResponse(body), directory, 1, "2014-01-01", "2014-03-31", 1
            )
            manifest_path = Path(write_manifest(
                directory, [record], False,
                "https://www.nseindia.com/api/corporates-corporateActions",
                "2014-01-01", "2026-08-31"
            ))
            manifest = json.loads(manifest_path.read_text())
            self.assertFalse(manifest["retrieval_complete"])
            self.assertEqual(manifest["response_attempt_count"], 1)
            self.assertEqual(manifest["successful_http_200_count"], 1)
            self.assertEqual(manifest["responses"][0]["response_body_sha256"], record["response_body_sha256"])


if __name__ == "__main__":
    unittest.main()
