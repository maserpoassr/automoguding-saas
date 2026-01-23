import os
from sqlmodel import Session, select
from server.models import AdminUser, AuditLog
from server.auth import hash_password

def ensure_seed_admin_users() -> None:
    from server.database import engine
    app_env = (os.getenv("APP_ENV") or os.getenv("ENV") or "").strip().lower()

    admin_user = (os.getenv("ADMIN_USERNAME") or "admin").strip()
    admin_pass = (os.getenv("ADMIN_PASSWORD") or "admin123456").strip()
    operator_user = (os.getenv("OPERATOR_USERNAME") or "operator").strip()
    operator_pass = (os.getenv("OPERATOR_PASSWORD") or "operator123456").strip()
    viewer_user = (os.getenv("VIEWER_USERNAME") or "viewer").strip()
    viewer_pass = (os.getenv("VIEWER_PASSWORD") or "viewer123456").strip()

    seeds = [
        (admin_user, admin_pass, "admin"),
        (operator_user, operator_pass, "operator"),
        (viewer_user, viewer_pass, "viewer"),
    ]

    with Session(engine) as session:
        has_any = session.exec(select(AdminUser).limit(1)).first() is not None
        if app_env in ["prod", "production"] and has_any:
            return
        if app_env in ["prod", "production"]:
            if os.getenv("ADMIN_USERNAME") is None or os.getenv("ADMIN_PASSWORD") is None:
                raise RuntimeError("生产环境必须设置 ADMIN_USERNAME / ADMIN_PASSWORD")
            if os.getenv("OPERATOR_USERNAME") is None or os.getenv("OPERATOR_PASSWORD") is None:
                raise RuntimeError("生产环境必须设置 OPERATOR_USERNAME / OPERATOR_PASSWORD")
            if os.getenv("VIEWER_USERNAME") is None or os.getenv("VIEWER_PASSWORD") is None:
                raise RuntimeError("生产环境必须设置 VIEWER_USERNAME / VIEWER_PASSWORD")
        for username, password, role in seeds:
            if not username or not password:
                continue
            existing = session.exec(select(AdminUser).where(AdminUser.username == username)).first()
            if existing:
                if not existing.role:
                    existing.role = role
                    session.add(existing)
                    session.commit()
                continue
            session.add(
                AdminUser(
                    username=username,
                    password_hash=hash_password(password),
                    role=role,
                    enabled=True,
                )
            )
            session.commit()
            session.add(AuditLog(actor="system", action="admin_user.seed", target_user_id=None, detail={"username": username, "role": role}))
            session.commit()

