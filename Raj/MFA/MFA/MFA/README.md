# Media Reporting System Workspace

A professional, local media monitoring and reporting platform.

### Zero Node.js Required — Single Command Run

You do not need Node.js or `npm`. Everything is served directly by the Python FastAPI backend on **Port 8000**:

```powershell
# 1. Navigate to backend
cd d:\MFA\media-reporting-system\backend

# 2. Install requirements (once)
python -m pip install -r requirements.txt

# 3. Start application
python -m uvicorn app.main:app --reload --port 8000
```

### Accessing the System:
- **Interactive Web Dashboard**: **`http://127.0.0.1:8000/`**
- **Dashboard JSON API**: `http://127.0.0.1:8000/api/dashboard`
- **Health Check API**: `http://127.0.0.1:8000/api/health`
- **Swagger Documentation**: `http://127.0.0.1:8000/docs`

---

*Note: For developers who wish to use Node.js and Vite separately, the `frontend/` directory is also preserved.*
