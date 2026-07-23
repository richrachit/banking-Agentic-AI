FROM python:3.12-slim AS core

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    BANKING_DATA_DIR=/app/data

WORKDIR /app

COPY requirements-api.txt requirements-training.txt requirements-postgres.txt requirements-server.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements-server.txt

COPY banking_agents ./banking_agents
COPY scripts ./scripts
COPY database ./database
COPY data ./data

RUN mkdir -p /app/data/models /app/uploads

FROM core AS document-ai
COPY requirements-ai.txt ./
RUN python -m pip install -r requirements-ai.txt

FROM core AS runtime
EXPOSE 8000 8001
CMD ["python", "-m", "uvicorn", "banking_agents.api_app:app", "--host", "0.0.0.0", "--port", "8001"]
