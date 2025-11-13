import sqlite3
import os
import json
from pathlib import Path

class SettingsStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(os.path.dirname(self.db_path)).mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                label TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        try:
            cols = cur.execute("PRAGMA table_info(settings)").fetchall()
            if "label" not in {c[1] for c in cols}:
                cur.execute("ALTER TABLE settings ADD COLUMN label TEXT")
        except Exception:
            pass
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS card_layouts (
                container TEXT PRIMARY KEY,
                order_json TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS api_credentials (
                backend TEXT,
                exchange_type TEXT,
                api_key TEXT,
                api_secret TEXT,
                passphrase TEXT,
                testnet TEXT,
                is_demo TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        try:
            cols = cur.execute("PRAGMA table_info(api_credentials)").fetchall()
            names = {c[1] for c in cols}
            if "exchange_type" not in names:
                cur.execute("ALTER TABLE api_credentials ADD COLUMN exchange_type TEXT")
        except Exception:
            pass
        try:
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_api_credentials_exchange_type ON api_credentials(exchange_type)")
        except Exception:
            pass
        self.conn.commit()

    def get(self, key: str):
        try:
            cur = self.conn.cursor()
            cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cur.fetchone()
            return row[0] if row else None
        except Exception:
            return None

    def get_item(self, key: str):
        try:
            cur = self.conn.cursor()
            cur.execute("SELECT key, value, label FROM settings WHERE key = ?", (key,))
            row = cur.fetchone()
            if not row:
                return None
            return {"key": row[0], "value": row[1], "label": row[2]}
        except Exception:
            return None

    def list_settings(self):
        try:
            cur = self.conn.cursor()
            rows = cur.execute("SELECT key, value, label FROM settings").fetchall()
            return [{"key": r[0], "value": r[1], "label": r[2]} for r in rows]
        except Exception:
            return []

    def set(self, key: str, value: str, label: str = None):
        try:
            cur = self.conn.cursor()
            cur.execute(
                "INSERT INTO settings(key, value, label, updated_at) VALUES(?, ?, ?, CURRENT_TIMESTAMP) ON CONFLICT(key) DO UPDATE SET value=excluded.value, label=COALESCE(excluded.label, settings.label), updated_at=excluded.updated_at",
                (key, value, label)
            )
            self.conn.commit()
            return True
        except Exception:
            return False

    def set_label(self, key: str, label: str):
        try:
            cur = self.conn.cursor()
            cur.execute("UPDATE settings SET label = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?", (label, key))
            self.conn.commit()
            return True
        except Exception:
            return False

    def get_layouts(self):
        try:
            cur = self.conn.cursor()
            rows = cur.execute("SELECT container, order_json FROM card_layouts").fetchall()
            out = []
            for c, o in rows:
                try:
                    order = json.loads(o)
                except Exception:
                    order = []
                out.append({"container": c, "order": order})
            return out
        except Exception:
            return []

    def set_layout(self, container: str, order):
        try:
            ojson = json.dumps(order, ensure_ascii=False)
            cur = self.conn.cursor()
            cur.execute(
                "INSERT INTO card_layouts(container, order_json, updated_at) VALUES(?, ?, CURRENT_TIMESTAMP) ON CONFLICT(container) DO UPDATE SET order_json=excluded.order_json, updated_at=excluded.updated_at",
                (container, ojson)
            )
            self.conn.commit()
            return True
        except Exception:
            return False

    def get_credentials(self, exchange_type: str = None):
        try:
            cur = self.conn.cursor()
            if exchange_type:
                row = cur.execute(
                    "SELECT exchange_type, api_key, api_secret, passphrase, testnet, is_demo FROM api_credentials WHERE exchange_type = ?",
                    (exchange_type,)
                ).fetchone()
            else:
                row = cur.execute(
                    "SELECT exchange_type, api_key, api_secret, passphrase, testnet, is_demo FROM api_credentials ORDER BY updated_at DESC LIMIT 1"
                ).fetchone()
            if not row:
                return None
            return {
                "exchange_type": row[0] or "okx",
                "api_key": row[1] or "",
                "api_secret": row[2] or "",
                "passphrase": row[3] or "",
                "testnet": row[4] or "false",
                "is_demo": row[5] or "true",
            }
        except Exception:
            return None

    def set_credentials(self, exchange_type: str = "okx", api_key: str = "", api_secret: str = "", passphrase: str = "", testnet: str = "false", is_demo: str = "true"):
        try:
            cur = self.conn.cursor()
            cur.execute(
                "INSERT INTO api_credentials(exchange_type, api_key, api_secret, passphrase, testnet, is_demo, updated_at) VALUES(?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP) ON CONFLICT(exchange_type) DO UPDATE SET api_key=excluded.api_key, api_secret=excluded.api_secret, passphrase=excluded.passphrase, testnet=excluded.testnet, is_demo=excluded.is_demo, updated_at=excluded.updated_at",
                (exchange_type, api_key, api_secret, passphrase, testnet, is_demo)
            )
            self.conn.commit()
            return True
        except Exception:
            return False

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass
