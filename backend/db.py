# backend/db.py

import sqlite3
from flask import g

DB_PATH = "mvp.db"

def get_db():
    """Return a request-scoped database connection."""
    if "database" not in g:
        g.database = sqlite3.connect(DB_PATH)
        g.database.row_factory = sqlite3.Row
        g.database.execute("PRAGMA foreign_keys = ON;")
    return g.database

def close_db(error=None):
    """Close database connection automatically after request."""
    db = g.pop("database", None)
    if db is not None:
        db.close()
