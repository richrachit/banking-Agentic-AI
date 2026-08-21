# Server deployment

This repository is a reference/demo implementation. Its local JSON/SQLite
persistence, in-process API tokens, demo identities, and filesystem uploads are
not suitable for live banking data without the production integrations and
controls described in the main README.

## Core server build

Install Docker Engine with the Compose plugin, copy `.env.example` to `.env`,
replace every example secret/origin, and run:

```sh
docker compose up --build -d web api
docker compose ps
```

The one-shot `model-init` service seeds demo workflow and credit-bureau fixture
data before the servers start. There are no secondary classifier-training jobs.

- Browser: `http://SERVER:8000`
- API docs: `http://SERVER:8001/docs`
- API health: `http://SERVER:8001/api/v1/health`

The only learned model is the unified generative-AI provider described in
[UNIFIED_GENERATIVE_AI.md](UNIFIED_GENERATIVE_AI.md).

## PostgreSQL schema preview

The PostgreSQL service remains an optional schema target:

```sh
docker compose --profile postgres up -d postgres
```

The running application still uses JSON/SQLite. Starting PostgreSQL does not
switch repositories.

## Operations

```sh
docker compose logs -f api web
docker compose restart api web
docker compose down
```

The `banking_data` volume persists application state. The `document_models`
volume stores the optional unified local base model.
The initializer records a marker in that volume and does not reseed or retrain
after successful first-time initialization.
