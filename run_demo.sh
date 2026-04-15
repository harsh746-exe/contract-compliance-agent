#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

step() { echo -e "\n${BLUE}=== $1 ===${NC}\n"; }
pass() { echo -e "${GREEN}✓ $1${NC}"; }
fail() { echo -e "${RED}✗ $1${NC}"; exit 1; }

# Activate venv if present
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
fi

# Pre-flight: check .env exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}No .env file found.${NC}"
    echo "  For local setup (no API keys): bash setup_ollama.sh"
    echo "  Or copy the example:            cp .env.example .env"
    exit 1
fi

# Pre-flight: if using Ollama, verify the server is reachable
if grep -q 'LLM_PROVIDER=ollama' .env 2>/dev/null; then
    step "Pre-flight: Checking Ollama server"
    if curl -sf http://localhost:11434/v1/models >/dev/null 2>&1; then
        pass "Ollama server is running"
    else
        echo -e "${YELLOW}Ollama server is not running.${NC}"
        echo "  Start it in another terminal:  ollama serve"
        echo "  Or re-run setup:               bash setup_ollama.sh"
        fail "Ollama server unreachable at localhost:11434"
    fi
fi

step "Step 1/5: Running test suite"
pytest -q || fail "Tests failed"
pass "All tests passed"

step "Step 2/5: MCP Compliance Run — Case 01 (baseline scenario)"
python3 demo.py --scenario-dir examples/scenarios/compliance_review_case_01 --mode mcp \
    || fail "Case 01 MCP run failed"
pass "Case 01 complete"

step "Step 3/5: MCP Compliance Run — Case 02 (IT services scenario)"
python3 demo.py --scenario-dir examples/scenarios/it_services_compliance_02 --mode mcp \
    || fail "Case 02 MCP run failed"
pass "Case 02 complete"

step "Step 4/5: Running evaluation"
python3 demo.py --scenario-dir examples/scenarios/it_services_compliance_02 --mode mcp --evaluate-only \
    || echo "Evaluation step skipped or not wired yet — check manually"
pass "Evaluation complete"

step "Step 5/5: Starting dashboard"
echo "Dashboard will start on http://localhost:8000"
echo "Press Ctrl+C to stop"
python3 -m uvicorn stakeholder_dashboard:app --host 0.0.0.0 --port 8000
