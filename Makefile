.PHONY: demo demo-live test verify-scopes verify-manifest metrics lint-coverage check-docs compliance \
        recording-prep recording-reset ledger-count

demo:
	HODI_OFFLINE=1 python3 scripts/demo.py

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

compliance:
	python3 scripts/compliance.py
	python3 scripts/count_defect_ledger.py --check
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
