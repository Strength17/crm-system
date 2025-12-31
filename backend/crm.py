from flask import Blueprint, render_template, request, jsonify
from db import get_db
from helpers import token_required, parse_request_data, check_forbidden
import re, sqlite3

crm_bp = Blueprint("crm", __name__, url_prefix="/crm")

# -------------------
# Global schema constraints
# -------------------
SCHEMA_CONSTRAINTS = {
    "prospects": {
        "status": ["new", "contacted", "qualified", "not_qualified", "won", "lost"]
    },
    "interactions": {
        "channel": ["email", "phone", "sms"],
        "type": ["outbound", "inbound"],
        "response_type": ["opened", "clicked", "replied", "ignored"],
        "success": [0, 1]
    },
    "deals": {
        "stage": ["initiated", "negotiating", "closed", "won", "lost"]
    },
    "payments": {
        "method": ["stripe", "api", "manual"],
        "status": ["pending", "completed"]
    }
}

# -------------------
# Dashboard
# -------------------
@crm_bp.route("/dashboard", methods=["GET"])
def dashboard():
    # Page shell only; data loaded via JS from /crm/dashboard-data
    return render_template("dashboard.html", active_page="dashboard")

@crm_bp.route("/dashboard-data", methods=["GET"])
@token_required
def dashboard_data(current_user):
    db = get_db()

    # Retrieve 'count' parameter from query string, make it required
    count = request.args.get("count", type=int)
    if count is None:
        # Optionally, you can handle missing 'count' here
        # For now, return an error or default to a value
        return jsonify({"error": "Missing 'count' parameter"}), 400

    # Total prospects count
    prospects_count = db.execute(
        "SELECT COUNT(*) AS c FROM prospects WHERE user_id = ?",
        (current_user["id"],)
    ).fetchone()["c"]

    # Deals referencing prospects with interactions (attempt_number > 0)
    deals_count = db.execute(
        """
        SELECT COUNT(DISTINCT d.id) AS c
        FROM deals d
        JOIN interactions i ON d.prospect_id = i.prospect_id
        WHERE d.user_id = ? AND i.attempt_number > 0
        """,
        (current_user["id"],)
    ).fetchone()["c"]

    # Sum of payment amounts where status is completed
    payments_total = db.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM payments
        WHERE user_id = ? AND status = 'completed'
        """,
        (current_user["id"],)
    ).fetchone()["total"]


    # Count of interactions with attempt_number > 0
    interactions_count = db.execute(
        "SELECT COUNT(*) AS c FROM interactions WHERE user_id = ? AND attempt_number > 0",
        (current_user["id"],)
    ).fetchone()["c"]

    # Fetch prospect details with limit
    prospects_details = db.execute(
        """
        SELECT id, name, website, email, phone, pain, pain_score, status
        FROM prospects
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (current_user["id"], count)
    ).fetchall()

    prospects_list = [dict(row) for row in prospects_details]

    return jsonify({
        "user": {
            "id": current_user["id"],
            "name": current_user["name"],
            "email": current_user["email"]
        },
        "counts": {
            "prospects": prospects_count,
            "interactions_attempted": interactions_count,
            "deals_attempted": deals_count,
            "payments_total": payments_total
        },
        "prospects": prospects_list
    }), 200

# -------------------
# Prospects
# -------------------
@crm_bp.route("/prospects", methods=["GET"])
def prospects_page():
    # Page shell only; table populated via JS from /crm/prospects-data
    return render_template("mvp-prospects.html", active_page="prospects")

@crm_bp.route("/prospects-data", methods=["GET"])
@token_required
def prospects_data(current_user):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM prospects WHERE user_id = ?",
        (current_user["id"],)
    ).fetchall()
    return jsonify([dict(row) for row in rows]), 200

@crm_bp.route("/prospects/<int:prospect_id>", methods=["POST"])
@token_required
def update_prospect(current_user, prospect_id):
    data = parse_request_data(request)
    name = data.get("name")
    website = data.get("website")
    email = data.get("email")
    phone = data.get("phone")
    pain = data.get("pain")
    pain_score = data.get("pain_score")
    status = data.get("status")

    # Validate required fields
    if not name:
        return jsonify({"error": "Missing required field: name"}), 400
    if not email:
        return jsonify({"error": "Missing required field: email"}), 400
    if not status:
        return jsonify({"error": "Missing required field: status"}), 400

    # Security regex patterns
    FORBIDDEN_PATTERN = re.compile(r"[;'\"]|--", re.IGNORECASE)
    SQL_KEYWORDS = re.compile(r"\b(OR|AND|DROP|SELECT|UNION|INSERT|DELETE)\b", re.IGNORECASE)
    EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

    # Validate name
    if FORBIDDEN_PATTERN.search(name) or SQL_KEYWORDS.search(name):
        return jsonify({"error": "Forbidden characters in name"}), 400

    # Validate email
    if not EMAIL_RE.match(email):
        return jsonify({"error": "Invalid email format"}), 400
    if FORBIDDEN_PATTERN.search(email) or SQL_KEYWORDS.search(email):
        return jsonify({"error": "Forbidden characters in email"}), 400

    # Validate status
    if status not in SCHEMA_CONSTRAINTS["prospects"]["status"]:
        return jsonify({"error": f"Invalid status '{status}'"}), 400

    # Validate optional fields if provided
    if website:
        if FORBIDDEN_PATTERN.search(website) or SQL_KEYWORDS.search(website):
            return jsonify({"error": "Forbidden characters in website"}), 400
    if phone:
        if FORBIDDEN_PATTERN.search(phone) or SQL_KEYWORDS.search(phone):
            return jsonify({"error": "Forbidden characters in phone"}), 400
    if pain:
        if FORBIDDEN_PATTERN.search(pain) or SQL_KEYWORDS.search(pain):
            return jsonify({"error": "Forbidden characters in pain"}), 400
    if pain_score is not None:
        try:
            pain_score = int(pain_score)
            if not (0 <= pain_score <= 10):
                return jsonify({"error": "pain_score must be between 0 and 10"}), 400
        except ValueError:
            return jsonify({"error": "pain_score must be an integer"}), 400

    db = get_db()

    # Verify ownership
    owner = db.execute(
        "SELECT id FROM prospects WHERE id = ? AND user_id = ?",
        (prospect_id, current_user["id"])
    ).fetchone()
    if not owner:
        return jsonify({"error": "Prospect not found or unauthorized"}), 404

    # Perform update
    db.execute(
        "UPDATE prospects SET name=?, website=?, email=?, phone=?, pain=?, pain_score=?, status=? WHERE id=? AND user_id=?",
        (name, website, email, phone, pain, pain_score, status, prospect_id, current_user["id"])
    )
    db.commit()

    # Return updated prospect info
    return jsonify({
        "id": prospect_id,
        "user_id": current_user["id"],
        "name": name,
        "website": website,
        "email": email,
        "phone": phone,
        "pain": pain,
        "pain_score": pain_score,
        "status": status
    }), 200


@crm_bp.route("/prospects/<int:prospect_id>", methods=["DELETE"])
@token_required
def delete_prospect(current_user, prospect_id):
    db = get_db()
    try:
        # Verify ownership
        owner = db.execute(
            "SELECT id FROM prospects WHERE id = ? AND user_id = ?",
            (prospect_id, current_user["id"])
        ).fetchone()

        if not owner:
            return jsonify({"error": "Prospect not found or unauthorized"}), 404

        db.execute("BEGIN")

        # Delete all interactions related to this prospect
        db.execute(
            "DELETE FROM interactions WHERE prospect_id = ? AND user_id = ?",
            (prospect_id, current_user["id"])
        )

        # Delete all deals related to this prospect
        db.execute(
            "DELETE FROM deals WHERE prospect_id = ? AND user_id = ?",
            (prospect_id, current_user["id"])
        )

        # Delete all payments tied to those deals
        db.execute(
            """
            DELETE FROM payments
            WHERE deal_id IN (
                SELECT id FROM deals WHERE prospect_id = ? AND user_id = ?
            )
            """,
            (prospect_id, current_user["id"])
        )

        # Delete the prospect itself
        db.execute(
            "DELETE FROM prospects WHERE id = ? AND user_id = ?",
            (prospect_id, current_user["id"])
        )

        db.commit()
        return jsonify({"message": "Prospect and all related data deleted successfully"}), 200

    except Exception as e:
        db.rollback()
        return jsonify({"error": "Deletion failed", "details": str(e)}), 500


# -------------------
# Interactions
# -------------------
@crm_bp.route("/interactions", methods=["GET"])
def interactions_page():
    return render_template("mvp-interactions.html", active_page="interactions")

@crm_bp.route("/interactions-data", methods=["GET"])
@token_required
def interactions_data(current_user):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM interactions i WHERE i.user_id = ?",
        (current_user["id"],)
    ).fetchall()
    return jsonify([dict(row) for row in rows]), 200

@crm_bp.route("/interactions/<int:interaction_id>", methods=["POST"])
@token_required
def update_interaction(current_user, interaction_id):
    data = parse_request_data(request)
    prospect_id = data.get("prospect_id")
    channel = data.get("channel")
    type_ = data.get("type")
    attempt_number = data.get("attempt_number")
    content = data.get("content")
    response_type = data.get("response_type")
    success = data.get("success")

    # Validate required fields
    if not prospect_id:
        return jsonify({"error": "Missing required field: prospect_id"}), 400
    if not channel:
        return jsonify({"error": "Missing required field: channel"}), 400
    if not type_:
        return jsonify({"error": "Missing required field: type"}), 400
    if attempt_number is None:
        return jsonify({"error": "Missing required field: attempt_number"}), 400
    if not content:
        return jsonify({"error": "Missing required field: content"}), 400

    # Validation checks (same as create route)
    forbidden = check_forbidden(content, "content")
    if forbidden: return forbidden

    if channel not in SCHEMA_CONSTRAINTS["interactions"]["channel"]:
        return jsonify({"error": f"Invalid channel '{channel}'. Must be one of {SCHEMA_CONSTRAINTS['interactions']['channel']}"}), 400
    if type_ not in SCHEMA_CONSTRAINTS["interactions"]["type"]:
        return jsonify({"error": f"Invalid type '{type_}'. Must be one of {SCHEMA_CONSTRAINTS['interactions']['type']}"}), 400
    if response_type not in SCHEMA_CONSTRAINTS["interactions"]["response_type"] and response_type is not None:
        return jsonify({"error": f"Invalid response_type '{response_type}'. Must be one of {SCHEMA_CONSTRAINTS['interactions']['response_type']}"}), 400
    if success not in SCHEMA_CONSTRAINTS["interactions"]["success"] and success is not None:
        return jsonify({"error": "Invalid success value. Must be 0 or 1"}), 400

    db = get_db()

    # Verify ownership
    owner = db.execute(
        "SELECT id FROM prospects WHERE id = ? AND user_id = ?",
        (prospect_id, current_user["id"])
    ).fetchone()
    if not owner:
        return jsonify({"error": "Prospect not found"}), 404

    # Perform update
    db.execute(
        "UPDATE interactions SET prospect_id=?, channel=?, type=?, attempt_number=?, content=?, response_type=?, success=? WHERE id=? AND user_id=?",
        (prospect_id, channel, type_, attempt_number, content, response_type, success, interaction_id, current_user["id"])
    )
    db.commit()

    # Return updated interaction
    return jsonify({
        "id": interaction_id,
        "user_id": current_user["id"],
        "prospect_id": prospect_id,
        "channel": channel,
        "type": type_,
        "attempt_number": attempt_number,
        "content": content,
        "response_type": response_type,
        "success": success
    }), 200


@crm_bp.route("/interactions/<int:interaction_id>", methods=["DELETE"])
@token_required
def delete_interaction(current_user, interaction_id):
    db = get_db()
    try:
        interaction = db.execute(
            "SELECT * FROM interactions WHERE id = ? AND user_id = ?",
            (interaction_id, current_user["id"])
        ).fetchone()

        if not interaction:
            return jsonify({"error": "Interaction not found or not authorized"}), 404

        prospect_id = interaction["prospect_id"]

        db.execute("BEGIN")

        # Delete interaction
        db.execute("DELETE FROM interactions WHERE id = ?", (interaction_id,))

        # Delete deals for this prospect
        db.execute("DELETE FROM deals WHERE prospect_id = ? AND user_id = ?", (prospect_id, current_user["id"]))

        # Delete payments tied to those deals
        db.execute("""
            DELETE FROM payments 
            WHERE deal_id IN (SELECT id FROM deals WHERE prospect_id = ? AND user_id = ?)
        """, (prospect_id, current_user["id"]))

        # Delete prospect
        db.execute("DELETE FROM prospects WHERE id = ? AND user_id = ?", (prospect_id, current_user["id"]))

        db.commit()
        return jsonify({"message": "Interaction and related data deleted successfully"}), 200

    except Exception as e:
        db.rollback()
        print(f"Error during delete operation for interaction {interaction_id}: {e}")
        return jsonify({"error": "Deletion failed", "details": str(e)}), 500

# -------------------
# Deals
# -------------------
@crm_bp.route("/deals", methods=["GET"])
def deals_page():
    return render_template("mvp-deals.html", active_page="deals")

@crm_bp.route("/deals-data", methods=["GET"])
@token_required
def deals_data(current_user):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM deals d WHERE d.user_id = ?",
        (current_user["id"],)
    ).fetchall()
    return jsonify([dict(row) for row in rows]), 200



@crm_bp.route("/deals/<int:deal_id>", methods=["DELETE"])
@token_required
def delete_deal(current_user, deal_id):
    db = get_db()
    try:
        deal = db.execute(
            "SELECT * FROM deals WHERE id = ? AND user_id = ?",
            (deal_id, current_user["id"])
        ).fetchone()

        if not deal:
            return jsonify({"error": "Deal not found or not authorized"}), 404

        prospect_id = deal["prospect_id"]

        db.execute("BEGIN")

        # Delete related payments
        db.execute(
            "DELETE FROM payments WHERE deal_id = ? AND user_id = ?",
            (deal_id, current_user["id"])
        )

        # Delete the deal itself
        db.execute(
            "DELETE FROM deals WHERE id = ? AND user_id = ?",
            (deal_id, current_user["id"])
        )

        # Check if prospect has any other deals left
        remaining_deals = db.execute(
            "SELECT COUNT(*) AS c FROM deals WHERE prospect_id = ? AND user_id = ?",
            (prospect_id, current_user["id"])
        ).fetchone()["c"]

        if remaining_deals == 0:
            # Delete interactions linked to the prospect
            db.execute(
                "DELETE FROM interactions WHERE prospect_id = ? AND user_id = ?",
                (prospect_id, current_user["id"])
            )
            # Delete the prospect itself
            db.execute(
                "DELETE FROM prospects WHERE id = ? AND user_id = ?",
                (prospect_id, current_user["id"])
            )

        db.commit()
        return jsonify({"message": "Deal and related data deleted successfully"}), 200

    except Exception as e:
        db.rollback()
        return jsonify({"error": "Deletion failed", "details": str(e)}), 500


@crm_bp.route("/deals/<int:deal_id>", methods=["POST"])
@token_required
def update_deal(current_user, deal_id):
    data = parse_request_data(request)
    # Example of fields that can be updated
    deal_value = data.get("deal_value")
    stage = data.get("stage")
    stage_reason = data.get("stage_reason")

    # Fetch existing deal to verify ownership
    db = get_db()
    deal = db.execute(
        "SELECT * FROM deals WHERE id = ? AND user_id = ?",
        (deal_id, current_user["id"])
    ).fetchone()
    if not deal:
        return jsonify({"error": "Deal not found or not authorized"}), 404

    # Prepare fields for update
    fields = []
    params = []

    if deal_value is not None:
        fields.append("deal_value = ?")
        params.append(deal_value)
    if stage is not None:
        # Validate stage if necessary
        if stage not in SCHEMA_CONSTRAINTS["deals"]["stage"]:
            return jsonify({"error": f"Invalid stage '{stage}'. Must be one of {SCHEMA_CONSTRAINTS['deals']['stage']}"}), 400
        fields.append("stage = ?")
        params.append(stage)
    if stage_reason is not None:
        forbidden = check_forbidden(stage_reason, "stage_reason")
        if forbidden:
            return forbidden
        fields.append("stage_reason = ?")
        params.append(stage_reason)

    if not fields:
        return jsonify({"error": "No valid fields to update"}), 400

    params.extend([deal_id, current_user["id"]])
    query = f"UPDATE deals SET {', '.join(fields)} WHERE id = ? AND user_id = ?"
    db.execute(query, (*params,))
    db.commit()

    return jsonify({"message": "Deal updated successfully"}), 200


# -------------------
# Payments
# -------------------
@crm_bp.route("/payments", methods=["GET"])
def payments_page():
    return render_template("mvp-payments.html", active_page="payments")

@crm_bp.route("/payments-data", methods=["GET"])
@token_required
def payments_data(current_user):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM payments pay WHERE pay.user_id = ?",
        (current_user["id"],)
    ).fetchall()
    return jsonify([dict(row) for row in rows]), 200


@crm_bp.route("/payments/<int:payment_id>", methods=["DELETE"])
@token_required
def delete_payment(current_user, payment_id):
    db = get_db()
    try:
        payment = db.execute(
            "SELECT * FROM payments WHERE id = ? AND user_id = ?",
            (payment_id, current_user["id"])
        ).fetchone()

        if not payment:
            return jsonify({"error": "Payment not found or not authorized"}), 404

        deal_id = payment["deal_id"]

        db.execute("BEGIN")

        # Delete the payment itself
        db.execute(
            "DELETE FROM payments WHERE id = ? AND user_id = ?",
            (payment_id, current_user["id"])
        )

        # Optionally cascade: delete the deal if no other payments remain
        remaining_payments = db.execute(
            "SELECT COUNT(*) AS c FROM payments WHERE deal_id = ? AND user_id = ?",
            (deal_id, current_user["id"])
        ).fetchone()["c"]

        if remaining_payments == 0:
            # Delete the deal
            db.execute(
                "DELETE FROM deals WHERE id = ? AND user_id = ?",
                (deal_id, current_user["id"])
            )

            # Check if prospect has other deals
            prospect_id = db.execute(
                "SELECT prospect_id FROM deals WHERE id = ? AND user_id = ?",
                (deal_id, current_user["id"])
            ).fetchone()

            if prospect_id:
                prospect_id = prospect_id["prospect_id"]
                remaining_deals = db.execute(
                    "SELECT COUNT(*) AS c FROM deals WHERE prospect_id = ? AND user_id = ?",
                    (prospect_id, current_user["id"])
                ).fetchone()["c"]

                if remaining_deals == 0:
                    # Delete interactions linked to the prospect
                    db.execute(
                        "DELETE FROM interactions WHERE prospect_id = ? AND user_id = ?",
                        (prospect_id, current_user["id"])
                    )
                    # Delete the prospect itself
                    db.execute(
                        "DELETE FROM prospects WHERE id = ? AND user_id = ?",
                        (prospect_id, current_user["id"])
                    )

        db.commit()
        return jsonify({"message": "Payment and related data deleted successfully"}), 200

    except Exception as e:
        db.rollback()
        return jsonify({"error": "Deletion failed", "details": str(e)}), 500


@crm_bp.route("/payments/<int:payment_id>", methods=["POST"])
@token_required
def update_payment(current_user, payment_id):
    data = parse_request_data(request)
    amount = data.get("amount")
    method = data.get("method")
    status = data.get("status")

    db = get_db()
    # Check if the payment exists and belongs to the current user
    payment = db.execute(
        "SELECT * FROM payments WHERE id = ? AND user_id = ?",
        (payment_id, current_user["id"])
    ).fetchone()
    if not payment:
        return jsonify({"error": "Payment not found or not authorized"}), 404

    # Prepare update fields
    fields = []
    params = []

    if amount is not None:
        fields.append("amount = ?")
        params.append(amount)
    if method is not None:
        forbidden = check_forbidden(method, "method")
        if forbidden:
            return forbidden
        if method not in SCHEMA_CONSTRAINTS["payments"]["method"]:
            return jsonify({"error": f"Invalid method '{method}'. Must be one of {SCHEMA_CONSTRAINTS['payments']['method']}"}), 400
        fields.append("method = ?")
        params.append(method)
    if status is not None:
        forbidden = check_forbidden(status, "status")
        if forbidden:
            return forbidden
        if status not in SCHEMA_CONSTRAINTS["payments"]["status"]:
            return jsonify({"error": f"Invalid status '{status}'. Must be one of {SCHEMA_CONSTRAINTS['payments']['status']}"}), 400
        fields.append("status = ?")
        params.append(status)

    if not fields:
        return jsonify({"error": "No valid fields to update"}), 400

    params.extend([payment_id, current_user["id"]])
    query = f"UPDATE payments SET {', '.join(fields)} WHERE id = ? AND user_id = ?"
    db.execute(query, (*params,))
    db.commit()

    return jsonify({"message": "Payment updated successfully"}), 200

# -------------------
# Add Business
# -------------------

# Page shell: loads the form
@crm_bp.route("/add-business", methods=["GET"])
def add_business_page():
    return render_template("add-business.html")

# Create route: seeds prospect + interaction + deal + payment
@crm_bp.route("/add-business", methods=["POST"])
@token_required
def add_business(current_user):
    data = parse_request_data(request)
    name = data.get("name")
    website = data.get("website", "")
    email = data.get("email")
    phone = data.get("phone", "")
    pain = data.get("pain", "")
    pain_score = data.get("pain_score", 5)
    status = data.get("status", "new")

    if not name or not email:
        return jsonify({"error": "Name and email are required"}), 400

    db = get_db()
    try:
        # 1. Prospect
        cur = db.execute(
            "INSERT INTO prospects (user_id, name, email, phone, website, status, pain, pain_score) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (current_user["id"], name, email, phone, website, status, pain, pain_score)
        )
        prospect_id = cur.lastrowid

        # 2. Interaction (default)
        cur = db.execute(
            "INSERT INTO interactions (user_id, prospect_id, channel, type, attempt_number, content, response_type, success) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (current_user["id"], prospect_id, "email", "outbound", 0, "Initial outreach", None, 0)
        )
        interaction_id = cur.lastrowid

        # 3. Deal (default)
        cur = db.execute(
            "INSERT INTO deals (user_id, prospect_id, deal_value, stage, stage_reason) VALUES (?, ?, ?, ?, ?)",
            (current_user["id"], prospect_id, 0, "initiated", "New business created")
        )
        deal_id = cur.lastrowid

        # 4. Payment (default)
        cur = db.execute(
            "INSERT INTO payments (user_id, deal_id, amount, method, status) VALUES (?, ?, ?, ?, ?)",
            (current_user["id"], deal_id, 0, "manual", "pending")
        )
        payment_id = cur.lastrowid

        db.commit()

    except sqlite3.IntegrityError:
        return jsonify({"error": "Business with this email already exists"}), 400

    return jsonify({
        "prospect_id": prospect_id,
        "interaction_id": interaction_id,
        "deal_id": deal_id,
        "payment_id": payment_id,
        "message": "Business created with default records"
    }), 201

# Optional: fetch all businesses for current user
@crm_bp.route("/businesses-data", methods=["GET"])
@token_required
def businesses_data(current_user):
    db = get_db()
    rows = db.execute(
        "SELECT id, name, email, phone, website, status, pain, pain_score "
        "FROM prospects WHERE user_id = ?",
        (current_user["id"],)
    ).fetchall()
    return jsonify([dict(row) for row in rows]), 200

