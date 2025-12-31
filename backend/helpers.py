from functools import wraps
from flask import request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
import jwt, datetime, re, os, secrets, hmac, hashlib
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from dotenv import load_dotenv
from db import get_db

load_dotenv()

# -------------------
# Email utilities   
# -------------------

import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

def send_verification_email(email, code, expires_at):
    from_name = os.getenv("APP_FROM_NAME", "SKY CRM")
    from_email = os.getenv("SMTP_FROM")
    api_key = os.getenv("SMTP_PASS")  # your SendGrid API key

    # Decide message type based on code format
    if code.isdigit() and len(code) == 6:
        # OTP style
        subject = f"Your Verification Code ~ {from_name}"
        body = f"Your verification code is {code}. It expires at {expires_at}."
    else:
        # Link style (reset password or similar)
        subject = f"Password Reset Link ~ {from_name}"
        body = (
            f"You requested a password reset.\n\n"
            f"Click the link below to reset your password.\n\n{code}\n\n"
            f"This link expires in {expires_at}."
        )


    message = Mail(
        from_email=f"{from_name} <{from_email}>",
        to_emails=email,
        subject=subject,
        plain_text_content=body
    )

    try:
        sg = SendGridAPIClient(api_key)
        response = sg.send(message)
        print(f"SendGrid response: {response.status_code}")
    except Exception as e:
        raise Exception(f"Failed to send email: {str(e)}")


FORBIDDEN_PATTERN = re.compile(r"[;'\"]|DROP\s+TABLE", re.IGNORECASE)

def check_forbidden(value, field_name):
    if value and FORBIDDEN_PATTERN.search(str(value)):
        return jsonify({"errors": [{"message": f"Forbidden characters in {field_name}"}]}), 400
    return None

# -------------------
# Password utilities
# -------------------
def hash_password(password: str) -> str:
    """Return a hashed password for storage."""
    return generate_password_hash(password)


def verify_password(stored_hash: str, candidate: str) -> bool:
    """Check a candidate password against stored hash."""
    return check_password_hash(stored_hash, candidate)


# -------------------
# Token utilities
# -------------------
SECRET_KEY = os.getenv("SECRET_KEY")

def generate_token(user_id, expires_hours=24):
    """Generate a JWT for a given user id."""
    expires = datetime.datetime.utcnow() + datetime.timedelta(hours=expires_hours)
    payload = {
        "sub": str(user_id),  # always store as string
        "exp": int(expires.timestamp())  # ✅ numeric timestamp
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token


def decode_token(token):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None



# -------------------
# Request parsing
# -------------------
def parse_request_data(request):
    """Support both JSON and form submissions."""
    if request.is_json:
        return request.get_json() or {}
    return request.form or {}


# -------------------
# Authentication decorator
# -------------------

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        db = get_db()
        current_user = None

        auth_header = request.headers.get("Authorization")
        if auth_header:
            # Case 1: Bearer JWT
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ", 1)[1]
                payload = decode_token(token)
                if payload:
                    user = db.execute(
                        "SELECT * FROM users WHERE id = ?", (payload["sub"],)
                    ).fetchone()
                    if user:
                        current_user = user
            else:
                # Case 2: raw API key
                raw_key = auth_header.strip()
                hashed = hash_api_key(raw_key)
                now = datetime.datetime.utcnow().isoformat()
                user = db.execute(
                    "SELECT * FROM users WHERE api_key_hash = ? AND api_key_active = 1 AND api_key_expires_at > ?",
                    (hashed, now)
                ).fetchone()
                if user:
                    current_user = user

        # Case 3: session fallback
        if not current_user and "user_id" in session:
            user = db.execute(
                "SELECT * FROM users WHERE id = ?", (session["user_id"],)
            ).fetchone()
            if user:
                current_user = user

        if not current_user:
            return jsonify({"errors": ["Authentication required"]}), 401

        return f(current_user, *args, **kwargs)
    return decorated


# Helper decorator to require JWT
def require_jwt(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Authorization header missing"}), 401

        token = auth_header.split(" ", 1)[1]
        payload = decode_token(token)
        if not payload:
            return jsonify({"error": "Invalid or expired token"}), 401

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE id = ?", (payload["sub"],)).fetchone()
        if not user:
            return jsonify({"error": "User not found"}), 404

        request.user = user
        return f(*args, **kwargs)
    return decorated

# -------------------
# API Key utilities
# -------------------

SERVER_SECRET = os.getenv("API_KEY_SECRET", "fallback")

def hash_api_key(raw_key: str) -> str:
    return hmac.new(SERVER_SECRET.encode(), raw_key.encode(), hashlib.sha256).hexdigest()

def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    return hmac.new(SERVER_SECRET.encode(), raw_key.encode(), hashlib.sha256).hexdigest() == stored_hash
