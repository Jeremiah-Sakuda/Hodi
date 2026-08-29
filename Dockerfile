FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY src/evidence_service/requirements.txt src/evidence_service/requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY src/ /app/src/
# fixtures/ carries the committed Gemini response cache and the demo grant log.
# It was omitted, so the deployed service ran with an EMPTY response cache —
# every interpretation went to Vertex even when a recorded answer existed — and
# the failure-tolerance drill could not read its fixture events at all.
COPY fixtures/ /app/fixtures/
# The committed, dated crawler audit — /metrics-snapshot serves this file so no
# live page hard-codes an audit figure. Without it the route answers 503.
COPY docs/metrics.json /app/docs/metrics.json

ENV PYTHONPATH=/app

EXPOSE 8080

CMD ["uvicorn", "src.evidence_service.main:app", "--host", "0.0.0.0", "--port", "8080"]

# This is the ONLY Dockerfile that builds the deployed service. A stale copy
# lived at src/evidence_service/Dockerfile until 2026-08-12: it installed from
# requirements.txt instead of the lockfile and omitted `COPY fixtures/`, whose
# absence had already shipped once — the deployed service ran with an empty
# Gemini response cache and the failure-tolerance drill 500'd because it could
# not read its fixture events. Deploying from that path reintroduced a fixed
# defect, so it was deleted rather than kept in sync. `make deploy` builds this
# file from the repository root; src/harness/Dockerfile is a separate artifact
# for the HOD-020 Cloud Run Job and does not build the service.
