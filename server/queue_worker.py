import datetime
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from sqlmodel import Session, select
from sqlalchemy import update, case, func

from server.database import engine
from server.models import BatchJob, BatchJobItem, User, AuditLog
from server.scheduler import user_to_config
from server.task_runner import run_task_by_config

_stop_event = threading.Event()
_thread: threading.Thread | None = None
_executor: ThreadPoolExecutor | None = None

def _now_utc() -> datetime.datetime:
    return datetime.datetime.utcnow()

def _calc_backoff_seconds(attempts: int) -> int:
    base = int(os.getenv("BATCH_RETRY_BASE_SECONDS") or "3")
    cap = int(os.getenv("BATCH_RETRY_MAX_SECONDS") or "60")
    if attempts <= 0:
        return base
    seconds = base * (2 ** (attempts - 1))
    return min(cap, seconds)

def _finalize_item(job_id: int, item_id: int, ok: bool, error: str | None) -> None:
    with Session(engine) as session:
        item = session.get(BatchJobItem, item_id)
        if not item:
            return
        item.status = "success" if ok else "fail"
        item.finished_at = datetime.datetime.utcnow()
        item.error = error
        session.add(item)
        now = _now_utc().isoformat(sep=" ", timespec="seconds")
        success_inc = 1 if ok else 0
        fail_inc = 0 if ok else 1
        session.exec(
            update(BatchJob)
            .where(BatchJob.id == job_id)
            .values(
                completed=BatchJob.completed + 1,
                success=BatchJob.success + success_inc,
                fail=BatchJob.fail + fail_inc,
                status=case((BatchJob.completed + 1 >= BatchJob.total, "done"), else_="running"),
                started_at=func.coalesce(BatchJob.started_at, now),
                finished_at=case((BatchJob.completed + 1 >= BatchJob.total, now), else_=BatchJob.finished_at),
            )
        )
        session.commit()

# (文件其余部分保持仓库原样，本次仅同步 finalize commit 合并优化)
