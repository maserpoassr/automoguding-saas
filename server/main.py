import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from server.database import create_db_and_tables
from server.api import router
from server.scheduler import start_scheduler
from server.admin_users import ensure_seed_admin_users
from server.queue_worker import start_queue_worker, stop_queue_worker

app = FastAPI(title="AutoMoGuDing SaaS")

@app.middleware("http")
async def _security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    resp.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    return resp

def _strip_wrapping(s: str) -> str:
    s2 = (s or "").strip()
    while len(s2) >= 2 and s2[0] == s2[-1] and s2[0] in ["'", '"', "`"]:
        s2 = s2[1:-1].strip()
    return s2

def _parse_origins(s: str) -> list[str]:
    raw = _strip_wrapping(s)
    if not raw:
        return []
    out: list[str] = []
    for part in raw.split(","):
        v = _strip_wrapping(part)
        if v:
            out.append(v)
    return out

app_env = (os.getenv("APP_ENV") or os.getenv("ENV") or "").strip().lower()
origins_env = os.getenv("CORS_ORIGINS") or os.getenv("FRONTEND_ORIGINS") or ""
origins = _parse_origins(origins_env)

if origins or app_env not in ["prod", "production"]:
    if not origins:
        origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
    allow_all = len(origins) == 1 and origins[0] == "*"
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False if allow_all else True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
@app.on_event("startup")
def on_startup():
    create_db_and_tables()
    ensure_seed_admin_users()

    try:
        from server.util.CaptchaUtils import ensure_model_exists, MODEL_URLS

        for filename, url in MODEL_URLS.items():
            ensure_model_exists(filename, url)
    except Exception as e:
        print(f"Warning: Failed to download models: {e}")

    start_scheduler()
    start_queue_worker()


@app.on_event("shutdown")
def on_shutdown():
    stop_queue_worker()


app.include_router(router, prefix="/api")

static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web/dist")
if os.path.exists(static_dir):
    index_path = os.path.join(static_dir, "index.html")
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    @app.middleware("http")
    async def _spa_fallback(request: Request, call_next):
        resp = await call_next(request)
        if resp.status_code != 404:
            return resp
        if request.method != "GET":
            return resp
        path = request.url.path or "/"
        if path.startswith("/api"):
            return resp
        if path in ["/docs", "/redoc", "/openapi.json"]:
            return resp
        accept = (request.headers.get("accept") or "").lower()
        if "text/html" not in accept and "*/*" not in accept:
            return resp
        if not os.path.exists(index_path):
            return resp
        return FileResponse(index_path)
