from flask import Blueprint, request, jsonify,  g, render_template
import jwt
from backend.db import get_db
import random, secrets, datetime
from backend.helpers import (
    SECRET_KEY,
    hash_password,
    verify_password,
    generate_token,
    decode_token,
    parse_request_data,
    send_verification_email,
    check_forbidden,
    require_jwt,
    hash_api_key,
    token_required,
    generate_password_hash
)


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/index", methods=["GET"])
def index():
    return render_template("landing.html")


# ============================================================
# AUTH MIDDLEWARE — session cookie OR JWT OR API key
# ============================================================
@auth_bp.before_app_request
def load_user():
    """
    Attach g.user if request carries valid credentials.
    - JWT (Bearer token) for interactive sessions
    - API key (ApiKey <raw>) for programmatic access
    If neither is present or valid, g.user stays None.
    """
    g.user = None
    db = get_db()

    auth_header = request.headers.get("Authorization", "")

    # --- JWT path ---
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
        payload = decode_token(token)
        if payload:
            user = db.execute(
                "SELECT * FROM users WHERE id = ?", (payload.get("sub"),)
            ).fetchone()
            if user:
                g.user = user
        return  # stop here if JWT was processed

    # --- API key path (future use, independent) ---
    if auth_header.startswith("ApiKey "):
        raw_key = auth_header.split(" ", 1)[1]
        hashed = hash_api_key(raw_key)
        user = db.execute(
            "SELECT * FROM users WHERE api_key_hash = ? AND api_key_active = 1",
            (hashed,)
        ).fetchone()
        if user:
            # check expiry
            exp = user["api_key_expires_at"]
            if exp and datetime.datetime.utcnow() > datetime.datetime.fromisoformat(exp):
                user = None
        g.user = user
        return

    # --- No credentials ---
    # g.user remains None


@auth_bp.route("/signup", methods=["POST"])
def signup():
    data = parse_request_data(request)
    email = data.get("email")
    password = data.get("password")
    name = data.get("name")

    if not email or not password or not name:
        return jsonify({"error": "Missing fields"}), 400

    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        return jsonify({"error": "Email exists"}), 409

    # Generate OTP
    code = f"{random.randint(0, 999999):06d}"
    expires_at = (datetime.datetime.utcnow() + datetime.timedelta(minutes=10)).isoformat()

    # Insert all fields into email_codes
    db.execute("""
        INSERT OR REPLACE INTO email_codes (email, code, expires_at, name, password_hash)
        VALUES (?, ?, ?, ?, ?)
    """, (email, code, expires_at, name, hash_password(password)))
    db.commit()

        # Send verification email
    try:
        send_verification_email(email, code, expires_at)
    except Exception as e:
        return jsonify({"error": f"Failed to send verification email: {str(e)}"}), 500

    return jsonify(
        {
            "message": "Verification code sent. If you don’t see it in your inbox, please check your Spam folder.",
            "expires_at": expires_at
        }
    ), 200

@auth_bp.route("/signup", methods=["GET"])
def signup_page():
    return render_template("signup.html")



@auth_bp.route("/verify-code", methods=["POST"])
def verify_code():
    data = parse_request_data(request)
    email = data.get("email")
    code = data.get("code")

    if not email or not code:
        return jsonify({"error": "Email and code required"}), 400

    db = get_db()
    row = db.execute("SELECT code, expires_at, name, password_hash FROM email_codes WHERE email = ?", (email,)).fetchone()
    if not row or row["code"] != code:
        return jsonify({"error": "Invalid verification code"}), 403

    if datetime.datetime.utcnow() > datetime.datetime.fromisoformat(row["expires_at"]):
        return jsonify({"error": "Verification code expired"}), 403

    # Insert user now
    db.execute("INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
               (row["name"], email, row["password_hash"]))
    db.execute("DELETE FROM email_codes WHERE email = ?", (email,))
    db.commit()

    user = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()

    return jsonify({"message": "User created"}), 201

@auth_bp.route("/verify-code", methods=["GET"])
def validate_email_page():
    return render_template("validate email.html")

@auth_bp.route("/login", methods=["POST"])
def login():
    data = parse_request_data(request)
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Missing fields"}), 400

    forbidden = check_forbidden(email, "email")
    if forbidden:
        return jsonify({"error": "Forbidden characters in email"}), 400

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not user or not verify_password(user["password_hash"], password):
        return jsonify({"error": "Invalid credentials"}), 401

    token = generate_token(user["id"])
    return jsonify({"message": "Logged in successfully", "token": token}), 200

@auth_bp.route("/login", methods=["GET"])
def login_page():
    return render_template("login.html")

@auth_bp.route("/logout", methods=["POST"])
def logout():
    # Stateless logout: client discards token
    return jsonify({"message": "Logged out. Please discard your token client-side."}), 200


    # Stateless logout: client discards token
    return jsonify({"message": "Logged out (discard your token client-side)"}), 200


    data = parse_request_data(request)
    email = data.get("email")
    if not email:
        return jsonify({"error": "Email required"}), 400

    token = secrets.token_urlsafe(32)
    expires = datetime.datetime.utcnow() + datetime.timedelta(hours=1)

    db = get_db()
    db.execute("INSERT OR REPLACE INTO reset_tokens (email, token, expires_at) VALUES (?, ?, ?)",
               (email, token, expires.isoformat()))
    db.commit()

    reset_link = f"http://localhost:5000/auth/reset-page?token={token}"
    return jsonify({"message": "Reset link generated", "reset_link": reset_link}), 200
# -------------------
# Request password reset link (stateless)
# -------------------

@auth_bp.route("/request-reset", methods=["POST", "GET"])
def request_reset():
    if request.method == "GET":
        return render_template("forgot password.html")

    data = parse_request_data(request)
    email = data.get("email")
    if not email:
        return jsonify({"error": "Email required"}), 400

    db = get_db()
    user = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if not user:
        return jsonify({"error": "No account found with that email"}), 404

    # Use the user's id in the token
    expires = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
    exp_ts = int(expires.timestamp())
    remaining_seconds = exp_ts - int(datetime.datetime.utcnow().timestamp())
    remaining_minutes = remaining_seconds // 60
    remaining_hours = remaining_seconds // 3600

    payload = {"sub": str(user["id"]), "exp": exp_ts}
    reset_token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")

    reset_link = f"http://localhost:5000/auth/reset-password?token={reset_token}"

    try:
        send_verification_email(
            email,
            reset_link,
            f"{remaining_minutes} minutes (~{remaining_hours} hours)"
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({
        "message": "Reset link sent",
        "expires_at": exp_ts,
        "expires_in_minutes": remaining_minutes,
        "expires_in_hours": remaining_hours
    }), 200

@auth_bp.route("/reset-password", methods=["GET"])
def reset_password():
    return render_template("reset-password.html")


# -------------------
# Reset password with token (stateless)
# -------------------

@auth_bp.route("/reset", methods=["POST"])
def reset():
    data = parse_request_data(request)
    token = data.get("token")
    new_password = data.get("password")

    if not token or not new_password:
        return jsonify({"error": "Missing fields"}), 400

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expired"}), 403
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 403

    email = payload.get("sub")
    db = get_db()
    user = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if not user:
        return jsonify({"error": "User not found"}), 404

    hashed = generate_password_hash(new_password)
    db.execute("UPDATE users SET password_hash = ? WHERE email = ?", (hashed, email))
    db.commit()

    return jsonify({"message": "Password updated successfully"}), 200


@auth_bp.route("/debug-code", methods=["GET"])
def debug_code():
    email = request.args.get("email")
    db = get_db()
    row = db.execute("SELECT code FROM email_codes WHERE email = ?", (email,)).fetchone()
    if not row:
        return jsonify({"error": "No code"}), 404
    return jsonify({"code": row["code"]}), 200


@auth_bp.route("/generate-api-key", methods=["POST"])
@require_jwt
def generate_api_key():
    user = request.user
    raw_key = secrets.token_urlsafe(32)
    hashed = hash_api_key(raw_key)
    expires = datetime.datetime.utcnow() + datetime.timedelta(days=90)

    db = get_db()
    db.execute("UPDATE users SET api_key_hash = ?, api_key_expires_at = ?, api_key_active = 1 WHERE id = ?",
               (hashed, expires.isoformat(), user["id"]))
    db.commit()

    return jsonify({"message": "API key generated successfully", "api_key": raw_key, "expires_at": expires.isoformat()}), 200


@auth_bp.route("/resend-code", methods=["POST"])
def resend_code():
    data = parse_request_data(request)
    email = data.get("email")
    if not email:
        return jsonify({"error": "Email required"}), 400

    db = get_db()
    row = db.execute("SELECT email FROM email_codes WHERE email = ?", (email,)).fetchone()
    if not row:
        return jsonify({"error": "No signup record found for this email"}), 404

    code = f"{random.randint(0, 999999):06d}"
    expires_at = (datetime.datetime.utcnow() + datetime.timedelta(minutes=10)).isoformat()

    db.execute("""
        UPDATE email_codes SET code = ?, expires_at = ? WHERE email = ?
    """, (code, expires_at, email))
    db.commit()

    try:
        send_verification_email(email, code, expires_at)
    except Exception as e:
        return jsonify({"error": f"Failed to send verification email: {str(e)}"}), 500

    return jsonify({"message": "New code sent", "expires_at": expires_at}), 200


@auth_bp.route("/me", methods=["GET"])
@token_required
def me(current_user):
    return jsonify({
        "id": current_user["id"],
        "name": current_user["name"],
        "email": current_user["email"]
    }), 200
