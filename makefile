# ============================
# Makefile for MyMVP Backend
# ============================

PYTHON = python
VENV = env
VENV_BIN = $(VENV)/Scripts
ACTIVATE = $(VENV_BIN)/activate

BACKEND = backend
TEST_DIR = $(BACKEND)/tests

DB_PATH = mvp.db
INIT_DB = $(BACKEND)/init_db.py
CREATE_USER = $(BACKEND)/create_test_user.py

# ----------------------------
# Create virtual environment
# ----------------------------
venv:
    $(PYTHON) -m venv $(VENV)
    @echo "Virtual environment created."

# ----------------------------
# Install dependencies
# ----------------------------
install:
    $(VENV_BIN)/pip install -r requirements.txt
    @echo "Dependencies installed."

# ----------------------------
# Freeze dependencies
# ----------------------------
freeze:
    $(VENV_BIN)/pip freeze > requirements.txt
    @echo "requirements.txt updated."

# ----------------------------
# Run the backend server
# ----------------------------
run:
    $(VENV_BIN)/python $(BACKEND)/app.py

# ----------------------------
# Reset + recreate database
# ----------------------------
reset-db:
    @if exist $(DB_PATH) del $(DB_PATH)
    $(VENV_BIN)/python $(INIT_DB)
    @echo "Database reset and recreated."

# ----------------------------
# Create test user
# ----------------------------
create-user:
    $(VENV_BIN)/python $(CREATE_USER)

# ----------------------------
# Run all Postman tests
# ----------------------------
test:
    powershell -ExecutionPolicy Bypass -File run_tests.ps1

# ----------------------------
# Full setup (venv + install + db)
# ----------------------------
setup: venv install reset-db
    @echo "Environment fully set up."

# ----------------------------
# Clean environment
# ----------------------------
clean:
    @if exist $(VENV) rmdir /s /q $(VENV)
    @if exist $(DB_PATH) del $(DB_PATH)
    @echo "Environment cleaned."
