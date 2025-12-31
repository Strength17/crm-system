# backend/crud.py
from flask import request, jsonify, g
from db import get_db
from docs_registry import DOCS
import re

# ============================================================
# SQL Injection Pattern
# ============================================================
SQL_INJECTION_PATTERN = re.compile(
    r"(;|--|\bDROP\b|\bDELETE\b|\bINSERT\b|\bUPDATE\b|\bALTER\b|\bCREATE\b|\))",
    re.IGNORECASE
)

def looks_like_sql_injection(value: str) -> bool:
    if not isinstance(value, str):
        return False
    return bool(SQL_INJECTION_PATTERN.search(value))


# ============================================================
# CRUD Manager (Multi‑Tenant Version)
# ============================================================
class CRUDManager:
    """
    Multi‑tenant CRUD manager.
    Automatically:
    - Requires authentication (g.user)
    - Injects user_id on CREATE
    - Filters all queries by user_id
    - Validates foreign keys with user_id
    - Prevents user_id from being provided manually
    """

    def __init__(self, app, table: str, schema: dict):
        self.app = app
        self.table = table
        self.schema = schema

        assert self.table in ["prospects", "interactions", "deals", "payments"], \
            f"Table '{self.table}' is not allowed"

        DOCS[table] = {
            "schema": schema,
            "endpoints": {
                "create": f"POST /{table}",
                "list": f"GET /{table}",
                "get": f"GET /{table}/{{id}}",
                "update": f"PUT /{table}/{{id}}",
                "delete": f"DELETE /{table}/{{id}}",
            },
        }

        self._register_routes()

    # ============================================================
    # Helpers
    # ============================================================
    def _table_columns(self):
        db = get_db()
        cur = db.execute(f"PRAGMA table_info({self.table})")
        return {row["name"] for row in cur.fetchall()}

    def _record_belongs_to_user(self, record_id: int) -> bool:
        """Check if record exists AND belongs to authenticated user."""
        db = get_db()
        cur = db.execute(
            f"SELECT 1 FROM {self.table} WHERE id = ? AND user_id = ?",
            (record_id, g.user["id"])
        )
        return cur.fetchone() is not None

    def _fk_exists(self, fk_table: str, fk_field: str, fk_value):
        """Foreign key must belong to same user."""
        db = get_db()
        cur = db.execute(
            f"SELECT 1 FROM {fk_table} WHERE {fk_field} = ? AND user_id = ?",
            (fk_value, g.user["id"])
        )
        return cur.fetchone() is not None

    def _is_int_strict(self, value) -> bool:
        return isinstance(value, int) and not isinstance(value, bool)

    def _is_real(self, value) -> bool:
        return (isinstance(value, (int, float))) and not isinstance(value, bool)

    def _bad_json_response(self):
        return jsonify({"errors": ["invalid or missing JSON body"]}), 400

    # ============================================================
    # Validation
    # ============================================================
    def validate_payload(self, payload: dict, is_update: bool, record_id: int | None):
        errors = []

        # Block user_id from being provided manually
        if "user_id" in payload:
            errors.append("user_id cannot be provided manually")

        # Unknown fields
        for field in payload.keys():
            if field not in self.schema:
                errors.append(f"unknown field '{field}'")

        # Required fields on create
        if not is_update:
            for field, rules in self.schema.items():
                if rules.get("required"):
                    if field not in payload or payload.get(field) is None:
                        errors.append(f"missing required field '{field}'")

        # Field validations
        for field, value in payload.items():
            rules = self.schema.get(field)
            if rules is None:
                continue

            # SQL injection protection
            if rules.get("type") == "str" and isinstance(value, str):
                if looks_like_sql_injection(value):
                    errors.append(f"field '{field}' contains forbidden characters or SQL patterns")

            expected_type = rules.get("type")
            if expected_type == "str":
                if not isinstance(value, str):
                    errors.append(f"field '{field}' must be string")
            elif expected_type == "int":
                if not self._is_int_strict(value):
                    errors.append(f"field '{field}' must be integer")
            elif expected_type == "real":
                if not self._is_real(value):
                    errors.append(f"field '{field}' must be number")
            else:
                errors.append(f"field '{field}' has unsupported type rule '{expected_type}'")

            # Max length
            if isinstance(value, str) and "max_length" in rules:
                if len(value) > rules["max_length"]:
                    errors.append(f"field '{field}' exceeds max length {rules['max_length']}")

            # Min/max numeric
            if (self._is_real(value) or self._is_int_strict(value)):
                if "min" in rules and value < rules["min"]:
                    errors.append(f"field '{field}' below minimum {rules['min']}")
                if "max" in rules and value > rules["max"]:
                    errors.append(f"field '{field}' above maximum {rules['max']}")

            # Enum
            if "enum" in rules and value is not None:
                if value not in rules["enum"]:
                    errors.append(f"field '{field}' must be one of {rules['enum']}")

            # Foreign key (must belong to same user)
            if "fk" in rules and value is not None:
                fk_table, fk_field = rules["fk"]
                if not self._fk_exists(fk_table, fk_field, value):
                    errors.append(f"invalid foreign key '{field}' → {fk_table}.{fk_field}")

            # Unique
            if rules.get("unique") and value not in (None, ""):
                db = get_db()
                if is_update and record_id is not None:
                    cur = db.execute(
                        f"SELECT id FROM {self.table} WHERE {field} = ? AND id <> ? AND user_id = ?",
                        (value, record_id, g.user["id"])
                    )
                else:
                    cur = db.execute(
                        f"SELECT id FROM {self.table} WHERE {field} = ? AND user_id = ?",
                        (value, g.user["id"])
                    )
                if cur.fetchone():
                    errors.append(f"field '{field}' must be unique")

        return errors

    # ============================================================
    # Routes
    # ============================================================
    def _register_routes(self):

        # ---------------- CREATE ----------------
        @self.app.post(f"/{self.table}", endpoint=f"{self.table}_create")
        def create_record():
            if g.user is None:
                return jsonify({"error": "Unauthorized"}), 401

            if not request.is_json:
                return self._bad_json_response()

            payload = request.get_json(silent=True)
            if payload is None or not isinstance(payload, dict):
                return self._bad_json_response()

            errors = self.validate_payload(payload, is_update=False, record_id=None)
            if errors:
                return jsonify({"errors": errors}), 400

            # Inject user_id
            payload["user_id"] = g.user["id"]

            db = get_db()
            fields = list(payload.keys())
            values = list(payload.values())
            placeholders = ["?"] * len(values)

            if "created_at" in self._table_columns():
                fields.append("created_at")
                placeholders.append("datetime('now')")

            sql_fields = ", ".join(fields)
            sql_values = ", ".join(placeholders)

            cur = db.execute(
                f"INSERT INTO {self.table} ({sql_fields}) VALUES ({sql_values})",
                values
            )
            db.commit()

            new_id = cur.lastrowid
            return jsonify({"id": new_id, **payload}), 201

        # ---------------- LIST ----------------
        @self.app.get(f"/{self.table}", endpoint=f"{self.table}_list")
        def list_records():
            if g.user is None:
                return jsonify({"error": "Unauthorized"}), 401

            db = get_db()
            cur = db.execute(
                f"SELECT * FROM {self.table} WHERE user_id = ?",
                (g.user["id"],)
            )
            rows = [dict(row) for row in cur.fetchall()]
            return jsonify(rows), 200

        # ---------------- GET ----------------
        @self.app.get(f"/{self.table}/<int:record_id>", endpoint=f"{self.table}_get")
        def get_record(record_id: int):
            if g.user is None:
                return jsonify({"error": "Unauthorized"}), 401

            db = get_db()
            cur = db.execute(
                f"SELECT * FROM {self.table} WHERE id = ? AND user_id = ?",
                (record_id, g.user["id"])
            )
            row = cur.fetchone()
            if not row:
                return jsonify({"error": f"{self.table} record not found"}), 404

            return jsonify(dict(row)), 200

        # ---------------- UPDATE ----------------
        @self.app.put(f"/{self.table}/<int:record_id>", endpoint=f"{self.table}_update")
        def update_record(record_id: int):
            if g.user is None:
                return jsonify({"error": "Unauthorized"}), 401

            if not self._record_belongs_to_user(record_id):
                return jsonify({"error": f"{self.table} record not found"}), 404

            if not request.is_json:
                return self._bad_json_response()

            payload = request.get_json(silent=True)
            if payload is None or not isinstance(payload, dict):
                return self._bad_json_response()

            if len(payload) == 0:
                return jsonify({"errors": ["empty update payload"]}), 400

            errors = self.validate_payload(payload, is_update=True, record_id=record_id)
            if errors:
                return jsonify({"errors": errors}), 400

            db = get_db()
            assignments = [f"{k} = ?" for k in payload.keys()]
            values = list(payload.values())

            if "updated_at" in self._table_columns():
                assignments.append("updated_at = datetime('now')")

            sql_assignments = ", ".join(assignments)
            values.append(record_id)

            db.execute(
                f"UPDATE {self.table} SET {sql_assignments} WHERE id = ? AND user_id = ?",
                values + [g.user["id"]]
            )
            db.commit()

            return jsonify({"id": record_id, **payload}), 200

        # ---------------- DELETE ----------------
        @self.app.delete(f"/{self.table}/<int:record_id>", endpoint=f"{self.table}_delete")
        def delete_record(record_id: int):
            if g.user is None:
                return jsonify({"error": "Unauthorized"}), 401

            if not self._record_belongs_to_user(record_id):
                return jsonify({"error": f"{self.table} record not found"}), 404

            db = get_db()
            db.execute(
                f"DELETE FROM {self.table} WHERE id = ? AND user_id = ?",
                (record_id, g.user["id"])
            )
            db.commit()

            return jsonify({"id": record_id, "deleted": True}), 200
