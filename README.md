# VerifyGrid

**VerifyGrid** is an intelligent data verification and reconciliation platform designed to ingest, clean, normalize, and reconcile complex datasets across diverse formats.

---

## Repository Structure

```
verifygrid/
├── backend/            # FastAPI + SQLAlchemy + PostgreSQL backend
│   ├── app/            # Application source code
│   │   ├── api/        # REST API endpoints (v1)
│   │   ├── core/       # Configuration and security settings
│   │   ├── db/         # Database sessions and models
│   │   ├── models/     # SQLAlchemy ORM models
│   │   ├── schemas/    # Pydantic validation schemas
│   │   ├── services/   # Business logic, ingestion, preprocessing
│   │   └── utils/      # Normalization and matching utilities
│   ├── migrations/     # Alembic database migrations
│   ├── storage/        # Project-scoped local storage for file uploads
│   ├── tests/          # Comprehensive automated test suite
│   └── README.md       # Detailed backend documentation
└── frontend/           # React frontend application
```

---

## Quick Start

### Backend Setup

```bash
cd backend

# Create or activate virtual environment
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start development server
uvicorn app.main:app --reload
```

API documentation will be accessible at [http://localhost:8000/docs](http://localhost:8000/docs).

### Running Tests

```bash
cd backend
pytest tests/ -v
```

For detailed documentation on the data preprocessing pipeline, API schemas, and normalization rules, refer to [backend/README.md](backend/README.md).
