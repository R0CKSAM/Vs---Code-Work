# Media Reporting System - Backend

FastAPI backend service for the Media Reporting System.

## Architecture (Phase 0)

In **Phase 0 — Foundation**, the backend provides:
- Core application setup with modular architecture
- Configured CORS middleware for the local React/Vite frontend
- Pydantic schemas validating API payloads
- Mock data service supplying realistic media industry KPIs, monitored websites, and news
- Clean separation: endpoints (`api/`), business logic/mock service (`services/`), schemas (`schemas/`), configuration (`core/`)

> **Note**: Database (PostgreSQL) and scraping engines (BeautifulSoup / Playwright) will be introduced in subsequent phases.

---

## Directory Structure

```
backend/
├── app/
│   ├── api/
│   │   └── endpoints/
│   │       ├── health.py        # GET /api/health
│   │       └── dashboard.py     # GET /api/dashboard
│   ├── core/
│   │   └── config.py           # Application settings and CORS
│   ├── models/                 # Database models (Phase 4)
│   ├── schemas/
│   │   └── dashboard.py        # Pydantic validation schemas
│   ├── services/
│   │   └── mock_data.py        # Phase 0 mock data generator
│   ├── utils/                  # Helper utilities
│   ├── __init__.py
│   └── main.py                 # FastAPI application instance
├── requirements.txt
└── README.md
```

---

## How to Run

### 1. Prerequisites
- Python 3.10+ installed

### 2. Create and Activate Virtual Environment
```bash
# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv .venv

# Activate on Windows PowerShell:
.venv\Scripts\Activate.ps1

# Or activate on Windows Command Prompt:
.venv\Scripts\activate.bat

# Or activate on Linux/macOS:
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run Development Server
```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API will be available at:
- **Root**: `http://127.0.0.1:8000/`
- **Interactive Swagger Docs**: `http://127.0.0.1:8000/docs`
- **Health Check**: `http://127.0.0.1:8000/api/health`
- **Dashboard Data**: `http://127.0.0.1:8000/api/dashboard`
