from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from server.database import create_db_and_tables
from server.api import router
from server.scheduler import start_scheduler
from server.admin_users import ensure_seed_admin_users
from server.queue_worker import start_queue_worker, stop_queue_worker
import os

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

origins_env = (os.getenv("CORS_ORIGINS") or os.getenv("FRONTEND_ORIGINS") or "").strip()
origins = [o.strip() for o in origins_env.split(",") if o.strip()] if origins_env else []
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
    start_scheduler()
    start_queue_worker()

@app.on_event("shutdown")
def on_shutdown():
    stop_queue_worker()

app.include_router(router, prefix="/api")

# 挂载前端静态文件
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web/dist")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

