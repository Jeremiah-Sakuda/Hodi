import os
import sys
from datetime import datetime, timezone

# Add the project root to the path so we can import src modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.cloud import firestore
from src.schema.grant_event import GrantEvent, Scope
from src.schema.signing import unsigned_placeholder

def seed_firestore():
    project_id = os.environ.get("GCP_PROJECT_ID", "hodi-2026")
    print(f"Connecting to Firestore project: {project_id}")
    db = firestore.Client(project=project_id)
    
    t0 = datetime.now(timezone.utc)
    
    # The five corpus works
    works = [
        {"work_id": "work-essay-001", "artist_id": "artist-jeremiah", "control_tier": "asserted"},
        {"work_id": "work-repo-001", "artist_id": "artist-jeremiah", "control_tier": "verified_control"},
        {"work_id": "work-audio-001", "artist_id": "artist-jeremiah", "control_tier": "asserted"},
        {"work_id": "work-essay-002", "artist_id": "artist-jeremiah", "control_tier": "asserted"},
        {"work_id": "work-audio-002", "artist_id": "artist-jeremiah", "control_tier": "asserted"}
    ]
    
    # 1. Seed works collection
    print("Seeding works...")
    batch = db.batch()
    for w in works:
        doc_ref = db.collection("works").document(w["work_id"])
        batch.set(doc_ref, w)
    
    # 2. Seed grants collection (1 active training grant per work)
    print("Seeding grants...")
    for idx, w in enumerate(works):
        work_id = w["work_id"]
        grant_id = f"grant-seed-{idx+1}"
        event_id = f"event-seed-{idx+1}"
        
        event = GrantEvent(
            event_id=event_id,
            grant_id=grant_id,
            work_id=work_id,
            counterparty_id=f"buyer-acme-{idx+1}",
            scope=Scope(
                use_type="training",
                model_class="all_models",
                derivative_retention=True,
                attribution_required=True,
                commercial=True,
                valid_from=t0,
                valid_until=None
            ),
            kind="granted",
            issued_at=t0,
            signature=unsigned_placeholder("grant", grant_id)
        )
        
        doc_ref = db.collection("grants").document(event_id)
        # Using model_dump() per Pydantic v2 guidelines
        batch.set(doc_ref, event.model_dump())
        
    batch.commit()
    print("Firestore seeding complete.")

if __name__ == "__main__":
    seed_firestore()
