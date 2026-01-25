from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
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

# CORS 配置：默认允许同源访问，若配置了环境变量则追加
origins_env = (os.getenv("CORS_ORIGINS") or os.getenv("FRONTEND_ORIGINS") or "").strip()
origins = [o.strip() for o in origins_env.split(",") if o.strip()]
if not origins:
    # 默认允许开发环境，生产环境若同源则无需 CORS，但为了保险可设为 * 或具体域名
    # 注意：前后端同源部署（同端口）时，浏览器不会触发 CORS 预检，除非跨域
    origins = ["*"] 

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    create_db_and_tables()
    ensure_seed_admin_users()
    
    # 异步下载/检查模型文件
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

# 挂载前端静态文件及 SPA 路由回退处理
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web/dist")

if os.path.exists(static_dir):
    # 1. 先挂载静态资源目录（assets, vite.svg 等）
    app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")
    
    # 2. 手动处理根路径和其他路径，实现 SPA 的 History 模式支持
    #    即：如果是 API 请求则由上面 router 处理；
    #    如果文件存在则返回文件；
    #    否则（404）统一返回 index.html，让前端 Vue Router 接管
    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        # API 请求不处理（已由 include_router 处理，但为了保险起见）
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
            
        # 尝试查找物理文件
        file_path = os.path.join(static_dir, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
            
        # 默认返回 index.html
        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        
        return JSONResponse(status_code=404, content={"detail": "Frontend not found"})
