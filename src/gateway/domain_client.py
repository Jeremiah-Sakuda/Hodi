"""
src/gateway/domain_client.py — the front door asks a domain service; it does not
read the domain itself (HOD-733).

WHAT THIS MAKES TRUE. Until now the conflict boundary between the custodian, the
negotiator, the evidence agent and the arbiter was enforced by `AgentGateway`
inside ONE process running as ONE service account. The policy was real and
tested, but a bug in that process could reach any domain's data, because the
process held credentials for all of them. `docs/deployment_status.json` said so:
`conflict_domain_separation: in_process_only`.

With a domain service deployed per role, the front door's service account holds
NO grant on any domain database. It cannot read `works`, and not because a
policy table says no — because Google IAM will refuse it. To get identity data
it must ask the rights-custodian service, which runs as
`rights-custodian-sa`, is scoped by IAM condition to `hodi-identity`, and
re-checks policy locally before doing anything. A compromised front door can ask
the wrong question; it cannot obtain the wrong answer.

WHY THE CALLEE RE-CHECKS. The remote call carries a `role`, and a caller could
lie about it. So each domain service pins its role from its OWN environment
(`HODI_SERVICE_ROLE`) and refuses any request naming a different one. The role a
request executes under is therefore a property of which service answered, which
is a property of which service account Cloud Run started it with — not a field
in a body. This is the same correction made to `counterparty_id` after the
cross-buyer breach: identity comes from the credential, never from the payload.

DEFAULT OFF. With `HODI_DOMAIN_SERVICE_URLS` unset the gateway behaves exactly
as before, in-process. `make demo` stays credential-free, the offline suite is
untouched, and the split is something a deployment turns on rather than
something the code assumes.
"""

import json
import os
from typing import Any, Dict, List, Optional

# How long a domain call may take before the front door gives up. Bounded
# because a licensing decision must not hang on a cold domain service; the
# caller surfaces the failure rather than falling back to a local read, which
# would silently re-monolith the system under load.
DOMAIN_CALL_TIMEOUT_SECONDS = 30.0

ENV_SERVICE_URLS = "HODI_DOMAIN_SERVICE_URLS"
ENV_SERVICE_ROLE = "HODI_SERVICE_ROLE"


class DomainServiceUnavailable(RuntimeError):
    """A domain service could not be reached or refused the call."""


def service_urls() -> Dict[str, str]:
    """
    {role: url} from the environment, or {} when the split is not deployed.

    Accepts either JSON or `role=url|role=url`. The pipe form exists because
    `gcloud run deploy --update-env-vars` splits values on COMMAS, and a JSON
    object is nothing but commas — the first version of the deploy produced a
    truncated value that parsed to {} and silently disabled delegation, which
    would have left four domain services deployed and never called. Neither
    roles nor Cloud Run URLs can contain `|` or `=` in a position that breaks
    this, so the pipe form needs no escaping at all.
    """
    raw = os.environ.get(ENV_SERVICE_URLS, "").strip()
    if not raw:
        return {}
    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
            return {str(k): str(v) for k, v in parsed.items() if v}
        except Exception:
            return {}
    out: Dict[str, str] = {}
    for pair in raw.split("|"):
        role, sep, url = pair.partition("=")
        if sep and role.strip() and url.strip():
            out[role.strip()] = url.strip()
    return out


def this_service_role() -> Optional[str]:
    """
    The role THIS process is, if it is a domain service.

    Set only by scripts/deploy_domain_services.sh. Its presence is also what
    stops a domain service from proxying onward: a custodian service asked for
    identity data must read its own database, not call itself forever.
    """
    return os.environ.get(ENV_SERVICE_ROLE) or None


def _id_token(audience: str) -> str:
    """
    A Google-signed ID token for `audience`, minted from the ambient identity.

    Cloud Run's own IAM checks this token before our code runs, so the front
    door must additionally hold `roles/run.invoker` on each domain service —
    provisioned by the deploy script and asserted there, not assumed here.
    """
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token
    return google_id_token.fetch_id_token(google_requests.Request(), audience)


def _post(url: str, path: str, body: Dict[str, Any]) -> Any:
    import urllib.error
    import urllib.request

    payload = json.dumps(body).encode("utf-8")
    try:
        token = _id_token(url)
    except Exception as e:  # noqa: BLE001
        raise DomainServiceUnavailable(
            f"could not mint an ID token for {url}: {type(e).__name__}: {e}") from e

    req = urllib.request.Request(url.rstrip("/") + path, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    })
    try:
        with urllib.request.urlopen(req, timeout=DOMAIN_CALL_TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        # A 403 from a domain service is a POLICY answer and must surface as
        # one — never be swallowed into an empty result, which would read as
        # "there is no such data" instead of "you may not have it".
        raise DomainServiceUnavailable(
            f"{path} on {url} refused with HTTP {e.code}: {detail}") from e
    except Exception as e:  # noqa: BLE001
        raise DomainServiceUnavailable(
            f"{path} on {url} failed: {type(e).__name__}: {e}") from e


class DomainServiceClient:
    """Remote half of the gateway: one HTTPS hop per domain operation."""

    def __init__(self, urls: Optional[Dict[str, str]] = None):
        self._urls = urls if urls is not None else service_urls()

    def handles(self, role: str) -> bool:
        """
        True when this role is served by a separate deployed workload.

        False under HODI_OFFLINE no matter what is configured: a declared
        credential-free run must not open a socket, and `make demo` is the
        proof a judge runs first. A test that wants the real path injects a
        client into AgentGateway instead of relying on the environment.
        """
        if os.environ.get("HODI_OFFLINE") == "1":
            return False
        return role in self._urls and this_service_role() is None

    def read(self, role: str, collection: str, filters: Optional[Dict[str, Any]],
             session_context: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = _post(self._urls[role], "/internal/domain/read", {
            "role": role, "collection": collection,
            "filters": filters, "session_context": session_context,
        })
        return out.get("documents", [])

    def write(self, role: str, collection: str, doc_id: str,
              data: Dict[str, Any]) -> None:
        _post(self._urls[role], "/internal/domain/write", {
            "role": role, "collection": collection, "doc_id": doc_id, "data": data,
        })
