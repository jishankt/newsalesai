"""
Embedding-Based Semantic Understanding for Kepler Tech SalesAI.

Uses dense vector embeddings (via Ollama nomic-embed-text / bge-m3) to:
1. Semantically classify customer intent against labelled intent prototypes.
2. Semantically match customer natural-language requirements to catalog products.
3. Extract customer information (name, phone, email) using the LLM when regex fails.

This module sits ABOVE the deterministic regex layer — it fills in the gaps
for conversational, ambiguous, or multi-lingual input that regex cannot handle.
"""

from __future__ import annotations

import logging
import time
import re
from typing import Dict, Any, List, Optional, Tuple
import numpy as np

logger = logging.getLogger("nlp.semantic_understanding")

# ── Intent Prototypes (labelled exemplar sentences for each intent) ──────────
# Each entry: (intent_label, requested_action, list_of_exemplar_sentences)
# The embedding engine encodes all exemplars once (cached). Customer messages
# are matched via cosine similarity against this prototype matrix.

INTENT_PROTOTYPES: List[Tuple[str, str, List[str]]] = [
    ("greeting", "respond_socially", [
        "hello", "hi there", "good morning", "hey how are you",
        "good afternoon", "greetings", "howdy", "hey", "hi"
    ]),
    ("product_discovery", "ask_qualification_question", [
        "I need a printer", "looking for a plotter", "I want to buy a printer",
        "recommend me a printer", "which printer should I buy",
        "I am searching for a large format printer",
        "can you suggest a printer for CAD drawings",
        "I need something to print architectural blueprints",
        "show me options for photo printing",
        "I want to print t-shirts", "we need a sublimation printer",
        "what printers do you have for office use",
        "I need a copier for our office",
        "looking for an A0 plotter", "need something that prints A4 documents",
        "what are my options for a photo booth printer",
    ]),
    ("product_question", "answer_product_attribute", [
        "what is the print speed of the T3100",
        "does the P900 have a scanner",
        "how wide can the T5100 print",
        "what resolution does the CX-02 print at",
        "does this printer support wifi",
        "what ink does the P700 use",
        "how much does the AM-C4000 weigh",
        "can the SC-F500 print on t-shirts",
        "what paper sizes does this support",
        "tell me more about this product",
        "show me the specifications",
        "what are the dimensions",
        "how much memory does it have",
    ]),
    ("product_comparison", "compare_products", [
        "compare T3100 and T5100", "what is the difference between CX-02 and CY-02",
        "T3100 vs T5100", "which is better the P700 or P900",
        "CX-02 versus CY-02 which one should I choose",
        "what are the differences between these two printers",
        "compare the two models", "how do these printers compare",
        "which one has better speed", "which model is more affordable",
        "what's the difference between both",
    ]),
    ("consumables_query", "show_consumables", [
        "what ink does the T3100 use", "I need cartridges for my Epson",
        "which ink cartridges are compatible", "show me consumables",
        "how much does the ink cost", "I need to order replacement ribbons",
        "what maintenance box do I need", "compatible ink for SC-P900",
        "photo paper for the CX-02", "media for the printer",
        "which inks are available", "I need ribbon for my Citizen printer",
        "what cartridges fit my machine", "show ink options",
    ]),
    ("correction", "acknowledge_correction", [
        "actually I meant A0 not A1", "sorry I was wrong",
        "I made a mistake", "no I meant the 36 inch one",
        "correction: I need without scanner", "I changed my mind",
        "actually I don't need a scanner", "no wait, I want the bigger one",
        "my bad, I meant 60 prints per day not 600",
        "I said wrong number", "let me correct that",
    ]),
    ("confirmation", "continue_qualification", [
        "yes", "yes please", "that's correct", "sure", "ok that works",
        "sounds good", "yes I agree", "correct", "confirmed", "yep",
        "that is right", "yes with scanner", "yes I want that one",
    ]),
    ("rejection", "continue_qualification", [
        "no", "no thanks", "I don't want that", "not this one",
        "that doesn't work for me", "no scanner please",
        "I'd rather not", "nope", "that's not what I need",
        "not interested", "without scanner", "print only",
    ]),
    ("business_information", "provide_business_info", [
        "where is your office", "what are your working hours",
        "how can I contact you", "what is your phone number",
        "do you deliver to Abu Dhabi", "what is your email address",
        "where are you located", "do you have a showroom",
        "what brands do you carry", "are you open on Saturday",
        "how do I reach your sales team",
    ]),
    ("customer_introduction", "respond_socially", [
        "my name is Ahmed", "I am Mohammed from Dubai",
        "this is Sara speaking", "I'm John and I need a printer",
        "my name is Hassan, I need a quote",
        "hello my name is Fatima", "I am calling from XYZ company",
        "name is Kumar", "I'm from ABC trading company",
    ]),
    ("conversation_ending", "respond_socially", [
        "thank you", "thanks for your help", "bye", "goodbye",
        "that's all I needed", "have a good day", "cheers",
        "thanks, I'll be in touch", "okay thank you",
    ]),
    ("troubleshooting", "provide_support", [
        "my printer has a paper jam", "the print quality is bad",
        "there are lines on my prints", "the printer is not working",
        "it shows an error", "the printhead is clogged",
        "printer is offline", "ink is not flowing properly",
        "banding on my prints", "the printer stopped mid job",
    ]),
]


class SemanticIntentClassifier:
    """
    Classifies customer intent using embedding cosine similarity.

    On first call, encodes all intent prototype sentences into a matrix.
    Each customer message is then embedded and compared via dot product
    against the prototype matrix — no regex or keyword needed.

    Falls back gracefully if the embedding model is unavailable.
    """

    _instance: Optional["SemanticIntentClassifier"] = None

    def __init__(self):
        self._proto_matrix: Optional[np.ndarray] = None
        self._proto_labels: List[str] = []
        self._proto_actions: List[str] = []
        self._proto_texts: List[str] = []
        self._is_built = False
        self._build_attempted = False

    @classmethod
    def get(cls) -> "SemanticIntentClassifier":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _build_index(self) -> bool:
        """Encodes all prototype sentences and builds the similarity matrix."""
        if self._build_attempted:
            return self._is_built
        self._build_attempted = True
        try:
            from rag.embeddings_engine import embeddings_engine
            if not embeddings_engine.is_available():
                logger.info("SemanticIntentClassifier: embedding model offline, operating in regex-only mode.")
                return False

            texts: List[str] = []
            labels: List[str] = []
            actions: List[str] = []

            for intent_label, action, exemplars in INTENT_PROTOTYPES:
                for ex in exemplars:
                    texts.append(ex)
                    labels.append(intent_label)
                    actions.append(action)

            logger.info(f"SemanticIntentClassifier: encoding {len(texts)} prototype sentences…")
            t0 = time.time()
            matrix = embeddings_engine.embed_batch(texts)
            if matrix is None or matrix.shape[0] != len(texts):
                logger.warning("SemanticIntentClassifier: prototype embedding failed.")
                return False

            self._proto_matrix = matrix
            self._proto_labels = labels
            self._proto_actions = actions
            self._proto_texts = texts
            self._is_built = True
            logger.info(f"SemanticIntentClassifier: index built in {time.time()-t0:.2f}s ({len(texts)} prototypes).")
            return True

        except Exception as e:
            logger.warning(f"SemanticIntentClassifier build error: {e}")
            return False

    def classify(
        self,
        customer_message: str,
        top_k: int = 3,
        min_confidence: float = 0.55,
    ) -> Optional[Dict[str, Any]]:
        """
        Classifies customer_message semantically.

        Returns dict with keys:
          intent, requested_action, confidence, top_matches
        or None if model unavailable or confidence too low.
        """
        if not self._build_index():
            return None

        try:
            from rag.embeddings_engine import embeddings_engine
            q_vec = embeddings_engine.embed_text(customer_message)
            if q_vec is None:
                return None

            # Cosine similarity (vectors are L2-normalised, so dot = cosine)
            scores = np.dot(self._proto_matrix, q_vec)  # (N,)

            top_indices = np.argsort(scores)[::-1][:top_k * 3]

            # Aggregate by intent label (take max score per label)
            label_scores: Dict[str, float] = {}
            label_actions: Dict[str, str] = {}
            label_best_text: Dict[str, str] = {}
            for idx in top_indices:
                lbl = self._proto_labels[idx]
                sc = float(scores[idx])
                if lbl not in label_scores or sc > label_scores[lbl]:
                    label_scores[lbl] = sc
                    label_actions[lbl] = self._proto_actions[idx]
                    label_best_text[lbl] = self._proto_texts[idx]

            sorted_labels = sorted(label_scores.items(), key=lambda x: -x[1])
            best_label, best_score = sorted_labels[0]

            if best_score < min_confidence:
                logger.debug(
                    f"SemanticClassifier: low confidence {best_score:.3f} for '{customer_message[:60]}' "
                    f"→ best intent={best_label}"
                )
                return None

            top_matches = [
                {"intent": lbl, "action": label_actions[lbl], "score": round(sc, 3),
                 "nearest_prototype": label_best_text.get(lbl, "")}
                for lbl, sc in sorted_labels[:top_k]
            ]

            logger.info(
                f"SemanticClassifier: '{customer_message[:60]}' → intent={best_label} "
                f"confidence={best_score:.3f}"
            )
            return {
                "intent": best_label,
                "requested_action": label_actions[best_label],
                "confidence": round(best_score, 3),
                "top_matches": top_matches,
            }

        except Exception as e:
            logger.warning(f"SemanticIntentClassifier.classify error: {e}")
            return None


class SemanticRequirementsExtractor:
    """
    Uses embedding similarity to match a customer's freeform requirement
    description against a structured set of requirements (paper sizes,
    applications, scanner needs, volume ranges etc).

    This gives the system semantic understanding of statements like:
      "I need to print large drawings for my construction team"
        → application=architecture/CAD, print_width=36
    without needing rigid regex patterns.
    """

    # Requirement categories with prototype sentences
    _REQUIREMENT_PROTOTYPES = {
        "application:architecture_cad": [
            "architectural drawings", "engineering blueprints", "CAD drawings",
            "technical drawings", "construction plans", "GIS maps",
            "floor plans", "structural drawings", "plot plans",
        ],
        "application:photography": [
            "professional photography", "fine art printing", "gallery prints",
            "exhibition photos", "portrait printing", "landscape photography",
            "giclee prints",
        ],
        "application:photo_booth": [
            "photo booth", "event photography", "instant photo printing",
            "wedding photos", "party photos", "event instant prints",
        ],
        "application:office": [
            "office documents", "business reports", "A4 office printing",
            "A3 office printing", "enterprise documents", "business printing",
            "multi-function office printer",
        ],
        "application:dye_sublimation": [
            "t-shirt printing", "mug printing", "sublimation printing",
            "textile printing", "merchandise printing", "garment printing",
            "sportswear printing",
        ],
        "size:a4": [
            "A4 size", "letter size", "standard paper", "A4 documents",
            "small format", "desktop printer",
        ],
        "size:a3": [
            "A3 size", "tabloid size", "A3 printing", "A3+ printing",
        ],
        "size:a1_24inch": [
            "A1 size", "24 inch wide", "24 inch printer",
            "A1 drawings", "24 inch plotter",
        ],
        "size:a0_36inch": [
            "A0 size", "36 inch wide", "36 inch printer",
            "A0 drawings", "36 inch plotter", "full size drawings",
        ],
        "size:44inch": [
            "44 inch wide", "44 inch printer", "44 inch plotter",
            "extra wide format",
        ],
        "scanner:yes": [
            "with integrated scanner", "printer with scanner",
            "multi-function with scanning", "MFP with scan",
            "need scanning capability", "print and scan",
        ],
        "scanner:no": [
            "print only", "no scanner needed", "without scanner",
            "just printing", "only print", "printer only",
        ],
        "volume:low": [
            "a few prints per day", "5 to 20 prints daily",
            "light usage", "occasional printing", "small volume",
        ],
        "volume:medium": [
            "50 to 100 prints daily", "moderate volume", "medium workload",
            "regular office printing", "daily moderate prints",
        ],
        "volume:high": [
            "hundreds of prints per day", "high volume", "production printing",
            "large workload", "commercial volume", "heavy duty printing",
        ],
    }

    _instance: Optional["SemanticRequirementsExtractor"] = None

    def __init__(self):
        self._matrix: Optional[np.ndarray] = None
        self._keys: List[str] = []
        self._texts: List[str] = []
        self._is_built = False
        self._build_attempted = False

    @classmethod
    def get(cls) -> "SemanticRequirementsExtractor":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _build_index(self) -> bool:
        if self._build_attempted:
            return self._is_built
        self._build_attempted = True
        try:
            from rag.embeddings_engine import embeddings_engine
            if not embeddings_engine.is_available():
                return False

            texts: List[str] = []
            keys: List[str] = []

            for req_key, exemplars in self._REQUIREMENT_PROTOTYPES.items():
                for ex in exemplars:
                    texts.append(ex)
                    keys.append(req_key)

            matrix = embeddings_engine.embed_batch(texts)
            if matrix is None or matrix.shape[0] != len(texts):
                return False

            self._matrix = matrix
            self._keys = keys
            self._texts = texts
            self._is_built = True
            logger.info(f"SemanticRequirementsExtractor: index built ({len(texts)} prototypes).")
            return True
        except Exception as e:
            logger.warning(f"SemanticRequirementsExtractor build error: {e}")
            return False

    def extract(
        self, customer_message: str, min_confidence: float = 0.60
    ) -> Dict[str, Any]:
        """
        Extracts structured requirements from freeform customer text.

        Returns dict like:
          {
            "application": "architecture/CAD",
            "print_width": 36,
            "paper_size": "A0",
            "scanner_required": False,
          }
        """
        requirements: Dict[str, Any] = {}
        if not self._build_index():
            return requirements

        try:
            from rag.embeddings_engine import embeddings_engine
            q_vec = embeddings_engine.embed_text(customer_message)
            if q_vec is None:
                return requirements

            scores = np.dot(self._matrix, q_vec)
            top_indices = np.argsort(scores)[::-1][:20]

            # Collect best score per requirement key group (e.g. "application", "size", "scanner")
            key_best: Dict[str, Tuple[str, float]] = {}  # group -> (full_key, score)
            for idx in top_indices:
                sc = float(scores[idx])
                if sc < min_confidence:
                    break
                full_key = self._keys[idx]
                group = full_key.split(":")[0]  # "application", "size", "scanner", "volume"
                if group not in key_best or sc > key_best[group][1]:
                    key_best[group] = (full_key, sc)

            # Translate requirement keys to structured values
            for group, (full_key, sc) in key_best.items():
                val = full_key.split(":", 1)[1]  # e.g. "architecture_cad", "a0_36inch"
                if group == "application":
                    app_map = {
                        "architecture_cad": "architecture/CAD",
                        "photography": "photography",
                        "photo_booth": "photo_booth",
                        "office": "office_enterprise",
                        "dye_sublimation": "dye_sublimation",
                    }
                    if val in app_map:
                        requirements["application"] = app_map[val]
                        logger.debug(f"SemanticReqExtractor: application={app_map[val]} (score={sc:.3f})")

                elif group == "size":
                    size_map = {
                        "a4": ("A4", None),
                        "a3": ("A3", None),
                        "a1_24inch": ("A1", 24),
                        "a0_36inch": ("A0", 36),
                        "44inch": ("44-inch", 44),
                    }
                    if val in size_map:
                        paper_size, print_width = size_map[val]
                        requirements["paper_size"] = paper_size
                        if print_width:
                            requirements["print_width"] = print_width
                        logger.debug(f"SemanticReqExtractor: paper_size={paper_size}, print_width={print_width} (score={sc:.3f})")

                elif group == "scanner":
                    requirements["scanner_required"] = (val == "yes")
                    logger.debug(f"SemanticReqExtractor: scanner_required={val == 'yes'} (score={sc:.3f})")

                elif group == "volume":
                    volume_map = {"low": 15, "medium": 75, "high": 300}
                    if val in volume_map:
                        requirements["daily_volume_estimate"] = volume_map[val]
                        logger.debug(f"SemanticReqExtractor: volume={val} (score={sc:.3f})")

        except Exception as e:
            logger.warning(f"SemanticRequirementsExtractor.extract error: {e}")

        return requirements


def semantic_classify_intent(
    customer_message: str,
    state_summary: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Public helper: classify customer message intent using embeddings.

    Returns None if the embedding model is offline or confidence is too low
    (caller should then fall through to LLM or regex classifier).
    """
    classifier = SemanticIntentClassifier.get()
    result = classifier.classify(customer_message)
    return result


def semantic_extract_requirements(customer_message: str) -> Dict[str, Any]:
    """
    Public helper: extract structured requirements from freeform customer text
    using embedding similarity.
    """
    extractor = SemanticRequirementsExtractor.get()
    return extractor.extract(customer_message)


def semantic_find_products(
    customer_message: str,
    top_k: int = 4,
) -> List[Dict[str, Any]]:
    """
    Semantic product search: embed customer query and retrieve top-k products
    from the catalog using the existing hybrid RAG retriever.

    This directly leverages the dense embedding layer in RagRetriever which
    already combines 55% neural + 45% TF-IDF scoring.
    """
    try:
        from rag.retriever import rag_retriever
        results = rag_retriever.search(query=customer_message, limit=top_k)
        return results
    except Exception as e:
        logger.warning(f"semantic_find_products error: {e}")
        return []


def ai_extract_customer_data(raw_message: str) -> Dict[str, Optional[str]]:
    """
    Uses the LLM to extract customer contact data (name, phone, email, company)
    from a freeform message when regex patterns fail.

    This is the AI-powered fallback for the customer onboarding flow.
    Returns a dict with keys: name, phone, email, company.
    """
    result: Dict[str, Optional[str]] = {
        "name": None, "phone": None, "email": None, "company": None
    }

    # Quick pre-check: only call LLM if there's plausibly contact info
    has_digits = bool(re.search(r"\d{5,}", raw_message.replace(" ", "")))
    has_at = "@" in raw_message
    has_name_hint = bool(re.search(
        r"\b(?:my name is|i am|i'm|name:|name is|this is|call me)\b",
        raw_message, re.IGNORECASE
    ))

    if not (has_digits or has_at or has_name_hint):
        return result

    try:
        from ollama_client import ollama_client
        schema = {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Customer full name if mentioned, otherwise null"
                },
                "phone": {
                    "type": "string",
                    "description": "Phone number with country code if present, otherwise null"
                },
                "email": {
                    "type": "string",
                    "description": "Email address if present, otherwise null"
                },
                "company": {
                    "type": "string",
                    "description": "Company or organization name if mentioned, otherwise null"
                },
            },
            "required": ["name", "phone", "email", "company"]
        }

        ai_res = ollama_client.classify(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a customer data extraction assistant. "
                        "Extract the customer's name, phone number, email address, and company name "
                        "from the provided message. Return null for any field not present. "
                        "Do not invent or guess values. Be precise."
                    )
                },
                {"role": "user", "content": raw_message}
            ],
            schema=schema,
            temperature=0.0,
        )

        if ai_res.get("success") and ai_res.get("result"):
            res = ai_res["result"]
            null_values = {"none", "n/a", "unknown", "null", "not mentioned", "not provided", ""}

            raw_name = str(res.get("name") or "").strip()
            if raw_name.lower() not in null_values:
                result["name"] = raw_name

            raw_phone = str(res.get("phone") or "").strip()
            if raw_phone.lower() not in null_values and len(re.sub(r"[^\d]", "", raw_phone)) >= 7:
                result["phone"] = raw_phone

            raw_email = str(res.get("email") or "").strip()
            if raw_email.lower() not in null_values and "@" in raw_email:
                result["email"] = raw_email

            raw_company = str(res.get("company") or "").strip()
            if raw_company.lower() not in null_values:
                result["company"] = raw_company

            logger.info(
                f"ai_extract_customer_data: name={result['name']}, "
                f"phone={result['phone']}, email={result['email']}, "
                f"company={result['company']}"
            )

    except Exception as e:
        logger.warning(f"ai_extract_customer_data LLM call failed: {e}")

    return result


# ── Singleton access ──────────────────────────────────────────────────────────
_intent_classifier = SemanticIntentClassifier.get()
_req_extractor = SemanticRequirementsExtractor.get()
