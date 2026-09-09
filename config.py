import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Server Configuration
PORT = int(os.getenv("PORT", 5050))
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

# Ollama Endpoint Configuration
def _normalize_ollama_url() -> str:
    raw = os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST") or "http://127.0.0.1:11434"
    raw = raw.strip()
    if not raw.startswith("http://") and not raw.startswith("https://"):
        raw = f"http://{raw}"
    return raw.rstrip("/")

OLLAMA_BASE_URL = _normalize_ollama_url()
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:30b")
TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT", "10"))

# Advanced Ollama settings for /api/chat methods
OLLAMA_CONNECT_TIMEOUT = float(os.getenv("OLLAMA_CONNECT_TIMEOUT", "2.5"))
OLLAMA_READ_TIMEOUT = float(os.getenv("OLLAMA_READ_TIMEOUT", "90.0"))
OLLAMA_MAX_RETRIES = int(os.getenv("OLLAMA_MAX_RETRIES", "1"))
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "10m")
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "16384"))
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.1"))
OLLAMA_TOP_P = float(os.getenv("OLLAMA_TOP_P", "0.8"))
OLLAMA_CLASSIFIER_TEMPERATURE = float(os.getenv("OLLAMA_CLASSIFIER_TEMPERATURE", str(OLLAMA_TEMPERATURE)))
OLLAMA_RESPONSE_TEMPERATURE = float(os.getenv("OLLAMA_RESPONSE_TEMPERATURE", str(OLLAMA_TEMPERATURE)))

# Verified Company Context from https://www.keplertechllc.com/
DEFAULT_COMPANY_CONTEXT = {
    "company_name": "Kepler Tech LLC",
    "business_type": "Dubai's #1 Printer, Inkjet Media & Consumables Supplier & Authorized Distributor",
    "products_services": (
        "1. Large Format & Technical CAD Plotters: Epson SureColor T-Series (T3100, T5100, T3400, T5400) for AEC/CAD drawings.\n"
        "2. Professional Photo & Fine Art Printers: Epson SureColor P-Series (P700, P900, P7500, P9500) with UltraChrome PRO12 12-color ink systems.\n"
        "3. High-Speed Enterprise Office Printers: Epson WorkForce Enterprise (AM-C4000 40ppm, AM-C550 55ppm Heat-Free MFPs, WorkForce Pro WF-C879R with Replaceable Ink Pack System up to 86,000 pages).\n"
        "4. Dye-Sublimation Photo Printers: Citizen CX-02, CY-02, OP900II for event photography, photo booths, and studios.\n"
        "5. Premium Fine Art & Photo Media: Innova Art (IFA 11 Photo Cotton Rag 315gsm, IFA 13 Cold Press, IFA 22 Etching Rag), Olmec Photo Papers (OLM 68 Lustre, OLM 70 Pearl Premium 310gsm), Korejet rolls.\n"
        "6. Genuine Consumables: Epson UltraChrome Inks (700ml/350ml/110ml), Citizen photo ribbons/paper, Epson Maintenance Boxes.\n"
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
