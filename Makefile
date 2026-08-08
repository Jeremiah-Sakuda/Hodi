.PHONY: demo demo-live test verify-scopes verify-manifest metrics lint-coverage check-docs compliance

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
	python3 scripts/check_doc_metrics.py
