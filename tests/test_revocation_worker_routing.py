"""Private revocation-worker boundary tests (HOD-711)."""

import json
import unittest
from unittest.mock import MagicMock, patch

from src.gateway.revocation_client import (
    RevocationWorkerUnavailable,
    execute_revocation,
)


def _cascade(operation_id="operation-worker-1"):
    return {
        "operation_id": operation_id,
        "revoked_use_type": "training",
        "derived_scopes": [],
        "structured_derivation": [],
        "affected_grants": [],
        "issued_notices": [],
        "replayed_effects": 0,
    }


class TestPrivateRevocationClient(unittest.TestCase):
    def _response(self, body):
        response = MagicMock()
        response.read.return_value = json.dumps(body).encode("utf-8")
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        return response

    @patch("src.gateway.revocation_client._id_token", return_value="oidc-token")
    @patch("src.gateway.revocation_client.urllib.request.urlopen")
    def test_requires_and_parses_private_worker_attestation(self, urlopen, _token):
        urlopen.return_value = self._response({
            "execution_surface": "private-revocation-worker",
            "result": _cascade(),
        })

        result = execute_revocation(
            "https://worker.example", work_id="work-1",
            revoked_use_type="training", operation_id="operation-worker-1")

        self.assertEqual(result.operation_id, "operation-worker-1")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url,
                         "https://worker.example/internal/revocation/execute")
        self.assertEqual(request.get_header("Authorization"), "Bearer oidc-token")

    @patch("src.gateway.revocation_client._id_token", return_value="oidc-token")
    @patch("src.gateway.revocation_client.urllib.request.urlopen")
    def test_an_unmarked_200_fails_closed(self, urlopen, _token):
        urlopen.return_value = self._response({"result": _cascade()})
        with self.assertRaisesRegex(RevocationWorkerUnavailable,
                                   "execution-surface attestation"):
            execute_revocation(
                "https://worker.example", work_id="work-1",
                revoked_use_type="training", operation_id="operation-worker-1")

    @patch("src.gateway.revocation_client._id_token", return_value="oidc-token")
    @patch("src.gateway.revocation_client.urllib.request.urlopen")
    def test_malformed_remote_cascade_fails_closed(self, urlopen, _token):
        urlopen.return_value = self._response({
            "execution_surface": "private-revocation-worker",
            "result": {"operation_id": "missing-required-fields"},
        })
        with self.assertRaisesRegex(RevocationWorkerUnavailable, "invalid cascade"):
            execute_revocation(
                "https://worker.example", work_id="work-1",
                revoked_use_type="training", operation_id=None)


if __name__ == "__main__":
    unittest.main()
