"""Configuration settings for the Compliance Agent system."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# API Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview")

# Document Processing
CHUNK_SIZE = 600  # tokens
CHUNK_OVERLAP = 100  # tokens
MAX_CHUNK_SIZE = 1000  # tokens

# Vector Store
VECTOR_STORE_PATH = Path("data/vector_store")
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
TOP_K_RETRIEVAL = 5  # Number of evidence chunks to retrieve per requirement

# Agent Configuration
REQUIREMENT_KEYWORDS = [
    "shall", "must", "required", "will", "responsible for",
    "ensure", "provide", "implement", "maintain", "establish"
]

# Generic contract/policy categories (domain-agnostic)
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

# Compliance Decision Rubric
COMPLIANCE_LABELS = [
    "compliant",
    "partial",
    "not_compliant",
    "not_addressed"
]

# Confidence Thresholds
CONFIDENCE_HIGH = 0.75
CONFIDENCE_MEDIUM = 0.50
CONFIDENCE_LOW = 0.25

# Retry Configuration
MAX_RETRIES = 3
QUERY_EXPANSION_ENABLED = True

# Output Paths
OUTPUT_DIR = Path("output")
RESULTS_DIR = OUTPUT_DIR / "results"
LOGS_DIR = OUTPUT_DIR / "logs"
AGENTIC_RESULTS_DIR = OUTPUT_DIR / "agentic"
DEMO_CASES_DIR = OUTPUT_DIR / "demo_cases"
WORKFLOW_STATE_DIR = Path("data/workflow_state")
WORKFLOW_COMPLIANCE_STORE_DIR = Path("data/workflow_compliance_store")

# Create directories
OUTPUT_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
AGENTIC_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
DEMO_CASES_DIR.mkdir(parents=True, exist_ok=True)
WORKFLOW_STATE_DIR.mkdir(parents=True, exist_ok=True)
WORKFLOW_COMPLIANCE_STORE_DIR.mkdir(parents=True, exist_ok=True)
VECTOR_STORE_PATH.mkdir(parents=True, exist_ok=True)

# Evaluation
GROUND_TRUTH_PATH = Path("data/ground_truth")
EVALUATION_OUTPUT = OUTPUT_DIR / "evaluation"

# Agentic workflow configuration
AGENTIC_MAX_STEPS = 12
AGENTIC_MAX_ACTION_RETRIES = 2
