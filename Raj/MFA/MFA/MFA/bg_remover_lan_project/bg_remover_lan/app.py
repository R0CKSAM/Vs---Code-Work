import html
import io
import os
import socket
import traceback
import uuid
import zipfile
from pathlib import Path
from threading import Lock
from typing import List

from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image
from rembg import new_session, remove

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "outputs"
TEMP_DIR = BASE_DIR / "temp"
OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "35"))
MAX_BATCH = int(os.getenv("MAX_BATCH", "20"))
MODEL_NAME = os.getenv("REMBG_MODEL", "u2net")

app = FastAPI(title="Office AI Background Remover", version="1.0.0")

# Enable CORS for LAN access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Output-Filename"],
)

# Static files
static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Templates
templates_dir = BASE_DIR / "templates"
try:
    templates = Jinja2Templates(directory=str(templates_dir))
except Exception as e:
    print(f"[WARN] Jinja2Templates init error: {e}")
    templates = None

_session = None
_session_lock = Lock()


def get_session():
    global _session
    if _session is None:
        with _session_lock:
            if _session is None:
                try:
                    print(f"Loading rembg model '{MODEL_NAME}'...")
                    _session = new_session(MODEL_NAME)
                    print(f"Model '{MODEL_NAME}' loaded successfully.")
                except Exception as exc:
                    print(f"[ERROR] Failed to initialize rembg session with '{MODEL_NAME}': {exc}")
                    _session = None
    return _session


def safe_stem(filename: str) -> str:
    stem = Path(filename or "image").stem
    cleaned = "".join(c for c in stem if c.isalnum() or c in ("-", "_", " ")).strip()
    return cleaned[:80] or "image"


def validate_upload(upload: UploadFile, data: bytes):
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {suffix or 'unknown'}")
    if len(data) > MAX_FILE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"{upload.filename} exceeds {MAX_FILE_MB} MB")


def process_bytes(data: bytes) -> Image.Image:
    try:
        with Image.open(io.BytesIO(data)) as img:
            img = img.convert("RGBA")
            original_size = img.size
            session = get_session()
            if session is not None:
                result = remove(img, session=session)
            else:
                result = remove(img)
            if result.size != original_size:
                result = result.resize(original_size, Image.Resampling.LANCZOS)
            return result.convert("RGBA")
    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"Could not process image: {exc}") from exc


def image_to_png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    context = {
        "request": request,
        "max_file_mb": MAX_FILE_MB,
        "max_batch": MAX_BATCH,
        "model_name": MODEL_NAME,
    }

    # 1. Try modern Starlette >= 0.36 (FastAPI >= 0.108): TemplateResponse(request=request, name="index.html", context=context)
    if templates is not None:
        try:
            return templates.TemplateResponse(request=request, name="index.html", context=context)
        except TypeError:
            # 2. Try legacy Starlette < 0.36: TemplateResponse(name="index.html", context=context)
            try:
                return templates.TemplateResponse("index.html", context)
            except Exception as exc:
                print(f"[WARN] TemplateResponse legacy failed: {exc}")
        except Exception as exc:
            print(f"[WARN] TemplateResponse modern failed: {exc}")

    # 3. Direct HTML fallback: read template file and interpolate variables
    index_file = BASE_DIR / "templates" / "index.html"
    if index_file.exists():
        html_content = index_file.read_text(encoding="utf-8")
        html_content = html_content.replace("{{ max_file_mb }}", str(MAX_FILE_MB))
        html_content = html_content.replace("{{ max_batch }}", str(MAX_BATCH))
        html_content = html_content.replace("{{ model_name }}", str(MODEL_NAME))
        return HTMLResponse(content=html_content, status_code=200)

    return HTMLResponse(
        content="<h1>Office AI Background Remover</h1><p>templates/index.html not found.</p>",
        status_code=500,
    )


@app.get("/health")
async def health():
    return {"status": "ok", "model": MODEL_NAME}


@app.post("/api/remove")
async def remove_single(file: UploadFile = File(...)):
    data = await file.read()
    validate_upload(file, data)
    result = process_bytes(data)
    png = image_to_png_bytes(result)
    output_name = f"{safe_stem(file.filename)}_no_bg.png"
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Content-Disposition": f'attachment; filename="{output_name}"',
            "X-Output-Filename": output_name,
        },
    )


@app.post("/api/remove-batch")
async def remove_batch(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    if len(files) > MAX_BATCH:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_BATCH} files per batch")

    zip_buffer = io.BytesIO()
    errors = []
    used_names = set()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for index, upload in enumerate(files, start=1):
            try:
                data = await upload.read()
                validate_upload(upload, data)
                result = process_bytes(data)
                base = f"{safe_stem(upload.filename)}_no_bg"
                name = f"{base}.png"
                counter = 2
                while name.lower() in used_names:
                    name = f"{base}_{counter}.png"
                    counter += 1
                used_names.add(name.lower())
                zf.writestr(name, image_to_png_bytes(result))
            except Exception as exc:
                detail = getattr(exc, "detail", str(exc))
                errors.append(f"{upload.filename}: {detail}")

        if errors:
            zf.writestr("errors.txt", "\n".join(errors))

    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="background_removed_images.zip"'},
    )


def get_lan_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        return "127.0.0.1"


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "6805"))
    detected_ip = get_lan_ip()

    print("\n=======================================================")
    print(" Office AI Background Remover")
    print("=======================================================")
    print(f" Local URL:   http://127.0.0.1:{port}")
    print(f" Target LAN:  http://192.168.50.134:{port}")
    if detected_ip not in ("127.0.0.1", "192.168.50.134"):
        print(f" Detected IP: http://{detected_ip}:{port}")
    print(f" Binding to:  {host}:{port}")
    print(" Press Ctrl+C to stop.")
    print("=======================================================\n")

    uvicorn.run("app:app", host=host, port=port, reload=False)
