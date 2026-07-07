"""
AI学习助手 v2.0 — SQLite 数据库模块
替代 JSON 文件存储，支持并发读写、分页查询、数据统计
"""
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "app.db")


def get_db():
    """获取数据库连接（自动创建表）"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # 并发读写优化
    _init_tables(conn)
    return conn


def _init_tables(conn):
    """初始化表结构"""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mode TEXT NOT NULL,
            user_input TEXT NOT NULL,
            result TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS api_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT,
            endpoint TEXT,
            mode TEXT,
            prompt_length INTEGER,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_history_created ON history(created_at);
        CREATE INDEX IF NOT EXISTS idx_api_logs_ip ON api_logs(ip);
    """)


# ========== 历史记录 ==========
class HistoryDB:
    @staticmethod
    def add(mode, user_input, result):
        db = get_db()
        db.execute(
            "INSERT INTO history (mode, user_input, result) VALUES (?, ?, ?)",
            (mode, user_input[:500], result)
        )
        # 保留最近 500 条
        db.execute("DELETE FROM history WHERE id NOT IN (SELECT id FROM history ORDER BY id DESC LIMIT 500)")
        db.commit()
        db.close()

    @staticmethod
    def list(page=1, size=20):
        db = get_db()
        rows = db.execute(
            "SELECT * FROM history ORDER BY id DESC LIMIT ? OFFSET ?",
            (size, (page - 1) * size)
        ).fetchall()
        total = db.execute("SELECT COUNT(*) FROM history").fetchone()[0]
        db.close()
        return {"items": [dict(r) for r in rows], "total": total, "page": page}

    @staticmethod
    def get(history_id):
        db = get_db()
        row = db.execute("SELECT * FROM history WHERE id = ?", (history_id,)).fetchone()
        db.close()
        return dict(row) if row else None

    @staticmethod
    def clear():
        db = get_db()
        db.execute("DELETE FROM history")
        db.commit()
        db.close()


# ========== 提示词模板 ==========
class TemplateDB:
    @staticmethod
    def save(name, content):
        db = get_db()
        db.execute(
            "INSERT INTO templates (name, content, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(name) DO UPDATE SET content = excluded.content, updated_at = CURRENT_TIMESTAMP",
            (name, content)
        )
        db.commit()
        db.close()

    @staticmethod
    def list_all():
        db = get_db()
        rows = db.execute("SELECT * FROM templates ORDER BY updated_at DESC").fetchall()
        db.close()
        return {r["name"]: r["content"] for r in rows}

    @staticmethod
    def get(name):
        db = get_db()
        row = db.execute("SELECT * FROM templates WHERE name = ?", (name,)).fetchone()
        db.close()
        return dict(row) if row else None

    @staticmethod
    def delete(name):
        db = get_db()
        db.execute("DELETE FROM templates WHERE name = ?", (name,))
        db.commit()
        db.close()


# ========== API 调用日志 ==========
class ApiLogDB:
    @staticmethod
    def log(ip, endpoint, mode, prompt_length, status="success"):
        db = get_db()
        db.execute(
            "INSERT INTO api_logs (ip, endpoint, mode, prompt_length, status) VALUES (?, ?, ?, ?, ?)",
            (ip, endpoint, mode, prompt_length, status)
        )
        db.commit()
        db.close()

    @staticmethod
    def stats():
        """今日调用统计"""
        db = get_db()
        today = datetime.now().strftime("%Y-%m-%d")
        row = db.execute(
            "SELECT COUNT(*) as total, SUM(prompt_length) as chars FROM api_logs WHERE date(created_at) = ?",
            (today,)
        ).fetchone()
        per_mode = db.execute(
            "SELECT mode, COUNT(*) as cnt FROM api_logs WHERE date(created_at) = ? GROUP BY mode",
            (today,)
        ).fetchall()
        db.close()
        return {
            "today_total": row["total"] or 0,
            "today_chars": row["chars"] or 0,
            "by_mode": {r["mode"]: r["cnt"] for r in per_mode}
        }
