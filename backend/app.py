from flask import Flask, jsonify, redirect, request, g, url_for, make_response, session
from flask_cors import CORS
from backend.db import close_db, get_db
from backend.init_db import DatabaseInitializer  # aligned to renamed file
from backend.crud import CRUDManager
from backend.docs_registry import DOCS
from backend.auth import auth_bp  # <-- import your consolidated AUTH blueprint
from backend.crm import crm_bp   # <-- import your consolidated CRM blueprint
from dotenv import load_dotenv

load_dotenv(dotenv_path="C:/MyMVP/.env")
load_dotenv()


app = Flask(
    __name__,
    template_folder="../frontend/templates",
    static_folder="../frontend/static",
)



# Allow cookies for UI + headers for API (JWT/API key)
CORS(app, supports_credentials=True)

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(crm_bp)


@app.route("/")
def index():    
    return redirect(url_for("auth.index"))



# ============================================================
# DATABASE LIFECYCLE
# ============================================================
@app.teardown_appcontext
def teardown_db(exception):
    """Close DB connection after each request."""
    close_db(exception)


# ============================================================
# SCHEMAS (NO user_id — auto-bound in CRUDManager)
# Aligned to DB: prospect email/phone uniqueness is per user via DB index,
# not globally enforced here.
# ============================================================
prospects_schema = {
    "name": {"type": "str", "required": True, "max_length": 255},
    "website": {"type": "str", "required": False, "max_length": 500},
    "email": {"type": "str", "required": True, "max_length": 255},
    "phone": {"type": "str", "required": False, "max_length": 20},
    "pain": {"type": "str", "required": False, "max_length": 500},
    "pain_score": {"type": "int", "required": False, "min": 0, "max": 10},
    "status": {
        "type": "str",
        "required": True,
        "enum": ["new", "contacted", "qualified", "not_qualified", "won", "lost"]
    },
}

interactions_schema = {
    "prospect_id": {"type": "int", "required": True, "fk": ("prospects", "id")},
    "channel": {"type": "str", "required": True, "enum": ["email", "phone", "sms"]},
    "type": {"type": "str", "required": True, "enum": ["outbound", "inbound"]},
    "attempt_number": {"type": "int", "required": True, "min": 0},
    "content": {"type": "str", "required": True, "max_length": 2000},
    "response_type": {
        "type": "str",
        "required": False,
        "enum": ["opened", "clicked", "replied", "ignored"]
    },
    "success": {"type": "int", "required": False, "min": 0, "max": 1},
}

deals_schema = {
    "prospect_id": {"type": "int", "required": True, "fk": ("prospects", "id")},
    "deal_value": {"type": "real", "required": True, "min": 0},
    "stage": {
        "type": "str",
        "required": True,
        "enum": ["initiated", "negotiating", "closed", "won", "lost"]
    },
    "stage_reason": {"type": "str", "required": False, "max_length": 500},
}

payments_schema = {
    "deal_id": {"type": "int", "required": True, "fk": ("deals", "id")},
    "amount": {"type": "real", "required": True, "min": 0, "max": 1000000},
    "method": {
        "type": "str",
        "required": True,
        "enum": ["stripe", "api", "manual"]
    },
    "status": {
        "type": "str",
        "required": True,
        "enum": ["pending", "completed"]
    },
}

# ============================================================
# REGISTER CRUD ROUTES (CRUDManager auto-injects user_id from g.user)
# ============================================================
CRUDManager(app, "prospects", prospects_schema)
CRUDManager(app, "interactions", interactions_schema)
CRUDManager(app, "deals", deals_schema)
CRUDManager(app, "payments", payments_schema)


# ============================================================
# DOCUMENTATION
# ============================================================
@app.get("/docs")
def docs():
    return jsonify(DOCS), 200


@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


# ============================================================
# ERROR HANDLERS
# ============================================================
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "endpoint not found"}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "internal server error"}), 500


# ============================================================
# START SERVER
# ============================================================
if __name__ == "__main__":
    initializer = DatabaseInitializer()
    initializer.initialize()

    print("Starting Flask server...")
    print("API docs: http://localhost:5000/docs")
    print("Health: http://localhost:5000/health")

    app.run(debug=True, host="0.0.0.0", port=5000)
