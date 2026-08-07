import subprocess
from datetime import datetime, timezone
from google.cloud import firestore
from google.oauth2 import credentials
from src.gateway.gateway import AgentGateway
from src.schema.scope import Scope
from src.schema.grant_event import GrantEvent
from src.schema.lattice import is_use_type_contained, is_model_class_contained

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

req_scope = Scope(
    use_type="fine_tuning",
    model_class="open_weights",
    derivative_retention=False,
    attribution_required=True,
    commercial=False,
    territory=["US"],
    valid_from=t0.isoformat()
)

gateway = AgentGateway()
raw_grants = gateway.read_collection(
    calling_sa="licensing-negotiator@hodi-2026.iam.gserviceaccount.com",
    calling_role_key="licensing_negotiator",
    target_collection="grants",
    filters={"counterparty_id": "buyer1-e2e-test"},
    session_context={"counterparty_id": "buyer1-e2e-test"}
)
active_grants = [GrantEvent(**g) for g in raw_grants]

grant = active_grants[0]
g_scope = grant.scope

requested_territories = set(req_scope.territory)
granted_territories = set(g_scope.territory)
print("REQUESTED TERR:", requested_territories)
print("GRANTED TERR:", granted_territories)
print("IS SUBSET:", requested_territories.issubset(granted_territories))
if "WW" not in g_scope.territory and not requested_territories.issubset(granted_territories):
    print("FAILED ON TERRITORY")

doc_ref.delete()
