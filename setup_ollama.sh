#!/usr/bin/env bash
# ------------------------------------------------------------------
# setup_ollama.sh — One-command local setup for the Compliance Agent
#
# Run this after unzipping the project (no .venv or .env required).
# It installs Python dependencies, Ollama, pulls the required models,
# and generates a ready-to-use .env file.
#
# Usage:  bash setup_ollama.sh
# ------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC}  $1"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $1"; exit 1; }

OLLAMA_FAST_MODEL="llama3.2:3b"
OLLAMA_STANDARD_MODEL="llama3.1:8b"

# ------------------------------------------------------------------
# 1. Check Python
# ------------------------------------------------------------------
info "Checking Python installation..."
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")
        major=${ver%%.*}
        minor=${ver#*.}
        if [ "$major" -ge 3 ] && [ "$minor" -ge 9 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    fail "Python 3.9+ is required but not found. Please install Python first."
fi
ok "Found $PYTHON ($($PYTHON --version 2>&1))"

# ------------------------------------------------------------------
# 2. Create virtual environment and install dependencies
# ------------------------------------------------------------------
if [ ! -d ".venv" ]; then
    info "Creating virtual environment..."
    $PYTHON -m venv .venv
    ok "Virtual environment created at .venv/"
else
    ok "Virtual environment already exists"
fi

source .venv/bin/activate

info "Upgrading pip..."
pip install --upgrade pip --quiet

info "Installing Python dependencies (this may take a few minutes)..."
pip install -r requirements.txt --quiet
ok "Python dependencies installed"

info "Downloading spaCy language model..."
python -m spacy download en_core_web_sm --quiet 2>/dev/null || python -m spacy download en_core_web_sm
ok "spaCy model ready"

# ------------------------------------------------------------------
# 3. Install Ollama
# ------------------------------------------------------------------
info "Checking for Ollama..."

if command -v ollama &>/dev/null; then
    ok "Ollama is already installed ($(ollama --version 2>&1 || echo 'unknown version'))"
else
    info "Ollama not found. Installing..."
    OS="$(uname -s)"
    case "$OS" in
        Linux)
            info "Detected Linux — installing via official script..."
            curl -fsSL https://ollama.com/install.sh | sh
            ;;
        Darwin)
            if command -v brew &>/dev/null; then
                info "Detected macOS with Homebrew — installing via brew..."
                brew install ollama
            else
                info "Detected macOS — installing via official script..."
                curl -fsSL https://ollama.com/install.sh | sh
            fi
            ;;
        *)
            echo ""
            warn "Automatic Ollama installation is not supported on $OS."
            echo "  Please install Ollama manually from: https://ollama.com/download"
            echo "  Then re-run this script."
            exit 1
            ;;
    esac
    ok "Ollama installed"
fi

# ------------------------------------------------------------------
# 4. Start Ollama server (if not already running)
# ------------------------------------------------------------------
info "Ensuring Ollama server is running..."
if curl -sf http://localhost:11434/v1/models >/dev/null 2>&1; then
    ok "Ollama server is already running"
else
    info "Starting Ollama server in the background..."
    ollama serve &>/dev/null &
    OLLAMA_PID=$!

    for i in $(seq 1 15); do
        if curl -sf http://localhost:11434/v1/models >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done

    if curl -sf http://localhost:11434/v1/models >/dev/null 2>&1; then
        ok "Ollama server started (PID $OLLAMA_PID)"
    else
        fail "Could not start Ollama server. Try running 'ollama serve' manually in another terminal."
    fi
fi

# ------------------------------------------------------------------
# 5. Pull required models
# ------------------------------------------------------------------
echo ""
info "Pulling required models (this will download a few GB on first run)..."
echo ""

info "Pulling $OLLAMA_STANDARD_MODEL (~4.7 GB) — used for standard/strong tasks..."
ollama pull "$OLLAMA_STANDARD_MODEL"
ok "$OLLAMA_STANDARD_MODEL ready"

echo ""
info "Pulling $OLLAMA_FAST_MODEL (~2 GB) — used for fast tasks and orchestrator..."
ollama pull "$OLLAMA_FAST_MODEL"
ok "$OLLAMA_FAST_MODEL ready"

# ------------------------------------------------------------------
# 6. Generate .env file
# ------------------------------------------------------------------
if [ -f ".env" ]; then
    warn ".env file already exists — backing up to .env.backup"
    cp .env .env.backup
fi

cat > .env << 'ENVFILE'
# =============================================================
# Compliance Agent — Local Ollama Configuration
# Generated by setup_ollama.sh
# =============================================================

LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=llama3.1:8b

# Model tiers (all running locally via Ollama)
LLM_FAST_MODEL=llama3.2:3b
LLM_STANDARD_MODEL=llama3.1:8b
LLM_STRONG_MODEL=llama3.1:8b

# Orchestrator planner (uses the smaller/faster model)
ORCHESTRATOR_LLM_PROVIDER=ollama
ORCHESTRATOR_MODEL=llama3.2:3b
ORCHESTRATOR_BASE_URL=http://localhost:11434/v1

# Increase timeout for local inference (CPU can be slow)
LLM_TIMEOUT=120
ENVFILE

ok ".env file generated for Ollama"

# ------------------------------------------------------------------
# Done!
# ------------------------------------------------------------------
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Setup complete!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "  To run the demo:"
echo ""
echo "    source .venv/bin/activate"
echo "    bash run_demo.sh"
echo ""
echo "  Or run a single compliance check:"
echo ""
echo "    source .venv/bin/activate"
echo "    python3 demo.py --scenario-dir examples/scenarios/compliance_review_case_01 --mode mcp"
echo ""
echo "  To start the dashboard:"
echo ""
echo "    source .venv/bin/activate"
echo "    python3 -m uvicorn stakeholder_dashboard:app --host 0.0.0.0 --port 8000"
echo ""
echo -e "  ${YELLOW}Note:${NC} Make sure 'ollama serve' is running before starting."
echo "  The Ollama server was started by this script but will stop"
echo "  when you close this terminal. To keep it running, open a"
echo "  separate terminal and run: ollama serve"
echo ""
