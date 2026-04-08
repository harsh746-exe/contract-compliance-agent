"""Configuration settings for the Compliance Agent system."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# LLM Provider configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepinfra").strip().lower()

DEEPINFRA_API_KEY = os.getenv("DEEPINFRA_API_KEY", "") or os.getenv("DEEPIN_API_KEY", "")
DEEPINFRA_BASE_URL = os.getenv("DEEPINFRA_BASE_URL", "https://api.deepinfra.com/v1/openai")
DEEPINFRA_MODEL = os.getenv(
    "DEEPINFRA_MODEL",
    "meta-llama/Meta-Llama-3.1-70B-Instruct",
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

LLM_API_KEY = os.getenv(
    "LLM_API_KEY",
    DEEPINFRA_API_KEY if LLM_PROVIDER == "deepinfra" else OPENAI_API_KEY,
)
LLM_BASE_URL = os.getenv(
    "LLM_BASE_URL",
    DEEPINFRA_BASE_URL if LLM_PROVIDER == "deepinfra" else OPENAI_BASE_URL,
)
LLM_MODEL = os.getenv(
    "LLM_MODEL",
    DEEPINFRA_MODEL if LLM_PROVIDER == "deepinfra" else OPENAI_MODEL,
)

LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2000"))
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))
LLM_BACKOFF_BASE = float(os.getenv("LLM_BACKOFF_BASE", "2.0"))

# Orchestrator planning model.
# DeepInfra currently exposes Gemma 3 (`google/gemma-3-27b-it`) on the
# OpenAI-compatible endpoint, so this remains the default until Gemma 4 lands.
ORCHESTRATOR_LLM_PROVIDER = os.getenv("ORCHESTRATOR_LLM_PROVIDER", "google_gemma")
ORCHESTRATOR_MODEL = os.getenv("ORCHESTRATOR_MODEL", "google/gemma-3-27b-it")
ORCHESTRATOR_BASE_URL = os.getenv("ORCHESTRATOR_BASE_URL", "https://api.deepinfra.com/v1/openai")
ORCHESTRATOR_API_KEY = os.getenv("ORCHESTRATOR_API_KEY", DEEPINFRA_API_KEY)
ORCHESTRATOR_TEMPERATURE = float(os.getenv("ORCHESTRATOR_TEMPERATURE", "0.3"))
ORCHESTRATOR_MAX_TOKENS = int(os.getenv("ORCHESTRATOR_MAX_TOKENS", "1024"))

_DEFAULT_FAST_MODEL = OPENAI_MODEL if LLM_PROVIDER == "openai" else "meta-llama/Meta-Llama-3.1-8B-Instruct"
_DEFAULT_STANDARD_MODEL = OPENAI_MODEL if LLM_PROVIDER == "openai" else DEEPINFRA_MODEL
_DEFAULT_STRONG_MODEL = OPENAI_MODEL if LLM_PROVIDER == "openai" else DEEPINFRA_MODEL

LLM_TIERS = {
    "none": None,
    "fast": os.getenv("LLM_FAST_MODEL", _DEFAULT_FAST_MODEL),
    "standard": os.getenv("LLM_STANDARD_MODEL", _DEFAULT_STANDARD_MODEL),
    "strong": os.getenv("LLM_STRONG_MODEL", _DEFAULT_STRONG_MODEL),
}

# Document Processing
CHUNK_SIZE = 600
CHUNK_OVERLAP = 100
MAX_CHUNK_SIZE = 1000

# Vector Store
VECTOR_STORE_PATH = Path("data/vector_store")
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
TOP_K_RETRIEVAL = 5
BM25_TOP_K = int(os.getenv("BM25_TOP_K", "5"))
RERANK_TOP_K = int(os.getenv("RERANK_TOP_K", "5"))
RETRIEVAL_MAX_TOP_K = int(os.getenv("RETRIEVAL_MAX_TOP_K", "8"))

# Agent / skill configuration
REQUIREMENT_KEYWORDS = [
    "shall",
    "must",
    "required",
    "will",
    "responsible for",
    "ensure",
    "provide",
    "implement",
    "maintain",
    "establish",
]

CATEGORIES = [
    "obligations",
    "deliverables",
    "reporting",
    "confidentiality",
    "data_protection",
    "liability",
    "indemnity",
    "insurance",
    "termination",
    "dispute_resolution",
    "payment",
    "fees",
    "audit",
    "documentation",
    "timelines",
    "compliance",
]

COMPLIANCE_LABELS = [
    "compliant",
    "partial",
    "not_compliant",
    "not_addressed",
]

CONFIDENCE_HIGH = 0.75
CONFIDENCE_MEDIUM = 0.50
CONFIDENCE_LOW = 0.25
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", str(CONFIDENCE_HIGH)))

MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
QUERY_EXPANSION_ENABLED = os.getenv("QUERY_EXPANSION_ENABLED", "1") != "0"

# Agentic workflow configuration
EXECUTION_MODE = os.getenv("EXECUTION_MODE", "agentic").strip().lower()
AGENTIC_MAX_STEPS = int(os.getenv("AGENTIC_MAX_STEPS", "12"))
AGENTIC_MAX_ACTIONS = AGENTIC_MAX_STEPS
AGENTIC_MAX_ACTION_RETRIES = int(os.getenv("AGENTIC_MAX_ACTION_RETRIES", "2"))
MAX_REWRITE_ITERATIONS = int(os.getenv("MAX_REWRITE_ITERATIONS", "2"))

# Output Paths
OUTPUT_DIR = Path("output")
RESULTS_DIR = OUTPUT_DIR / "results"
LOGS_DIR = OUTPUT_DIR / "logs"
AGENTIC_RESULTS_DIR = OUTPUT_DIR / "agentic"
DEMO_CASES_DIR = OUTPUT_DIR / "demo_cases"
WORKFLOW_STATE_DIR = Path("data/workflow_state")
WORKFLOW_COMPLIANCE_STORE_DIR = Path("data/workflow_compliance_store")
RUN_STORE_DIR = Path("data/run_store")
SKILL_AUDIT_DIR = Path("data/skill_audit")

# Evaluation
GROUND_TRUTH_PATH = Path("data/ground_truth")
EVALUATION_OUTPUT = OUTPUT_DIR / "evaluation"

for directory in [
    OUTPUT_DIR,
    RESULTS_DIR,
    LOGS_DIR,
    AGENTIC_RESULTS_DIR,
    DEMO_CASES_DIR,
    WORKFLOW_STATE_DIR,
    WORKFLOW_COMPLIANCE_STORE_DIR,
    VECTOR_STORE_PATH,
    RUN_STORE_DIR,
    SKILL_AUDIT_DIR,
    EVALUATION_OUTPUT,
]:
    directory.mkdir(parents=True, exist_ok=True)
