import os
from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy import text

sqlite_file_name = os.getenv("DB_PATH", "database.db")
sqlite_url = f"sqlite:///{sqlite_file_name}"

connect_args = {"check_same_thread": False}
engine = create_engine(sqlite_url, connect_args=connect_args)

def create_db_and_tables():
    db_dir = os.path.dirname(sqlite_file_name)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    SQLModel.metadata.create_all(engine)
    _migrate_sqlite_schema()

def _migrate_sqlite_schema():
    try:
        with engine.connect() as conn:
            def _table_exists(name: str) -> bool:
                row = conn.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
                    {"name": name},
                ).fetchone()
                return row is not None

            columns = conn.execute(text("PRAGMA table_info('user')")).fetchall()
            col_names = {row[1] for row in columns}
            if "last_execution_result" not in col_names:
                conn.execute(text("ALTER TABLE user ADD COLUMN last_execution_result TEXT"))
            if "remark" not in col_names:
                conn.execute(text("ALTER TABLE user ADD COLUMN remark TEXT"))

            if _table_exists("batchjob"):
                columns = conn.execute(text("PRAGMA table_info('batchjob')")).fetchall()
                col_names = {row[1] for row in columns}
                if "started_at" not in col_names:
                    conn.execute(text("ALTER TABLE batchjob ADD COLUMN started_at TEXT"))
                if "finished_at" not in col_names:
                    conn.execute(text("ALTER TABLE batchjob ADD COLUMN finished_at TEXT"))
                if "cancel_requested" not in col_names:
                    conn.execute(text("ALTER TABLE batchjob ADD COLUMN cancel_requested INTEGER DEFAULT 0"))
                if "paused" not in col_names:
                    conn.execute(text("ALTER TABLE batchjob ADD COLUMN paused INTEGER DEFAULT 0"))

            if _table_exists("batchjobitem"):
                columns = conn.execute(text("PRAGMA table_info('batchjobitem')")).fetchall()
                col_names = {row[1] for row in columns}
                if "attempts" not in col_names:
                    conn.execute(text("ALTER TABLE batchjobitem ADD COLUMN attempts INTEGER DEFAULT 0"))
                if "max_attempts" not in col_names:
                    conn.execute(text("ALTER TABLE batchjobitem ADD COLUMN max_attempts INTEGER DEFAULT 3"))
                if "next_run_at" not in col_names:
                    conn.execute(text("ALTER TABLE batchjobitem ADD COLUMN next_run_at TEXT"))
            conn.commit()
    except Exception:
        return

def get_session():
    with Session(engine) as session:
        yield session
