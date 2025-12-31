# database_initializer.py
import sqlite3
from contextlib import closing
from typing import Optional

DB_PATH = "mvp.db"

class DatabaseInitializer:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _exec(self, conn: sqlite3.Connection, sql: str, params: Optional[tuple] = None) -> None:
        with closing(conn.cursor()) as c:
            c.execute(sql, params or ())

    def create_tables(self, conn: sqlite3.Connection) -> None:
        # Users — api_key and session_token are NULLable; set after login
        self._exec(conn, """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            api_key_hash TEXT UNIQUE,          -- store only a hash of the API key
            api_key_expires_at TEXT,           -- ISO timestamp, e.g. 90 days from issue
            api_key_active INTEGER DEFAULT 0,  -- 1 = active, 0 = revoked/inactive
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)


        self._exec(conn, """
        CREATE TABLE IF NOT EXISTS prospects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            website TEXT,
            email TEXT NOT NULL,
            phone TEXT,
            pain TEXT,
            pain_score INTEGER CHECK(pain_score >= 0 AND pain_score <= 10),
            status TEXT NOT NULL CHECK(status IN ('new','contacted','qualified','not_qualified','won','lost')),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """)

        self._exec(conn, """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_prospects_user_email ON prospects(user_id, email);
        """)

        self._exec(conn, """
        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            prospect_id INTEGER NOT NULL,
            channel TEXT CHECK(channel IN ('email','phone','sms')),
            type TEXT CHECK(type IN ('outbound','inbound')),
            attempt_number INTEGER CHECK(attempt_number >= 0),
            content TEXT NOT NULL,
            response_type TEXT CHECK(response_type IN ('opened','clicked','replied','ignored')),
            success INTEGER CHECK(success IN (0,1)),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (prospect_id) REFERENCES prospects(id) ON DELETE CASCADE
        );
        """)

        self._exec(conn, """
        CREATE TABLE IF NOT EXISTS deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            prospect_id INTEGER NOT NULL,
            deal_value REAL NOT NULL CHECK(deal_value >= 0),
            stage TEXT NOT NULL CHECK(stage IN ('initiated','negotiating','closed','won','lost')),
            stage_reason TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (prospect_id) REFERENCES prospects(id) ON DELETE CASCADE
        );
        """)

        self._exec(conn, """
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            deal_id INTEGER NOT NULL,
            amount REAL NOT NULL CHECK(amount >= 0),
            method TEXT CHECK(method IN ('stripe','api','manual')),
            status TEXT CHECK(status IN ('pending','completed')),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (deal_id) REFERENCES deals(id) ON DELETE CASCADE
        );
        """)

        # Pre-signup email verification codes table (disposable)
        self._exec(conn, """
        CREATE TABLE IF NOT EXISTS email_codes (
            email TEXT PRIMARY KEY NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            password_hash TEXT,
            expires_at TEXT
        );
        """)


        # Indexes
        self._exec(conn, "CREATE INDEX IF NOT EXISTS idx_interactions_prospect_id ON interactions(prospect_id);")
        self._exec(conn, "CREATE INDEX IF NOT EXISTS idx_deals_prospect_id ON deals(prospect_id);")
        self._exec(conn, "CREATE INDEX IF NOT EXISTS idx_payments_deal_id ON payments(deal_id);")
        self._exec(conn, "CREATE INDEX IF NOT EXISTS idx_prospects_user_id ON prospects(user_id);")
        self._exec(conn, "CREATE INDEX IF NOT EXISTS idx_interactions_user_id ON interactions(user_id);")
        self._exec(conn, "CREATE INDEX IF NOT EXISTS idx_deals_user_id ON deals(user_id);")
        self._exec(conn, "CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id);")

        # Triggers to keep updated_at consistent
        self._exec(conn, """
        CREATE TRIGGER IF NOT EXISTS trg_prospects_set_updated_at
        AFTER UPDATE ON prospects
        FOR EACH ROW
        BEGIN
            UPDATE prospects SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
        END;
        """)
        self._exec(conn, """
        CREATE TRIGGER IF NOT EXISTS trg_deals_set_updated_at
        AFTER UPDATE ON deals
        FOR EACH ROW
        BEGIN
            UPDATE deals SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
        END;
        """)

    def initialize(self) -> None:
        conn = self.connect()
        try:
            self.create_tables(conn)
            conn.commit()
            print("Database initialized successfully with user authentication + CRM schema.")
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

if __name__ == "__main__":
    DatabaseInitializer().initialize()
