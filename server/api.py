from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlmodel import Session, select
from sqlalchemy import func
from server.database import get_session, engine
from server.models import User, UserCreate, UserRead, UserUpdate, UserListRead, AuditLog, BatchJob, BatchJobItem, AdminUser
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
from server.auth import get_admin, get_operator, get_viewer, issue_token, get_client_ip, verify_password, hash_password
from server.secret_store import encrypt_secret

router = APIRouter()

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

def _mask_phone(value: str) -> str:
    s = str(value or "").strip()
    if not s:
        return ""
    digits = re.sub(r"\D", "", s)
    if len(digits) >= 4:
        last4 = digits[-4:]
        return "********" + last4
    return "*" * max(1, len(digits))

def _mask_number_like(value: Any) -> Any:
    if value is None:
        return value
    s = str(value).strip()
    if not s:
        return value
    sign = ""
    if s[0] in ["+", "-"]:
        sign = s[0]
        s = s[1:]
    digits = [c for c in s if c.isdigit()]
    if not digits:
        return value
    first = digits[0]
    masked_len = max(1, len(digits) - 1)
    return f"{sign}{first}{'*' * masked_len}"

def _mask_address(value: Any) -> Any:
    if value is None:
        return value
    s = str(value).strip()
    if not s:
        return value
    parts = [p.strip() for p in re.split(r"\s*[·,/，,]\s*", s) if p and p.strip()]
    if len(parts) >= 2:
        return f"{parts[0]}·{parts[1]}·***"
    m = re.search(r"(省|自治区|特别行政区)", s)
    if m:
        prov_end = m.end()
        rest = s[prov_end:]
        m2 = re.search(r"(市|州|盟|地区)", rest)
        if m2:
            city_end = prov_end + m2.end()
            return f"{s[:city_end]}·***"
        return f"{s[:prov_end]}·***"
    m3 = re.search(r"市", s)
    if m3:
        return f"{s[:m3.end()]}·***"
    return "***"

def _mask_clockin(clock_in: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(clock_in)
    location = out.get("location")
    if isinstance(location, dict):
        loc = dict(location)
        if "address" in loc:
            loc["address"] = _mask_address(loc.get("address"))
        if "latitude" in loc:
            loc["latitude"] = _mask_number_like(loc.get("latitude"))
        if "longitude" in loc:
            loc["longitude"] = _mask_number_like(loc.get("longitude"))
        if "area" in loc and loc.get("area"):
            loc["area"] = "***"
        out["location"] = loc
    return out

class AiTestRequest(BaseModel):
    apiUrl: str
    apikey: str
    model: str

class ReportSubmitRequest(BaseModel):
    content: str

_RATE_LIMIT_BUCKETS: Dict[str, List[float]] = {}
_GEOCODE_CACHE: "OrderedDict[tuple, tuple[float, Any]]" = OrderedDict()
_GEOCODE_LOCK = threading.Lock()

def _geocode_cache_get(key: tuple) -> Any:
    now = time.time()
    with _GEOCODE_LOCK:
        hit = _GEOCODE_CACHE.get(key)
        if not hit:
            return None
        exp, value = hit
        if exp <= now:
            _GEOCODE_CACHE.pop(key, None)
            return None
        _GEOCODE_CACHE.move_to_end(key)
        return value

def _geocode_cache_set(key: tuple, value: Any, ttl_seconds: int = 3600, maxsize: int = 800) -> None:
    now = time.time()
    exp = now + int(ttl_seconds)
    with _GEOCODE_LOCK:
        _GEOCODE_CACHE[key] = (exp, value)
        _GEOCODE_CACHE.move_to_end(key)
        while len(_GEOCODE_CACHE) > int(maxsize):
            _GEOCODE_CACHE.popitem(last=False)

def _rate_limit(key: str, limit: int, per_seconds: int) -> None:
    now = time.time()
    bucket = _RATE_LIMIT_BUCKETS.get(key, [])
    cutoff = now - per_seconds
    bucket = [t for t in bucket if t >= cutoff]
    if len(bucket) >= limit:
        raise HTTPException(status_code=429, detail="操作过于频繁，请稍后再试")
    bucket.append(now)
    _RATE_LIMIT_BUCKETS[key] = bucket

def _ensure_clockin_schedule_defaults(user: User):
    if not isinstance(user.clockIn, dict):
        return
    schedule = user.clockIn.get("schedule")
    if not isinstance(schedule, dict):
        schedule = {}
        user.clockIn["schedule"] = schedule
    schedule.setdefault("startTime", "07:30")
    schedule.setdefault("endTime", "18:00")
    weekdays = schedule.get("weekdays")
    if not isinstance(weekdays, list) or len(weekdays) == 0:
        custom_days = user.clockIn.get("customDays")
        if isinstance(custom_days, list) and len(custom_days) > 0:
            schedule["weekdays"] = custom_days
        else:
            schedule["weekdays"] = [1, 2, 3, 4, 5, 6, 7]
    if not schedule.get("totalDays"):
        schedule["totalDays"] = 180
    if schedule.get("totalDays") and not schedule.get("startDate"):
        schedule["startDate"] = datetime.date.today().strftime("%Y-%m-%d")

class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/auth/login")
def admin_login(request: Request, req: LoginRequest):
    client_ip = get_client_ip(request)
    _rate_limit(f"login:{client_ip}", limit=10, per_seconds=60)
    username = (req.username or "").strip()
    password = (req.password or "").strip()
    with Session(engine) as session:
        user = session.exec(select(AdminUser).where(AdminUser.username == username)).first()
        if not user or not user.enabled:
            raise HTTPException(status_code=401, detail="账号或密码错误")
        if not verify_password(password, user.password_hash):
            raise HTTPException(status_code=401, detail="账号或密码错误")
        role = user.role or "viewer"
        token = issue_token(subject=username, role=role)
        session.add(AuditLog(actor=username, action="auth.login", target_user_id=None, detail={"role": role}))
        session.commit()
        return {"token": token, "role": role, "username": username}

class AuditLogPageResponse(BaseModel):
    items: List[Dict[str, Any]]
    total: int
    page: int
    pageSize: int

@router.get("/audit-logs/page", response_model=AuditLogPageResponse)
def read_audit_logs_page(
    *,
    session: Session = Depends(get_session),
    admin: dict = Depends(get_admin),
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=200),
    q: Optional[str] = Query(None, max_length=60),
):
    stmt = select(AuditLog)
    if q:
        qq = q.strip()
        stmt = stmt.where((AuditLog.actor.contains(qq)) | (AuditLog.action.contains(qq)))
    total = session.exec(select(func.count()).select_from(stmt.subquery())).one()
    rows = session.exec(
        stmt.order_by(AuditLog.id.desc()).offset((page - 1) * pageSize).limit(pageSize)
    ).all()
    items = [
        {
            "id": r.id,
            "created_at": r.created_at.isoformat(sep=" ", timespec="seconds"),
            "actor": r.actor,
            "action": r.action,
            "target_user_id": r.target_user_id,
            "detail": r.detail,
        }
        for r in rows
    ]
    return {"items": items, "total": total, "page": page, "pageSize": pageSize}

class AdminUserCreateRequest(BaseModel):
    username: str
    password: str
    role: str = "viewer"

class AdminUserUpdateRequest(BaseModel):
    role: Optional[str] = None
    enabled: Optional[bool] = None

class AdminUserResetPasswordRequest(BaseModel):
    password: str

class AdminUserPageResponse(BaseModel):
    items: List[Dict[str, Any]]
    total: int
    page: int
    pageSize: int

@router.get("/admin-users/page", response_model=AdminUserPageResponse)
def read_admin_users_page(
    *,
    session: Session = Depends(get_session),
    admin: dict = Depends(get_admin),
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=200),
    q: Optional[str] = Query(None, max_length=60),
):
    stmt = select(AdminUser).where(AdminUser.role == "admin")
    if q:
        qq = q.strip()
        stmt = stmt.where(AdminUser.username.contains(qq))
    total = session.exec(select(func.count()).select_from(stmt.subquery())).one()
    rows = session.exec(
        stmt.order_by(AdminUser.id.desc()).offset((page - 1) * pageSize).limit(pageSize)
    ).all()
    items = [
        {
            "id": r.id,
            "created_at": r.created_at.isoformat(sep=" ", timespec="seconds"),
            "username": r.username,
            "role": r.role,
            "enabled": r.enabled,
        }
        for r in rows
    ]
    return {"items": items, "total": total, "page": page, "pageSize": pageSize}

@router.post("/admin-users")
def create_admin_user(
    *,
    session: Session = Depends(get_session),
    admin: dict = Depends(get_admin),
    req: AdminUserCreateRequest,
):
    raise HTTPException(status_code=400, detail="该管理平台仅保留管理员账号，此功能已禁用")

@router.patch("/admin-users/{admin_user_id}")
def update_admin_user(
    *,
    session: Session = Depends(get_session),
    admin: dict = Depends(get_admin),
    admin_user_id: int,
    req: AdminUserUpdateRequest,
):
    user = session.get(AdminUser, admin_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    changed: List[str] = []
    if user.role != "admin":
        raise HTTPException(status_code=400, detail="仅允许管理管理员账号")
    if req.role is not None:
        raise HTTPException(status_code=400, detail="不允许修改角色")
    if req.enabled is not None:
        enabled = bool(req.enabled)
        if not enabled and user.role == "admin":
            enabled_admins = session.exec(
                select(func.count()).select_from(AdminUser).where((AdminUser.role == "admin") & (AdminUser.enabled == True))
            ).one()
            if enabled_admins <= 1:
                raise HTTPException(status_code=400, detail="至少保留一个启用的管理员")
        user.enabled = enabled
        changed.append("enabled")
    session.add(user)
    session.add(AuditLog(actor=admin.get("sub"), action="admin_user.update", target_user_id=None, detail={"id": admin_user_id, "fields": changed}))
    session.commit()
    return {"ok": True}

@router.post("/admin-users/{admin_user_id}/reset-password")
def reset_admin_user_password(
    *,
    session: Session = Depends(get_session),
    admin: dict = Depends(get_admin),
    admin_user_id: int,
    req: AdminUserResetPasswordRequest,
):
    user = session.get(AdminUser, admin_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role != "admin":
        raise HTTPException(status_code=400, detail="仅允许管理管理员账号")
    password = (req.password or "").strip()
    if not password or len(password) < 6 or len(password) > 100:
        raise HTTPException(status_code=400, detail="密码长度需为 6-100")
    user.password_hash = hash_password(password)
    session.add(user)
    session.add(AuditLog(actor=admin.get("sub"), action="admin_user.reset_password", target_user_id=None, detail={"id": admin_user_id, "username": user.username}))
    session.commit()
    return {"ok": True}

@router.post("/users", response_model=UserRead)
def create_user(*, session: Session = Depends(get_session), user: UserCreate, operator: dict = Depends(get_operator)):
    db_user = User.from_orm(user)
    db_user.password = encrypt_secret(db_user.password)
    _ensure_clockin_schedule_defaults(db_user)
    session.add(db_user)
    session.flush()
    session.add(AuditLog(actor=operator.get("sub"), action="user.create", target_user_id=db_user.id, detail={"phone": db_user.phone}))
    session.commit()
    session.refresh(db_user)
    if db_user.enable_clockin:
        add_user_job(db_user)
    return _sanitize_user_for_read(db_user)

@router.get("/users", response_model=List[UserRead])
def read_users(*, session: Session = Depends(get_session), admin: dict = Depends(get_admin)):
    users = session.exec(select(User)).all()
    return [_sanitize_user_for_read(u) for u in users]

class UserPageResponse(BaseModel):
    items: List[UserListRead]
    total: int
    page: int
    pageSize: int
    q: Optional[str] = None

@router.get("/users/page", response_model=UserPageResponse)
def read_users_page(
    *,
    session: Session = Depends(get_session),
    viewer: dict = Depends(get_viewer),
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=200),
    q: Optional[str] = Query(None, min_length=1, max_length=50),
):
    stmt = select(User)
    if q:
        qq = q.strip()
        stmt = stmt.where((User.phone.contains(qq)) | (func.coalesce(User.remark, "").contains(qq)))

    total = session.exec(select(func.count()).select_from(stmt.subquery())).one()
    users = session.exec(
        stmt.order_by(User.id.desc()).offset((page - 1) * pageSize).limit(pageSize)
    ).all()
    items = [
        UserListRead(
            id=u.id,
            phone=_mask_phone(u.phone),
            remark=u.remark,
            enable_clockin=u.enable_clockin,
            last_run_time=u.last_run_time,
            last_status=u.last_status,
            logs=u.logs or [],
        )
        for u in users
    ]
    return {"items": items, "total": total, "page": page, "pageSize": pageSize, "q": q}

@router.get("/users/{user_id}", response_model=UserRead)
def read_user(*, session: Session = Depends(get_session), user_id: int, viewer: dict = Depends(get_viewer)):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _sanitize_user_for_read(user)

@router.get("/users/{user_id}/execution")
def read_user_execution(*, session: Session = Depends(get_session), user_id: int, viewer: dict = Depends(get_viewer)):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"results": user.last_execution_result or []}

@router.get("/users/{user_id}/job-info")
def read_user_job_info(
    *,
    request: Request,
    session: Session = Depends(get_session),
    user_id: int,
    operator: dict = Depends(get_operator),
):
    client_ip = get_client_ip(request)
    _rate_limit(f"job_info:{client_ip}:{user_id}", limit=3, per_seconds=60)
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not (str(user.phone or "").strip()) or not (str(user.password or "").strip()):
        raise HTTPException(status_code=400, detail="该用户未保存账号或密码，无法自动获取岗位信息")

    config_data = user_to_config(user)
    config = ConfigManager(config=config_data)
    api_client = ApiClient(config)
    if not config.get_value("userInfo.token"):
        api_client.login()
    if config.get_value("userInfo.userType") != "teacher" and not config.get_value("planInfo.planId"):
        api_client.fetch_internship_plan()
    job_info = api_client.get_job_info() or {}
    company = job_info.get("practiceCompanyEntity") or {}
    candidates = []
    for k in [
        "jobAddress",
        "address",
        "detailAddress",
        "jobDetailAddress",
        "practiceAddress",
        "practiceDetailAddress",
        "companyAddress",
        "workAddress",
    ]:
        v = job_info.get(k)
        if isinstance(v, str):
            s = v.strip()
            if s and s not in candidates:
                candidates.append(s)
    job_address = job_info.get("jobAddress")
    if isinstance(job_address, str):
        job_address = job_address.strip()
    if not job_address:
        job_address = candidates[0] if candidates else None
    return {
        "ok": True,
        "jobId": job_info.get("jobId"),
        "jobAddress": job_address,
        "addressCandidates": candidates,
        "companyName": company.get("companyName"),
        "quartersIntroduce": job_info.get("quartersIntroduce"),
    }


@router.get("/users/{user_id}/account-address")
def read_user_account_address(
    *,
    request: Request,
    session: Session = Depends(get_session),
    user_id: int,
    operator: dict = Depends(get_operator),
):
    client_ip = get_client_ip(request)
    _rate_limit(f"account_addr:{client_ip}:{user_id}", limit=3, per_seconds=60)
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
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
        "maskedAddress": _mask_address(best),
        "maskedCandidates": [_mask_address(x) for x in candidates],
        "checkinTime": checkin.get("attendenceTime"),
        "type": checkin.get("type"),
    }

@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(*, session: Session = Depends(get_session), user_id: int, user_update: UserUpdate, operator: dict = Depends(get_operator)):
    db_user = session.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    user_data = user_update.dict(exclude_unset=True)
    if "phone" in user_data and isinstance(user_data.get("phone"), str) and "*" in user_data.get("phone"):
        user_data.pop("phone", None)
    if "password" in user_data:
        if not (str(user_data.get("password") or "").strip()):
            user_data.pop("password", None)
        else:
            user_data["password"] = encrypt_secret(str(user_data.get("password") or ""))
    if "clockIn" in user_data and isinstance(user_data.get("clockIn"), dict) and isinstance(db_user.clockIn, dict):
        upd_clock = dict(user_data.get("clockIn") or {})
        upd_loc = upd_clock.get("location")
        cur_loc = (db_user.clockIn.get("location") or {}) if isinstance(db_user.clockIn.get("location"), dict) else {}
        if isinstance(upd_loc, dict):
            loc2 = dict(upd_loc)
            for k in ["address", "latitude", "longitude", "province", "city", "area"]:
                v = loc2.get(k)
                if isinstance(v, str) and "*" in v:
                    if k in cur_loc:
                        loc2[k] = cur_loc.get(k)
                    else:
                        loc2.pop(k, None)
            upd_clock["location"] = loc2
        user_data["clockIn"] = upd_clock
    if "ai" in user_data and isinstance(user_data.get("ai"), dict):
        ai_update = dict(user_data.get("ai") or {})
        if "apikey" in ai_update and not (str(ai_update.get("apikey") or "").strip()):
            ai_update.pop("apikey", None)
        if ai_update:
            current_ai = db_user.ai if isinstance(db_user.ai, dict) else {}
            merged_ai = dict(current_ai)
            merged_ai.update(ai_update)
            user_data["ai"] = merged_ai
        else:
            user_data.pop("ai", None)
    for key, value in user_data.items():
        setattr(db_user, key, value)
    _ensure_clockin_schedule_defaults(db_user)

    session.add(db_user)
    session.add(AuditLog(actor=operator.get("sub"), action="user.update", target_user_id=user_id, detail={"fields": list(user_data.keys())}))
    session.commit()
    session.refresh(db_user)

    remove_user_job(user_id)
    if db_user.enable_clockin:
        add_user_job(db_user)

    return _sanitize_user_for_read(db_user)

@router.delete("/users/{user_id}")
def delete_user(*, session: Session = Depends(get_session), user_id: int, admin: dict = Depends(get_admin)):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    remove_user_job(user_id)
    session.delete(user)
    session.add(AuditLog(actor=admin.get("sub"), action="user.delete", target_user_id=user_id, detail={}))
    session.commit()
    return {"ok": True}

@router.post("/users/{user_id}/run")
def run_user_task(*, request: Request, session: Session = Depends(get_session), user_id: int, operator: dict = Depends(get_operator)):
    client_ip = get_client_ip(request)
    _rate_limit(f"run:{client_ip}:{user_id}", limit=2, per_seconds=60)
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    config_data = user_to_config(user)
    results = run_task_by_config(config_data)

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

    session.add(AuditLog(actor=operator.get("sub"), action="user.run", target_user_id=user_id, detail={"status": status}))
    session.add(user)
    session.commit()

    return {"results": results}

class BatchRunRequest(BaseModel):
    ids: List[int]
    concurrency: int = 5

@router.post("/users/run/batch")
def run_users_batch(*, request: Request, req: BatchRunRequest, operator: dict = Depends(get_operator)):
    client_ip = get_client_ip(request)
    _rate_limit(f"run_batch:{client_ip}", limit=1, per_seconds=10)
    ids = [int(x) for x in (req.ids or []) if int(x) > 0]
    if not ids:
        raise HTTPException(status_code=400, detail="请选择要运行的账号")
    max_concurrency = int(os.getenv("BATCH_JOB_MAX_CONCURRENCY") or "10")
    max_concurrency = max(1, min(max_concurrency, 50))
    concurrency = max(1, min(int(req.concurrency or 5), max_concurrency))
    with Session(engine) as session:
        job = BatchJob(created_by=operator.get("sub"), total=len(ids), concurrency=concurrency, user_ids=ids, status="queued")
        session.add(job)
        session.flush()
        items = [BatchJobItem(job_id=job.id, user_id=uid, status="queued") for uid in ids]
        session.add_all(items)
        session.add(AuditLog(actor=operator.get("sub"), action="batch.enqueue", target_user_id=None, detail={"job_id": job.id, "total": len(ids), "concurrency": concurrency}))
        session.commit()
        job_id = job.id
    return {"ok": True, "queued": len(ids), "concurrency": concurrency, "job_id": job_id}

@router.get("/batch-jobs/{job_id}")
def read_batch_job(*, session: Session = Depends(get_session), job_id: int = 0, viewer: dict = Depends(get_viewer)):
    job = session.get(BatchJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    running = session.exec(
        select(func.count()).select_from(BatchJobItem).where((BatchJobItem.job_id == job_id) & (BatchJobItem.status == "running"))
    ).one()
    queued = session.exec(
        select(func.count()).select_from(BatchJobItem).where((BatchJobItem.job_id == job_id) & (BatchJobItem.status == "queued"))
    ).one()
    last_errors = session.exec(
        select(BatchJobItem)
        .where((BatchJobItem.job_id == job_id) & (BatchJobItem.status == "fail"))
        .order_by(BatchJobItem.id.desc())
        .limit(20)
    ).all()
    return {
        "id": job.id,
        "created_at": job.created_at.isoformat(sep=" ", timespec="seconds"),
        "created_by": job.created_by,
        "status": job.status,
        "total": job.total,
        "completed": job.completed,
        "success": job.success,
        "fail": job.fail,
        "concurrency": job.concurrency,
        "running": int(running or 0),
        "queued": int(queued or 0),
        "last_errors": [
            {"user_id": it.user_id, "message": it.error or "Fail", "ts": (it.finished_at.isoformat() if it.finished_at else None)}
            for it in last_errors
        ],
    }

@router.post("/batch-jobs/{job_id}/pause")
def pause_batch_job(*, session: Session = Depends(get_session), job_id: int, operator: dict = Depends(get_operator)):
    job = session.get(BatchJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.paused = True
    session.add(job)
    session.add(AuditLog(actor=operator.get("sub"), action="batch.pause", target_user_id=None, detail={"job_id": job_id}))
    session.commit()
    return {"ok": True}

@router.post("/batch-jobs/{job_id}/resume")
def resume_batch_job(*, session: Session = Depends(get_session), job_id: int, operator: dict = Depends(get_operator)):
    job = session.get(BatchJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.paused = False
    if job.status in ["paused", "queued"]:
        job.status = "queued"
    session.add(job)
    session.add(AuditLog(actor=operator.get("sub"), action="batch.resume", target_user_id=None, detail={"job_id": job_id}))
    session.commit()
    return {"ok": True}

@router.post("/batch-jobs/{job_id}/cancel")
def cancel_batch_job(*, session: Session = Depends(get_session), job_id: int, operator: dict = Depends(get_operator)):
    job = session.get(BatchJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.cancel_requested = True
    session.add(job)
    session.add(AuditLog(actor=operator.get("sub"), action="batch.cancel", target_user_id=None, detail={"job_id": job_id}))
    session.commit()
    return {"ok": True}

@router.post("/ai/test")
def ai_test(request: Request, req: AiTestRequest, operator: dict = Depends(get_operator)):
    client_ip = get_client_ip(request)
    _rate_limit(f"ai_test:{client_ip}", limit=5, per_seconds=60)
    api_url = (req.apiUrl or "").strip()
    api_key = (req.apikey or "").strip()
    model = (req.model or "").strip()
    if not api_url or not api_key or not model:
        raise HTTPException(status_code=400, detail="请填写 API URL、API Key 和 Model")
    base = api_url.rstrip("/")
    endpoint = urljoin(base + "/", "chat/completions") if base.endswith("/v1") else urljoin(base + "/", "v1/chat/completions")
    if not _is_safe_outbound_url(endpoint):
        raise HTTPException(status_code=400, detail="AI API URL 不安全（仅允许 https 且禁止内网/本机地址）")
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
        "temperature": 0,
    }
    t0 = time.time()
    try:
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=20)
        latency_ms = int((time.time() - t0) * 1000)
        if resp.status_code >= 400:
            try:
                err = resp.json()
            except Exception:
                err = {"error": resp.text}
            raise HTTPException(status_code=502, detail=f"AI 接口返回错误: {resp.status_code} {err}")
        data = resp.json()
        content = (
            (data.get("choices") or [{}])[0].get("message", {}).get("content")
            if isinstance(data, dict)
            else None
        )
        return {"ok": True, "latency_ms": latency_ms, "reply": content}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 接口请求失败: {str(e)}")


@router.post("/users/{user_id}/reports/daily/generate")
def generate_daily_report(
    *,
    request: Request,
    session: Session = Depends(get_session),
    user_id: int,
    operator: dict = Depends(get_operator),
):
    client_ip = get_client_ip(request)
    _rate_limit(f"daily_gen:{client_ip}:{user_id}", limit=3, per_seconds=60)
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not (str(user.phone or "").strip()) or not (str(user.password or "").strip()):
        raise HTTPException(status_code=400, detail="该用户未保存账号或密码，无法生成日报")

    config_data = user_to_config(user)
    config = ConfigManager(config=config_data)
    api_client = ApiClient(config)

    ai_cfg = config.get_value("config.ai")
    if not isinstance(ai_cfg, dict):
        raise HTTPException(status_code=400, detail="未配置 AI 参数")
    if not (str(ai_cfg.get("apikey") or "").strip()) or not (str(ai_cfg.get("apiUrl") or "").strip()) or not (str(ai_cfg.get("model") or "").strip()):
        raise HTTPException(status_code=400, detail="请先在 AI 设置中填写 API URL、API Key 和 Model")

    try:
        if not config.get_value("userInfo.token"):
            api_client.login()
        if config.get_value("userInfo.userType") != "teacher" and not config.get_value("planInfo.planId"):
            api_client.fetch_internship_plan()

        submitted = api_client.get_submitted_reports_info("day") or {}
        data = submitted.get("data", []) if isinstance(submitted, dict) else []
        count = (submitted.get("flag", 0) if isinstance(submitted, dict) else 0) + 1
        title = f"第{count}天日报"

        already_submitted = False
        current_time = datetime.datetime.now()
        if isinstance(data, list) and data:
            last = data[0]
            ts = last.get("createTime")
            if isinstance(ts, str):
                try:
                    last_time = datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                    if last_time.date() == current_time.date():
                        already_submitted = True
                except Exception:
                    pass

        job_info = api_client.get_job_info()
        content = generate_article(config, title, job_info, config.get_value("planInfo.planPaper.dayPaperNum"))
        return {"ok": True, "title": title, "content": content, "already_submitted": already_submitted}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e) or "生成日报失败")


@router.post("/users/{user_id}/reports/daily/submit")
def submit_daily_report_manual(
    *,
    request: Request,
    session: Session = Depends(get_session),
    user_id: int,
    req: ReportSubmitRequest,
    operator: dict = Depends(get_operator),
):
    client_ip = get_client_ip(request)
    _rate_limit(f"daily_submit:{client_ip}:{user_id}", limit=3, per_seconds=60)
    content = (req.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="日报内容不能为空")

    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not (str(user.phone or "").strip()) or not (str(user.password or "").strip()):
        raise HTTPException(status_code=400, detail="该用户未保存账号或密码，无法提交日报")

    config_data = user_to_config(user)
    config = ConfigManager(config=config_data)
    api_client = ApiClient(config)

    try:
        if not config.get_value("userInfo.token"):
            api_client.login()
        if config.get_value("userInfo.userType") != "teacher" and not config.get_value("planInfo.planId"):
            api_client.fetch_internship_plan()

        submitted = api_client.get_submitted_reports_info("day") or {}
        data = submitted.get("data", []) if isinstance(submitted, dict) else []
        current_time = datetime.datetime.now()
        if isinstance(data, list) and data:
            last = data[0]
            ts = last.get("createTime")
            if isinstance(ts, str):
                try:
                    last_time = datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                    if last_time.date() == current_time.date():
                        raise HTTPException(status_code=400, detail="今天已经提交过日报")
                except HTTPException:
                    raise
                except Exception:
                    pass

        count = (submitted.get("flag", 0) if isinstance(submitted, dict) else 0) + 1
        title = f"第{count}天日报"
        job_info = api_client.get_job_info()
        report_info = {
            "title": title,
            "content": content,
            "attachments": "",
            "reportType": "day",
            "jobId": job_info.get("jobId", None),
            "reportTime": current_time.strftime("%Y-%m-%d %H:%M:%S"),
            "formFieldDtoList": api_client.get_from_info(7),
        }
        api_client.submit_report(report_info)
        return {"ok": True, "title": title, "submitted_at": report_info["reportTime"]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e) or "提交日报失败")


@router.get("/geocode/search")
def geocode_search(q: str = Query(..., min_length=1, max_length=200), operator: dict = Depends(get_operator)):
    provider = (os.getenv("GEOCODE_PROVIDER") or "").strip().lower()
    amap_key = (os.getenv("AMAP_KEY") or "").strip()
    if not provider:
        provider = "amap" if amap_key else "osm"
    q2 = (q or "").strip()
    cache_key = ("search", provider, q2)
    cached = _geocode_cache_get(cache_key)
    if cached is not None:
        return cached

    if provider == "amap" and amap_key:
        try:
            resp = requests.get(
                "https://restapi.amap.com/v3/geocode/geo",
                params={"key": amap_key, "address": q2, "output": "json"},
                timeout=12,
            )
            resp.raise_for_status()
            data = resp.json() or {}
            geocodes = data.get("geocodes") or []
            results: List[Dict[str, Any]] = []
            for item in geocodes[:5]:
                loc = item.get("location")
                if not isinstance(loc, str) or "," not in loc:
                    continue
                lng_s, lat_s = loc.split(",", 1)
                try:
                    lon = float(lng_s)
                    lat = float(lat_s)
                except Exception:
                    continue
                label = item.get("formatted_address") or item.get("address") or q2
                results.append({"x": lon, "y": lat, "label": label, "bounds": None, "raw": item})
            out = {"results": results}
            _geocode_cache_set(cache_key, out, ttl_seconds=6 * 60 * 60, maxsize=800)
            return out
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"地理搜索失败: {str(e)}")

    nominatim_base = (os.getenv("NOMINATIM_BASE_URL") or "https://nominatim.openstreetmap.org").rstrip("/")
    params = {"q": q2, "format": "json", "limit": 5, "addressdetails": 1}
    headers = {"User-Agent": "AutoMoGuDingSaaS/1.0", "Accept-Language": "zh-CN,zh;q=0.9"}
    last_err: Optional[Exception] = None
    for attempt in range(2):
        try:
            resp = requests.get(
                f"{nominatim_base}/search",
                params=params,
                headers=headers,
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            results: List[Dict[str, Any]] = []
            for item in data or []:
                try:
                    lat = float(item.get("lat"))
                    lon = float(item.get("lon"))
                except Exception:
                    continue
                bbox = item.get("boundingbox")
                bounds: Optional[List[List[float]]] = None
                if isinstance(bbox, list) and len(bbox) == 4:
                    try:
                        south, north, west, east = map(float, bbox)
                        bounds = [[south, west], [north, east]]
                    except Exception:
                        bounds = None
                results.append(
                    {
                        "x": lon,
                        "y": lat,
                        "label": item.get("display_name") or q2,
                        "bounds": bounds,
                        "raw": item,
                    }
                )
            out = {"results": results}
            _geocode_cache_set(cache_key, out, ttl_seconds=60 * 60, maxsize=800)
            return out
        except Exception as e:
            last_err = e
            time.sleep(0.4 * (attempt + 1))
    raise HTTPException(status_code=502, detail=f"地理搜索失败: {str(last_err) if last_err else 'unknown'}")


@router.get("/geocode/reverse")
def geocode_reverse(
    lat: float = Query(...),
    lon: float = Query(...),
    operator: dict = Depends(get_operator),
):
    provider = (os.getenv("GEOCODE_PROVIDER") or "").strip().lower()
    amap_key = (os.getenv("AMAP_KEY") or "").strip()
    if not provider:
        provider = "amap" if amap_key else "osm"
    cache_key = ("reverse", provider, round(float(lat), 6), round(float(lon), 6))
    cached = _geocode_cache_get(cache_key)
    if cached is not None:
        return cached

    if provider == "amap" and amap_key:
        try:
            resp = requests.get(
                "https://restapi.amap.com/v3/geocode/regeo",
                params={
                    "key": amap_key,
                    "location": f"{lon},{lat}",
                    "radius": 200,
                    "extensions": "base",
                    "output": "json",
                },
                timeout=12,
            )
            resp.raise_for_status()
            data = resp.json() or {}
            regeocode = data.get("regeocode") or {}
            formatted = regeocode.get("formatted_address") or ""
            comp = regeocode.get("addressComponent") or {}
            province = comp.get("province") or ""
            city = comp.get("city") or ""
            if isinstance(city, list):
                city = ""
            district = comp.get("district") or ""
            township = comp.get("township") or ""
            neighborhood = (comp.get("neighborhood") or {}).get("name") if isinstance(comp.get("neighborhood"), dict) else ""
            building = (comp.get("building") or {}).get("name") if isinstance(comp.get("building"), dict) else ""
            name = building or neighborhood or township or district or city or province or ""
            out = {
                "display_name": formatted or name,
                "name": name,
                "address": {
                    "province": province,
                    "city": city,
                    "county": district,
                    "district": district,
                    "town": township,
                    "township": township,
                },
                "raw": data,
            }
            out2 = {"result": out}
            _geocode_cache_set(cache_key, out2, ttl_seconds=6 * 60 * 60, maxsize=1200)
            return out2
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"逆地理解析失败: {str(e)}")

    nominatim_base = (os.getenv("NOMINATIM_BASE_URL") or "https://nominatim.openstreetmap.org").rstrip("/")
    params = {"lat": lat, "lon": lon, "format": "json", "zoom": 18, "addressdetails": 1}
    headers = {"User-Agent": "AutoMoGuDingSaaS/1.0", "Accept-Language": "zh-CN,zh;q=0.9"}
    last_err: Optional[Exception] = None
    for attempt in range(2):
        try:
            resp = requests.get(
                f"{nominatim_base}/reverse",
                params=params,
                headers=headers,
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            out = {"result": data}
            _geocode_cache_set(cache_key, out, ttl_seconds=60 * 60, maxsize=1200)
            return out
        except Exception as e:
            last_err = e
            time.sleep(0.4 * (attempt + 1))
    raise HTTPException(status_code=502, detail=f"逆地理解析失败: {str(last_err) if last_err else 'unknown'}")
