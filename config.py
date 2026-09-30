import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Server Configuration
PORT = int(os.getenv("PORT", 5055))
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

# Ollama Endpoint Configuration & Protocol Normalization
raw_ollama_url = os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST") or "http://127.0.0.1:11434"
raw_ollama_url = raw_ollama_url.strip().rstrip("/")
if not (raw_ollama_url.startswith("http://") or raw_ollama_url.startswith("https://")):
    raw_ollama_url = f"http://{raw_ollama_url}"

OLLAMA_BASE_URL = raw_ollama_url
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:32b")

APP_ENV = os.getenv("APP_ENV") or os.getenv("FLASK_ENV") or os.getenv("ENVIRONMENT") or "development"
IS_PRODUCTION = APP_ENV.lower() in ("production", "prod")

# Customer Authentication & Chat History Feature Flag (default False)
CUSTOMER_LOGIN_ENABLED = os.getenv("CUSTOMER_LOGIN_ENABLED", "False").lower() in ("true", "1", "yes")

# Security Configuration
DEFAULT_SECRET_KEYS = {
    "kepler-tech-salesai-default-secret-change-in-production",
    "dev-secret-key",
    "secret",
    "change-me",
    "changeme",
    "default",
    ""
}
SECRET_KEY = os.getenv("SECRET_KEY", "kepler-tech-salesai-default-secret-change-in-production")
CREDENTIAL_PEPPER = os.getenv("CREDENTIAL_PEPPER", "")
if not CREDENTIAL_PEPPER and not IS_PRODUCTION:
    CREDENTIAL_PEPPER = "kepler-default-dev-credential-pepper-12345"


def validate_secret_key(secret_key=None, app_env=None, debug=None):
    """
    Validates that SECRET_KEY and CREDENTIAL_PEPPER are set and non-default in production mode.
    Refuses startup if running in production with missing or default secret key.
    Logs warning if DEBUG=False but APP_ENV is not explicitly production.
    """
    key = secret_key if secret_key is not None else SECRET_KEY
    env = (app_env if app_env is not None else APP_ENV).lower()
    is_debug = debug if debug is not None else DEBUG
    if not is_debug and env not in ("production", "prod"):
        import logging
        logging.getLogger("config").warning(
            "APP_ENV not set to 'production' — security gates for production may not be active."
        )
    if env in ("production", "prod") and not is_debug:
        if not key or key.strip() in DEFAULT_SECRET_KEYS or len(key.strip()) < 16:
            raise RuntimeError(
                "CRITICAL SECURITY CONFIGURATION ERROR: "
                "Insecure or default SECRET_KEY detected in production mode. "
                "Refusing startup. Set a strong, non-default SECRET_KEY environment variable (minimum 16 characters)."
            )
        pepper = os.getenv("CREDENTIAL_PEPPER", "")
        if not pepper or len(pepper.strip()) < 16:
            raise RuntimeError(
                "CRITICAL SECURITY CONFIGURATION ERROR: "
                "Missing or insecure CREDENTIAL_PEPPER detected in production mode. "
                "Refusing startup. Set a strong, non-default CREDENTIAL_PEPPER environment variable (minimum 16 characters)."
            )
    return True


ALLOWED_MODELS = os.getenv(
    "ALLOWED_MODELS",
    "qwen2.5:32b,qwen2.5:14b,qwen2.5:0.5b,qwen3:30b,qwen3:14b,qwen3:8b,gpt-oss:20b,llama3.1:latest,llama3:latest"
).split(",")
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5050,http://127.0.0.1:5050,http://localhost:5055,http://127.0.0.1:5055,https://keplertech.ae"
).split(",")
MAX_REQUEST_BYTES = int(os.getenv("MAX_REQUEST_BYTES", 64 * 1024))
TIMEOUT_SECONDS = int(os.getenv("OLLAMA_TIMEOUT", "60"))

# Rate Limiting Configuration
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "True").lower() == "true"
RATE_LIMIT_IP_PER_MINUTE = int(os.getenv("RATE_LIMIT_IP_PER_MINUTE", "60"))
RATE_LIMIT_SESSION_PER_MINUTE = int(os.getenv("RATE_LIMIT_SESSION_PER_MINUTE", "30"))
RATE_LIMIT_LOGIN_ATTEMPTS = int(os.getenv("RATE_LIMIT_LOGIN_ATTEMPTS", "5"))
RATE_LIMIT_LOGIN_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_LOGIN_WINDOW_SECONDS", "300"))
TRUSTED_PROXY_COUNT = int(os.getenv("TRUSTED_PROXY_COUNT", "1"))
TRUST_CF_CONNECTING_IP = os.getenv("TRUST_CF_CONNECTING_IP", "True").lower() == "true"

# Logging & Response State Safety
LOG_SENSITIVE_DATA = os.getenv("LOG_SENSITIVE_DATA", "False").lower() == "true"
EXPOSE_DEBUG_STATE = os.getenv("EXPOSE_DEBUG_STATE", "False").lower() == "true" or DEBUG or (APP_ENV.lower() in ("test", "testing"))

# Ollama Readiness Policy
# If True: /health/ready returns 503 when Ollama is offline.
# If False: /health/ready returns 200 with status="degraded" when Ollama is offline but catalogue & persistence are ok.
OLLAMA_MANDATORY_FOR_READY = os.getenv("OLLAMA_MANDATORY_FOR_READY", "False").lower() == "true"


# Advanced Ollama settings for /api/chat methods
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "20.0"))
OLLAMA_CONNECT_TIMEOUT = float(os.getenv("OLLAMA_CONNECT_TIMEOUT", "2.5"))
OLLAMA_READ_TIMEOUT = float(os.getenv("OLLAMA_READ_TIMEOUT", str(LLM_TIMEOUT_SECONDS)))
OLLAMA_MAX_RETRIES = int(os.getenv("OLLAMA_MAX_RETRIES", "1"))
raw_keep_alive = os.getenv("OLLAMA_KEEP_ALIVE", "24h").strip()
OLLAMA_KEEP_ALIVE = -1 if raw_keep_alive in ("-1", "-1s") else raw_keep_alive
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "4096"))
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.0"))
OLLAMA_TOP_P = float(os.getenv("OLLAMA_TOP_P", "0.8"))
OLLAMA_CLASSIFIER_TEMPERATURE = float(os.getenv("OLLAMA_CLASSIFIER_TEMPERATURE", str(OLLAMA_TEMPERATURE)))
OLLAMA_RESPONSE_TEMPERATURE = float(os.getenv("OLLAMA_RESPONSE_TEMPERATURE", str(OLLAMA_TEMPERATURE)))


# Verified Company Context from https://www.keplertechllc.com/
DEFAULT_COMPANY_CONTEXT = {
    "company_name": "Kepler Tech LLC",
    "business_type": "Dubai's #1 Printer, Inkjet Media & Consumables Supplier & Authorized Distributor",
    "products_services": (
        "1. Large Format & Technical CAD Plotters: Epson SureColor T-Series (SC-T3100, SC-T3700, SC-T5100, SC-T5405, SC-T5700, SC-T7700) for AEC/CAD drawings.\n"
        "2. Professional Photo & Fine Art Printers: Epson SureColor P-Series (SC-P700, SC-P900, SC-P5300, SC-P6500, SC-P7500, SC-P8500, SC-P9500, SC-P20500) with UltraChrome PRO ink systems.\n"
        "3. High-Speed Enterprise Office Printers: Epson WorkForce Enterprise (AM-C4000, AM-C5000, AM-C6000, WF-C21000, AM-C400, AM-C550 Heat-Free MFPs, WorkForce Pro WF-C878R, WF-C879R, WF-C5890, EM-C800).\n"
        "4. Dye-Sublimation Photo Printers: Citizen CZ-01, CX-02, CY-02, CX-02W for event photography, photo booths, and studios.\n"
        "5. Premium Fine Art & Photo Media: Innova Art (IFA 11 Photo Cotton Rag 315gsm, IFA 13 Cold Press, IFA 22 Etching Rag), Olmec Photo Papers (OLM 68 Lustre, OLM 70 Pearl Premium 310gsm), Korejet rolls.\n"
        "6. Genuine Consumables: Epson UltraChrome Inks, Citizen photo ribbons/paper, Epson Maintenance Boxes.\n"
        "7. Print Workflow Software: Mirage by DINAX (official RIP & print workflow software), AirCastPro (wireless print server for events), Adobe learning solutions."
    ),
    "location": "D79, Khalid Bin Waleed Road, Office No. 1, Abdulla Al Awar Building, Dubai, United Arab Emirates (Fast delivery all over UAE and Middle East).",
    "working_hours": "Monday – Friday: 8:30 AM to 5:30 PM | Saturday: 8:30 AM to 1:00 PM | Sunday: Closed",
    "additional_info": (
        "- Official authorized partner for Epson, Citizen, Innova Art, Olmec, Mirage (Dinax), AirCastPro, and Adobe.\n"
        "- Contact numbers: +971 4 323 1008 | +971 55 835 8586 | Emails: info@keplertech.ae, sales@keplertech.ae.\n"
        "- Services include certified hardware delivery, on-site installation, operator training, warranty handling, and annual maintenance contracts (AMC).\n"
        "- Strictly adhering to commercial policy: all formal pricing, volume discounts, and quotations are handled directly by enterprise sales executives through sales@keplertech.ae."
    )
}
