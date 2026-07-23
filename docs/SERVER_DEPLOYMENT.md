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

The one-shot `model-init` service seeds demo data, builds the model registry,
trains both synthetic development advisory classifiers, and trains the curated
support-chatbot intent classifier before the servers start.

- Browser: `http://SERVER:8000`
- API docs: `http://SERVER:8001/docs`
- API health: `http://SERVER:8001/api/v1/health`

The generated classifiers validate the model pipeline only. Synthetic fixtures
are not production model validation and must not influence live banking
decisions.

## Optional Qwen document vision model

The default `baseline` document provider requires no foundation-model download.
Qwen2.5-VL-3B is optional, large, and should only be installed after model-card,
licence, supply-chain, privacy, data-residency, RAM/VRAM, and GPU review:

```sh
docker compose --profile document-ai run --rm qwen-download
```

The downloaded model is stored in the `document_models` Docker volume. Enabling
inference also requires a GPU-capable runtime/device configuration. Set these
values in `.env`, rebuild `web` and `api`, and configure the Compose GPU device
reservation for the server:

```text
BANKING_IMAGE_TARGET=document-ai
DOCUMENT_AI_PROVIDER=qwen
DOCUMENT_AI_MODEL=/models/qwen2.5-vl-3b
```

Do not enable Qwen merely because it downloaded successfully. Its output is a
review suggestion and cannot authenticate identity, approve credit, or replace
human verification.

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

The `banking_data` volume persists application state and trained local artifacts.
The initializer records a marker in that volume and does not reseed or retrain
after successful first-time initialization.
