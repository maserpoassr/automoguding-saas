import logging
import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from server.task_runner import run_task_by_config
from server.database import engine
from server.models import User
from server.secret_store import decrypt_secret
from sqlmodel import Session, select
from typing import Dict, Any

scheduler = BackgroundScheduler()
logger = logging.getLogger(__name__)

def user_to_config(user: User) -> Dict[str, Any]:
    try:
        password = decrypt_secret(user.password)
    except Exception:
        password = ""
    return {
        "config": {
            "user": {"phone": user.phone, "password": password},
            "clockIn": user.clockIn,
            "reportSettings": user.reportSettings,
            "ai": user.ai,
            "pushNotifications": user.pushNotifications,
            "device": user.device
        }
    }

def _weekday_list_to_cron(weekdays):
    mapping = {1: "mon", 2: "tue", 3: "wed", 4: "thu", 5: "fri", 6: "sat", 7: "sun"}
    if not isinstance(weekdays, list) or len(weekdays) == 0:
        return None
    parts = []
    for d in weekdays:
        try:
            d_int = int(d)
        except Exception:
            continue
        if d_int in mapping:
            parts.append(mapping[d_int])
    return ",".join(sorted(set(parts))) if parts else None


def _parse_hhmm(value: Any, default_h: int, default_m: int):
    if not isinstance(value, str) or ":" not in value:
        return default_h, default_m
    try:
        hh, mm = value.split(":", 1)
        return int(hh), int(mm)
    except Exception:
        return default_h, default_m


def _get_schedule(user: User) -> Dict[str, Any]:
    clock_in = user.clockIn or {}
    schedule = (clock_in.get("schedule") or {}) if isinstance(clock_in, dict) else {}
    start_time = schedule.get("startTime") or "07:30"
    end_time = schedule.get("endTime") or "18:00"
    weekdays = schedule.get("weekdays")
    if weekdays is None:
        weekdays = clock_in.get("customDays") if isinstance(clock_in, dict) else None
    if weekdays is None:
        weekdays = [1, 2, 3, 4, 5, 6, 7]
    total_days = schedule.get("totalDays") if isinstance(schedule, dict) else None
    start_date = schedule.get("startDate") if isinstance(schedule, dict) else None
    return {
        "startTime": start_time,
        "endTime": end_time,
        "weekdays": weekdays,
        "totalDays": total_days,
        "startDate": start_date,
    }


def run_job(user_id: int, forced_checkin_type: str):
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user or not user.enable_clockin:
            logger.info(f"用户 {user_id} 不存在或已禁用，跳过任务")
            return

        schedule = _get_schedule(user)
        total_days = schedule.get("totalDays")
        start_date = schedule.get("startDate")
        if isinstance(total_days, int) and total_days > 0:
            if not start_date:
                start_date = datetime.date.today().strftime("%Y-%m-%d")
                if isinstance(user.clockIn, dict):
                    user.clockIn.setdefault("schedule", {})["startDate"] = start_date
                    session.add(user)
                    session.commit()
            try:
                start_dt = datetime.datetime.strptime(str(start_date), "%Y-%m-%d").date()
                if datetime.date.today() >= (start_dt + datetime.timedelta(days=total_days)):
                    user.enable_clockin = False
                    session.add(user)
                    session.commit()
                    remove_user_job(user_id)
                    logger.info(f"用户 {user_id} 打卡天数已到期，已自动停用")
                    return
            except Exception:
                pass
            
        config_data = user_to_config(user)
        
    logger.info(f"开始执行用户 {user_id} 的定时任务")
    try:
        results = run_task_by_config(config_data, forced_checkin_type=forced_checkin_type)
        
        # 更新状态
        with Session(engine) as session:
            user = session.get(User, user_id)
            if user:
                user.last_run_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                # 简单判断，如果有 fail 则状态为 Fail
                status = "Success"
                for r in results:
                    if r.get("status") == "fail":
                        status = "Fail"
                        break
                user.last_status = status
                # 记录日志摘要
                log_summary = []
                for r in results:
                    if r.get("status") != "skip":
                        log_summary.append(f"{r.get('task_type')}: {r.get('message')}")
                if log_summary:
                    user.logs = log_summary # 覆盖旧日志
                user.last_execution_result = results
                session.add(user)
                session.commit()
    except Exception as e:
        logger.error(f"任务执行异常: {e}")

def add_user_job(user: User):
    schedule = _get_schedule(user)
    start_h, start_m = _parse_hhmm(schedule.get("startTime"), 7, 30)
    end_h, end_m = _parse_hhmm(schedule.get("endTime"), 18, 0)
    dow = _weekday_list_to_cron(schedule.get("weekdays"))
    if not dow:
        return

    # 上班打卡
    scheduler.add_job(
        run_job,
        CronTrigger(day_of_week=dow, hour=start_h, minute=start_m, jitter=600),
        args=[user.id, "START"],
        id=f"user_{user.id}_start",
        replace_existing=True
    )
    # 下班打卡
    scheduler.add_job(
        run_job,
        CronTrigger(day_of_week=dow, hour=end_h, minute=end_m, jitter=600),
        args=[user.id, "END"],
        id=f"user_{user.id}_end",
        replace_existing=True
    )

def remove_user_job(user_id: int):
    try:
        scheduler.remove_job(f"user_{user_id}_start")
        scheduler.remove_job(f"user_{user_id}_end")
    except Exception:
        pass

def start_scheduler():
    scheduler.start()
    with Session(engine) as session:
        # 注意：这里可能需要处理数据库还没初始化的问题，最好在 main.py 里先调 create_db_and_tables
        try:
            users = session.exec(select(User).where(User.enable_clockin == True)).all()
            for user in users:
                add_user_job(user)
            logger.info(f"调度器启动，加载了 {len(users)} 个用户的任务")
        except Exception as e:
            logger.error(f"加载任务失败（可能是数据库未初始化）: {e}")
