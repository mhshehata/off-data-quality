FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scripts/ scripts/
COPY sql/ sql/
COPY docs/sttm.xlsx docs/sttm.xlsx

CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--workers", "1", "--threads", "2", "--timeout", "3600", "scripts.pipeline_server:app"]
