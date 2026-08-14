.PHONY: demo demo-live test verify-scopes verify-manifest metrics lint-coverage check-docs compliance \
        recording-prep recording-reset ledger-count red-team buyer-client deployment-status deployment-status-check

demo:
	HODI_OFFLINE=1 python3 scripts/demo.py

# The five-attack red-team drill (HOD-712). Credential-free, offline, and
# every boundary that yields exits nonzero — so it runs in CI as a guard, not
# just as a demo.
red-team:
	HODI_OFFLINE=1 python3 scripts/red_team.py

# A buyer-side system that verifies receipts with Hodi's PUBLIC key and stops
# when the artist revokes (HOD-719). The evidence that a counterparty honours
# the rail, not just that Hodi records it.
buyer-client:
	HODI_OFFLINE=1 python3 scripts/buyer_client.py

test:
	HODI_OFFLINE=1 python3 -m unittest discover -s tests

demo-live:
	time python3 scripts/test_live_cross_counterparty.py

verify-scopes:
	python3 scripts/verify_scopes.py

verify-manifest:
	python3 scripts/verify_manifest.py

metrics:
	python3 scripts/daily_accrual_check.py --write-metrics

lint-coverage:
	python3 scripts/measure_lint_coverage.py

check-docs:
	python3 scripts/check_doc_metrics.py

# Deployment truth, derived (HOD-715). No argument renders the table the docs
# embed; --check validates the file's own rules (a 'verified' capability must
# name its evidence AND its date; a 'never run' one must not carry a date).
deployment-status:
	python3 scripts/deployment_status.py

deployment-status-check:
	python3 scripts/deployment_status.py --check

compliance:
	python3 scripts/compliance.py
	python3 scripts/count_defect_ledger.py --check
	python3 scripts/deployment_status.py --check
	python3 scripts/check_doc_metrics.py

ledger-count:
	python3 scripts/count_defect_ledger.py --write-metrics

# The ONE reproducible deployment path. Deploying by hand is how the runtime
# identity gets lost: without --service-account the service silently reverts to
# the default compute SA (roles/editor), which can update and delete grant
# events, and the append-only invariant becomes false at runtime with nothing
# failing. This target provisions IAM, deploys, and then PROVES the deployed
# identity cannot rewrite history before reporting success.
deploy:
	./scripts/deploy.sh

# Recording state (docs/VIDEO-SCRIPT.md). Both write to LIVE Firestore grants —
# appends only, never the works collection.
recording-prep:
	python3 scripts/prepare_recording.py

recording-reset:
	python3 scripts/prepare_recording.py --between-takes
