import logging
import datetime
import os
from zoneinfo import ZoneInfo
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from server.task_runner import run_task_by_config
from server.database import engine
from server.models import User
from server.secret_store import decrypt_secret
from sqlmodel import Session, select
from typing import Dict, Any

def _resolve_scheduler_timezone():
    tz_name = (os.getenv("SCHEDULER_TIMEZONE") or os.getenv("TZ") or "").strip()
    if not tz_name:
        tz_name = "Asia/Shanghai"
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return None

scheduler = BackgroundScheduler(timezone=_resolve_scheduler_timezone())
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

def _get_report_settings(user: User) -> Dict[str, Any]:
    rs = user.reportSettings or {}
    if not isinstance(rs, dict):
        rs = {}
    daily = rs.get("daily") if isinstance(rs.get("daily"), dict) else {}
    weekly = rs.get("weekly") if isinstance(rs.get("weekly"), dict) else {}
    monthly = rs.get("monthly") if isinstance(rs.get("monthly"), dict) else {}
    return {"daily": daily, "weekly": weekly, "monthly": monthly}

def _parse_hhmm_str(value: Any, default_h: int, default_m: int):
    return _parse_hhmm(value, default_h, default_m)

def run_report_job(user_id: int, specific_task_type: str):
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            logger.info(f"用户 {user_id} 不存在，跳过任务")
            return
        config_data = user_to_config(user)

    logger.info(f"开始执行用户 {user_id} 的定时报告任务: {specific_task_type}")
    try:
        results = run_task_by_config(config_data, specific_task_type=specific_task_type)
        with Session(engine) as session:
            user = session.get(User, user_id)
            if user:
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
    try:
        jitter_seconds = int(os.getenv("SCHEDULER_JITTER_SECONDS") or "600")
    except Exception:
        jitter_seconds = 600
    jitter_seconds = max(0, min(jitter_seconds, 3600))
    try:
        report_jitter_seconds = int(os.getenv("SCHEDULER_REPORT_JITTER_SECONDS") or "0")
    except Exception:
        report_jitter_seconds = 0
    report_jitter_seconds = max(0, min(report_jitter_seconds, 3600))

    if user.enable_clockin:
        scheduler.add_job(
            run_job,
            CronTrigger(day_of_week=dow, hour=start_h, minute=start_m, jitter=jitter_seconds),
            args=[user.id, "START"],
            id=f"user_{user.id}_start",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=15 * 60,
        )
        scheduler.add_job(
            run_job,
            CronTrigger(day_of_week=dow, hour=end_h, minute=end_m, jitter=jitter_seconds),
            args=[user.id, "END"],
            id=f"user_{user.id}_end",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=15 * 60,
        )

    rs = _get_report_settings(user)
    daily = rs.get("daily") or {}
    weekly = rs.get("weekly") or {}
    monthly = rs.get("monthly") or {}

    if daily.get("enabled") is True:
        submit_time = daily.get("submitTime") or "12:00"
        submit_days = daily.get("submitDays")
        daily_dow = _weekday_list_to_cron(submit_days) if submit_days is not None else "mon,tue,wed,thu,fri,sat,sun"
        if daily_dow:
            hh, mm = _parse_hhmm_str(submit_time, 12, 0)
            scheduler.add_job(
                run_report_job,
                CronTrigger(day_of_week=daily_dow, hour=hh, minute=mm, jitter=report_jitter_seconds),
                args=[user.id, "daily_report"],
                id=f"user_{user.id}_daily_report",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=60 * 60,
            )

    if weekly.get("enabled") is True:
        try:
            submit_weekday = int(weekly.get("submitTime"))
        except Exception:
            submit_weekday = 1
        weekly_dow = _weekday_list_to_cron([submit_weekday])
        submit_at = weekly.get("submitAt") or "12:00"
        hh, mm = _parse_hhmm_str(submit_at, 12, 0)
        if weekly_dow:
            scheduler.add_job(
                run_report_job,
                CronTrigger(day_of_week=weekly_dow, hour=hh, minute=mm, jitter=report_jitter_seconds),
                args=[user.id, "weekly_report"],
                id=f"user_{user.id}_weekly_report",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=12 * 60 * 60,
            )

    if monthly.get("enabled") is True:
        try:
            submit_day = int(monthly.get("submitTime"))
        except Exception:
            submit_day = 20
        submit_day = max(1, min(submit_day, 31))
        day_expr = "28,29,30,31" if submit_day >= 28 else str(submit_day)
        submit_at = monthly.get("submitAt") or "12:00"
        hh, mm = _parse_hhmm_str(submit_at, 12, 0)
        scheduler.add_job(
            run_report_job,
            CronTrigger(day=day_expr, hour=hh, minute=mm, jitter=report_jitter_seconds),
            args=[user.id, "monthly_report"],
            id=f"user_{user.id}_monthly_report",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=24 * 60 * 60,
        )

def remove_user_job(user_id: int):
    try:
        scheduler.remove_job(f"user_{user_id}_start")
        scheduler.remove_job(f"user_{user_id}_end")
        scheduler.remove_job(f"user_{user_id}_daily_report")
        scheduler.remove_job(f"user_{user_id}_weekly_report")
        scheduler.remove_job(f"user_{user_id}_monthly_report")
    except Exception:
        pass

def start_scheduler():
    scheduler.start()
    with Session(engine) as session:
        # 注意：这里可能需要处理数据库还没初始化的问题，最好在 main.py 里先调 create_db_and_tables
        try:
            users = session.exec(select(User)).all()
            for user in users:
                add_user_job(user)
            logger.info(f"调度器启动，加载了 {len(users)} 个用户的任务")
        except Exception as e:
            logger.error(f"加载任务失败（可能是数据库未初始化）: {e}")
