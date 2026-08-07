FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY src/evidence_service/requirements.txt src/evidence_service/requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY src/ /app/src/

ENV PYTHONPATH=/app

EXPOSE 8080

CMD ["uvicorn", "src.evidence_service.main:app", "--host", "0.0.0.0", "--port", "8080"]
