import subprocess
from datetime import datetime, timezone
from google.cloud import firestore
from google.oauth2 import credentials
from src.gateway.gateway import AgentGateway
from src.schema.scope import Scope
from src.schema.grant_event import GrantEvent
from src.agents.licensing_negotiator import LicensingNegotiatorAgent

t0 = datetime.now(timezone.utc)
active_grant = GrantEvent(
    event_id="e1-test-buyer", grant_id="g1-test-buyer", work_id="w1", counterparty_id="buyer1-e2e-test",
    scope=Scope(use_type="training", model_class="all_models", derivative_retention=True, attribution_required=True, commercial=True, valid_from=t0, valid_until=None),
    kind="granted", issued_at=t0, signature="sig1"
)
token = subprocess.check_output(['gcloud', 'auth', 'print-access-token']).decode('utf-8').strip()
creds = credentials.Credentials(token)
db = firestore.Client(project="hodi-2026", credentials=creds)

doc_ref = db.collection("grants").document("g1-test-buyer")
doc_ref.set(active_grant.model_dump(mode='json'))

gateway = AgentGateway()
docs = gateway.read_collection(
    calling_sa="licensing-negotiator@hodi-2026.iam.gserviceaccount.com",
    calling_role_key="licensing_negotiator",
    target_collection="grants",
    filters={"counterparty_id": "buyer1-e2e-test"},
    session_context={"counterparty_id": "buyer1-e2e-test"}
)

print("PARSED GRANTS:", [GrantEvent(**g) for g in docs])
doc_ref.delete()
