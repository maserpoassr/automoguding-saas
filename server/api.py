from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlmodel import Session, select
from sqlalchemy import func
from server.database import get_session, engine
from server.models import User, UserCreate, UserRead, UserUpdate, UserListRead, AuditLog, BatchJob, BatchJobItem, AdminUser, AppUser
from server.scheduler import add_user_job, remove_user_job, user_to_config
from server.task_runner import run_task_by_config
from server.util.Config import ConfigManager
from server.coreApi.MainLogicApi import ApiClient
from server.coreApi.AiServiceClient import generate_article
from typing import List, Any, Dict, Optional
import datetime
import requests
from pydantic import BaseModel
from urllib.parse import urljoin, urlparse
import time
import os
import ipaddress
import socket
import re
import threading
from collections import OrderedDict
from server.auth import get_admin, get_operator, get_viewer, get_user, issue_token, get_client_ip, verify_password, hash_password
from server.secret_store import encrypt_secret

router = APIRouter()

NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org"

def _is_private_or_special_ip(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
        return bool(
            a.is_private
            or a.is_loopback
            or a.is_link_local
            or a.is_multicast
            or a.is_reserved
            or a.is_unspecified
        )
    except Exception:
        return True

def _is_safe_outbound_url(url: str) -> bool:
    allow_private = (os.getenv("ALLOW_PRIVATE_AI_TEST") or "").strip().lower() in ["1", "true", "yes", "on"]
    if allow_private:
        return True
    u = urlparse(url)
    if u.scheme != "https":
        return False
    host = (u.hostname or "").strip()
    if not host:
        return False
    if host.lower() == "localhost":
        return False
    port = u.port or 443
    if port != 443:
        return False
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except Exception:
        return False
    for info in infos:
        ip = info[4][0]
        if _is_private_or_special_ip(ip):
            return False
    return True

def _sanitize_user_for_read(user: User) -> Dict[str, Any]:
    data = UserRead.model_validate(user).model_dump()
    data["password"] = ""
    phone = data.get("phone")
    if isinstance(phone, str):
        data["phone"] = _mask_phone(phone)
    clock_in = data.get("clockIn")
    if isinstance(clock_in, dict):
        clock_in2 = _mask_clockin(clock_in)
        data["clockIn"] = clock_in2
    ai = data.get("ai")
    if isinstance(ai, dict):
        ai2 = dict(ai)
        if "apikey" in ai2:
            ai2["apikey"] = ""
        data["ai"] = ai2
    return data

def _sanitize_user_for_self(user: User) -> Dict[str, Any]:
    data = UserRead.model_validate(user).model_dump()
    data["password"] = ""
    phone = data.get("phone")
    if isinstance(phone, str):
        data["phone"] = _mask_phone(phone)
    if "app_password_hash" in data:
        data["app_password_hash"] = None
    return data

def _get_authed_app_user(*, session: Session, payload: dict) -> AppUser:
    sub = str(payload.get("sub") or "")
    if sub.startswith("app:"):
        try:
            app_user_id = int(sub.split(":", 1)[1])
        except Exception:
            raise HTTPException(status_code=401, detail="未登录或登录已过期")
        app_user = session.get(AppUser, app_user_id)
        if not app_user:
            raise HTTPException(status_code=401, detail="未登录或登录已过期")
        if app_user.enabled is not True:
            raise HTTPException(status_code=403, detail="账号已被禁用")
        return app_user

    if not sub.startswith("user:"):
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    try:
        legacy_user_id = int(sub.split(":", 1)[1])
    except Exception:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    legacy_user = session.get(User, legacy_user_id)
    if not legacy_user:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    if legacy_user.app_enabled is not True:
        raise HTTPException(status_code=403, detail="账号已被禁用")
    if not legacy_user.app_password_hash:
        raise HTTPException(status_code=403, detail="账号未启用用户端登录")
    app_user = session.exec(select(AppUser).where(AppUser.phone == legacy_user.phone)).first()
    if not app_user:
        app_user = AppUser(
            phone=legacy_user.phone,
            password_hash=legacy_user.app_password_hash,
            enabled=bool(legacy_user.app_enabled),
            bound_user_id=legacy_user.id,
        )
        session.add(app_user)
        session.commit()
        session.refresh(app_user)
    if app_user.enabled is not True:
        raise HTTPException(status_code=403, detail="账号已被禁用")
    return app_user

def _get_bound_task_user(*, session: Session, app_user: AppUser) -> User:
    if not app_user.bound_user_id:
        raise HTTPException(status_code=403, detail="请先绑定工学云账号")
    user = session.get(User, int(app_user.bound_user_id))
    if not user:
        raise HTTPException(status_code=403, detail="绑定信息已失效，请重新绑定工学云账号")
    return user

def _any_report_enabled(user: User) -> bool:
    rs = user.reportSettings if isinstance(user.reportSettings, dict) else {}
    for k in ["daily", "weekly", "monthly"]:
        part = rs.get(k)
        if isinstance(part, dict) and part.get("enabled") is True:
            return True
    return False

class AppRegisterRequest(BaseModel):
    phone: str
    password: str

class AppLoginRequest(BaseModel):
    phone: str
    password: str

class AppReportSubmitRequest(BaseModel):
    content: str

class AppMeResponse(BaseModel):
    app_phone: str
    bound: bool
    task_user: Optional[Dict[str, Any]] = None

class AppRunRequest(BaseModel):
    task_type: Optional[str] = None

@router.post("/app/auth/register")
def app_register(request: Request, req: AppRegisterRequest):
    client_ip = get_client_ip(request)
    _rate_limit(f"app_register:{client_ip}", limit=10, per_seconds=60)
    phone = (req.phone or "").strip()
    password = (req.password or "").strip()
    if not phone or len(phone) < 4:
        raise HTTPException(status_code=400, detail="请输入正确的手机号/账号")
    if not password or len(password) < 6:
        raise HTTPException(status_code=400, detail="密码长度需为 6-100")
    with Session(engine) as session:
        exists = session.exec(select(AppUser).where(AppUser.phone == phone)).first()
        if exists:
            raise HTTPException(status_code=400, detail="该账号已注册")
        legacy = session.exec(select(User).where(User.phone == phone)).first()
        if legacy and legacy.app_password_hash:
            raise HTTPException(status_code=400, detail="该账号已注册")
        app_user = AppUser(phone=phone, password_hash=hash_password(password), enabled=True, bound_user_id=None)
        session.add(app_user)
        session.flush()
        session.add(AuditLog(actor=f"app:{app_user.id}", action="app.register", target_user_id=None, detail={}))
        session.commit()
        token = issue_token(subject=f"app:{app_user.id}", role="user")
        return {"token": token, "user_id": app_user.id, "phone": phone}

@router.post("/app/auth/login")
def app_login(request: Request, req: AppLoginRequest):
    client_ip = get_client_ip(request)
    _rate_limit(f"app_login:{client_ip}", limit=15, per_seconds=60)
    phone = (req.phone or "").strip()
    password = (req.password or "").strip()
    with Session(engine) as session:
        app_user = session.exec(select(AppUser).where(AppUser.phone == phone)).first()
        if app_user:
            if app_user.enabled is not True:
                raise HTTPException(status_code=403, detail="账号已被禁用")
            if not verify_password(password, app_user.password_hash):
                raise HTTPException(status_code=401, detail="账号或密码错误")
            token = issue_token(subject=f"app:{app_user.id}", role="user")
            session.add(AuditLog(actor=f"app:{app_user.id}", action="app.login", target_user_id=None, detail={}))
            session.commit()
            return {"token": token, "user_id": app_user.id, "phone": phone}

        legacy_user = session.exec(select(User).where(User.phone == phone)).first()
        if not legacy_user or legacy_user.app_enabled is not True or not legacy_user.app_password_hash:
            raise HTTPException(status_code=401, detail="账号或密码错误")
        if not verify_password(password, legacy_user.app_password_hash):
            raise HTTPException(status_code=401, detail="账号或密码错误")
        app_user = AppUser(
            phone=phone,
            password_hash=legacy_user.app_password_hash,
            enabled=True,
            bound_user_id=legacy_user.id,
        )
        session.add(app_user)
        session.flush()
        token = issue_token(subject=f"app:{app_user.id}", role="user")
        session.add(AuditLog(actor=f"app:{app_user.id}", action="app.login", target_user_id=legacy_user.id, detail={"legacy": True}))
        session.commit()
        return {"token": token, "user_id": app_user.id, "phone": phone}

@router.get("/app/me")
def app_me(*, session: Session = Depends(get_session), payload: dict = Depends(get_user)):
    app_user = _get_authed_app_user(session=session, payload=payload)
    if not app_user.bound_user_id:
        return AppMeResponse(app_phone=app_user.phone, bound=False, task_user=None)
    user = session.get(User, int(app_user.bound_user_id))
    if not user:
        return AppMeResponse(app_phone=app_user.phone, bound=False, task_user=None)
    return AppMeResponse(app_phone=app_user.phone, bound=True, task_user=_sanitize_user_for_self(user))

class AppMeUpdateRequest(BaseModel):
    password: Optional[str] = None
    clockIn: Optional[Dict[str, Any]] = None
    reportSettings: Optional[Dict[str, Any]] = None
    ai: Optional[Dict[str, Any]] = None

class AppBindRequest(BaseModel):
    task_phone: str
    task_password: str

@router.post("/app/bind")
def app_bind(
    *,
    request: Request,
    session: Session = Depends(get_session),
    payload: dict = Depends(get_user),
    req: AppBindRequest,
):
    app_user = _get_authed_app_user(session=session, payload=payload)
    task_phone = (req.task_phone or "").strip()
    task_password = (req.task_password or "").strip()
    if not task_phone or len(task_phone) < 4:
        raise HTTPException(status_code=400, detail="请输入正确的工学云账号")
    if not task_password or len(task_password) < 6:
        raise HTTPException(status_code=400, detail="密码长度需为 6-100")

    client_ip = get_client_ip(request)
    _rate_limit(
        f"app_bind:{client_ip}:{app_user.id}",
        limit=10,
        per_seconds=10 * 60,
        detail="绑定尝试过于频繁，请 10 分钟后再试",
    )

    verify_on = (os.getenv("MOGUDING_BIND_VERIFY") or "1").strip().lower() not in ["0", "false", "no", "off"]
    if verify_on:
        cfg = ConfigManager(config={"config": {"user": {"phone": task_phone, "password": task_password}}})
        api_client = ApiClient(cfg)
        api_client.max_retries = 1
        try:
            api_client.login()
            token = cfg.get_value("userInfo.token")
            if not token:
                raise HTTPException(status_code=400, detail="工学云账号验证失败")
        except HTTPException:
            raise
        except Exception as e:
            msg = str(e) or "工学云账号验证失败"
            if "验证码" in msg:
                raise HTTPException(status_code=400, detail="工学云账号验证失败：触发验证码，请稍后再试")
            raise HTTPException(status_code=400, detail="工学云账号或密码错误")

    user = session.exec(select(User).where(User.phone == task_phone)).first()
    if user:
        other = session.exec(select(AppUser).where((AppUser.bound_user_id == user.id) & (AppUser.id != app_user.id))).first()
        if other:
            raise HTTPException(status_code=400, detail="该工学云账号已被其他账号绑定")
        user.password = encrypt_secret(task_password)
        if user.enable_clockin is None:
            user.enable_clockin = True
    else:
        user = User(
            phone=task_phone,
            password=encrypt_secret(task_password),
            remark=None,
            app_enabled=True,
            enable_clockin=True,
        )
        _ensure_clockin_schedule_defaults(user)
        session.add(user)
        session.flush()

    app_user.bound_user_id = user.id
    session.add(app_user)
    session.add(user)
    session.add(AuditLog(actor=str(payload.get("sub")), action="app.bind", target_user_id=user.id, detail={"task_phone": _mask_phone(task_phone)}))
    session.commit()
    session.refresh(user)
    remove_user_job(user.id)
    if user.enable_clockin or _any_report_enabled(user):
        add_user_job(user)
    return {"ok": True, "user_id": user.id}

@router.get("/app/account-address")
def app_account_address(
    *,
    request: Request,
    session: Session = Depends(get_session),
    payload: dict = Depends(get_user),
):
    app_user = _get_authed_app_user(session=session, payload=payload)
    user = _get_bound_task_user(session=session, app_user=app_user)
    client_ip = get_client_ip(request)
    _rate_limit(f"app_account_addr:{client_ip}:{user.id}", limit=3, per_seconds=60)

    if not (str(user.phone or "").strip()) or not (str(user.password or "").strip()):
        raise HTTPException(status_code=400, detail="该用户未保存账号或密码，无法自动获取账号地址")

    try:
        config_data = user_to_config(user)
        config = ConfigManager(config=config_data)
        api_client = ApiClient(config)
        if not config.get_value("userInfo.token"):
            api_client.login()
        if config.get_value("userInfo.userType") != "teacher" and not config.get_value("planInfo.planId"):
            api_client.fetch_internship_plan()
        checkin = api_client.get_checkin_info() or {}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e) or "获取账号地址失败")

    candidates: List[str] = []
    for k in [
        "address",
        "detailAddress",
        "lastDetailAddress",
        "lastAddress",
        "practiceAddress",
        "practiceDetailAddress",
        "companyAddress",
        "workAddress",
    ]:
        v = checkin.get(k)
        if isinstance(v, str):
            s = v.strip()
            if s and s not in candidates:
                candidates.append(s)

    best = candidates[0] if candidates else None
    if candidates:
        best = sorted(candidates, key=lambda x: len(x), reverse=True)[0]
    if not best:
        raise HTTPException(status_code=404, detail="未获取到账号地址（可能该账号暂无打卡记录）")

    try:
        clock_in = user.clockIn if isinstance(user.clockIn, dict) else {}
        loc = clock_in.get("location") if isinstance(clock_in.get("location"), dict) else {}
        loc2 = dict(loc)
        loc2["address"] = best
        parts = [p.strip() for p in re.split(r"\s*[·,/，,]\s*", str(best)) if p and p.strip()]
        if len(parts) >= 1 and not loc2.get("province"):
            loc2["province"] = parts[0]
        if len(parts) >= 2 and not loc2.get("city"):
            loc2["city"] = parts[1]
        if len(parts) >= 3 and not loc2.get("area"):
            loc2["area"] = parts[2]
        clock_in2 = dict(clock_in)
        clock_in2["location"] = loc2
        user.clockIn = clock_in2
        session.add(user)
        session.commit()
    except Exception:
        session.rollback()

    return {
        "ok": True,
        "address": best,
        "addressCandidates": candidates,
        "checkinTime": checkin.get("attendenceTime"),
        "type": checkin.get("type"),
    }

@router.patch("/app/me")
def app_update_me(
    *,
    session: Session = Depends(get_session),
    payload: dict = Depends(get_user),
    req: AppMeUpdateRequest,
):
    app_user = _get_authed_app_user(session=session, payload=payload)
    user = _get_bound_task_user(session=session, app_user=app_user)
    changed: List[str] = []
    if req.password is not None:
        pw = (req.password or "").strip()
        if not pw or len(pw) < 6 or len(pw) > 100:
            raise HTTPException(status_code=400, detail="密码长度需为 6-100")
        user.password = encrypt_secret(pw)
        changed.append("password")
    if req.clockIn is not None:
        if not isinstance(req.clockIn, dict):
            raise HTTPException(status_code=400, detail="clockIn 格式错误")
        user.clockIn = req.clockIn
        changed.append("clockIn")
        _ensure_clockin_schedule_defaults(user)
    if req.reportSettings is not None:
        if not isinstance(req.reportSettings, dict):
            raise HTTPException(status_code=400, detail="reportSettings 格式错误")
        user.reportSettings = req.reportSettings
        changed.append("reportSettings")
    if req.ai is not None:
        if not isinstance(req.ai, dict):
            raise HTTPException(status_code=400, detail="ai 格式错误")
        ai_update = dict(req.ai)
        if "apikey" in ai_update and not (str(ai_update.get("apikey") or "").strip()):
            ai_update.pop("apikey", None)
        if ai_update:
            current_ai = user.ai if isinstance(user.ai, dict) else {}
            merged_ai = dict(current_ai)
            merged_ai.update(ai_update)
            user.ai = merged_ai
            changed.append("ai")
    session.add(user)
    session.add(AuditLog(actor=str(payload.get("sub")), action="app.user.update", target_user_id=user.id, detail={"fields": changed}))
    session.commit()
    session.refresh(user)
    remove_user_job(user.id)
    if user.enable_clockin or _any_report_enabled(user):
        add_user_job(user)
    return _sanitize_user_for_self(user)

@router.post("/app/run")
def app_run(
    *,
    request: Request,
    session: Session = Depends(get_session),
    payload: dict = Depends(get_user),
    req: Optional[AppRunRequest] = None,
):
    app_user = _get_authed_app_user(session=session, payload=payload)
    user = _get_bound_task_user(session=session, app_user=app_user)
    client_ip = get_client_ip(request)
    _rate_limit(f"app_run:{client_ip}:{user.id}", limit=3, per_seconds=60)
    config_data = user_to_config(user)

    specific_task_type = req.task_type if req else None
    results = run_task_by_config(config_data, specific_task_type=specific_task_type)

    user.last_run_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "Success"
    for r in results:
        if r.get("status") == "fail":
            status = "Fail"
            break
    user.last_status = status
    log_summary = []
    for r in results:
        if r.get("status") != "skip":
            log_summary.append(f"{r.get('task_type')}: {r.get('message')}")
    if log_summary:
        user.logs = log_summary
    user.last_execution_result = results
    session.add(AuditLog(actor=str(payload.get("sub")), action="app.user.run", target_user_id=user.id, detail={"status": status}))
    session.add(user)
    session.commit()
    return {"results": results}

@router.get("/app/execution")
def app_execution(*, session: Session = Depends(get_session), payload: dict = Depends(get_user)):
    app_user = _get_authed_app_user(session=session, payload=payload)
    user = _get_bound_task_user(session=session, app_user=app_user)
    return {"results": user.last_execution_result or []}
