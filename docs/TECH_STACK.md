# Technology Stack and Libraries

| Layer | Technology |
|---|---|
| Language/runtime | Python 3.11+ |
| API | FastAPI, Uvicorn, Pydantic |
| Multipart upload | python-multipart |
| PDF validation/text extraction | pypdf |
| Browser UI | Server-served HTML5, CSS and vanilla JavaScript |
| Local persistence | SQLite, JSON, JSON Lines, filesystem |
| Production data target | PostgreSQL/psycopg |
| Testing | unittest, FastAPI TestClient/httpx2 |

Dependency files:

- `requirements-api.txt`: FastAPI runtime, upload support, test client and PDF reader.
- `requirements-postgres.txt`: optional PostgreSQL client for future adapter work.

Removed libraries: PyTorch, Transformers, Accelerate, Hugging Face Hub, Pillow, scikit-learn and joblib. They belonged to deleted VLM/training products and are not required by the current application. Scanned-image OCR still needs an approved provider/library plus its runtime dependency before production.
