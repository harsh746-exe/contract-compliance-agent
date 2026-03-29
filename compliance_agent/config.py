"""Configuration settings for the Compliance Agent system (internal module)."""

import os
import sys
from pathlib import Path

# Try to import from root config, fallback to environment
try:
    # Add parent directory to path
    root_dir = Path(__file__).parent.parent
    sys.path.insert(0, str(root_dir))
    from config import *
except ImportError:
    # Fallback: load from environment and set defaults
    from dotenv import load_dotenv
    load_dotenv()
    
    # API Configuration
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview")
    
    # Document Processing
    CHUNK_SIZE = 600
    CHUNK_OVERLAP = 100
    MAX_CHUNK_SIZE = 1000
    
    # Vector Store
    VECTOR_STORE_PATH = Path("data/vector_store")
    EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
    TOP_K_RETRIEVAL = 5
    
    # Agent Configuration
    REQUIREMENT_KEYWORDS = [
        "shall", "must", "required", "will", "responsible for",
        "ensure", "provide", "implement", "maintain", "establish"
    ]
    
    CATEGORIES = [
        "obligations", "deliverables", "reporting", "confidentiality",
        "data_protection", "liability", "indemnity", "insurance",
        "termination", "dispute_resolution", "payment", "fees",
        "audit", "documentation", "timelines", "compliance"
    ]
    
    COMPLIANCE_LABELS = [
        "compliant", "partial", "not_compliant", "not_addressed"
    ]
    
    CONFIDENCE_HIGH = 0.75
    CONFIDENCE_MEDIUM = 0.50
    CONFIDENCE_LOW = 0.25
    
    MAX_RETRIES = 3
    QUERY_EXPANSION_ENABLED = True
    
    OUTPUT_DIR = Path("output")
    RESULTS_DIR = OUTPUT_DIR / "results"
    LOGS_DIR = OUTPUT_DIR / "logs"
    DEMO_CASES_DIR = OUTPUT_DIR / "demo_cases"
    
    OUTPUT_DIR.mkdir(exist_ok=True)
    RESULTS_DIR.mkdir(exist_ok=True)
    LOGS_DIR.mkdir(exist_ok=True)
    DEMO_CASES_DIR.mkdir(parents=True, exist_ok=True)
    VECTOR_STORE_PATH.mkdir(parents=True, exist_ok=True)
