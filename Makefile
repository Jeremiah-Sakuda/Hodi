.PHONY: demo demo-live test verify-scopes verify-manifest metrics compliance

demo:
	HODI_OFFLINE=1 python3 scripts/demo.py

test:
	HODI_OFFLINE=1 python3 -m unittest discover -s tests -t .

demo-live:
	time python3 scripts/test_live_cross_counterparty.py

verify-scopes:
	python3 scripts/verify_scopes.py

verify-manifest:
	python3 scripts/verify_manifest.py

metrics:
	python3 scripts/daily_accrual_check.py --write-metrics

compliance:
	python3 scripts/compliance.py
