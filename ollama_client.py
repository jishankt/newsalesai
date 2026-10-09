"""
Ollama HTTP Client for conversational generation and structured classification.
Communicates with http://localhost:11434/api/chat (structured) and /api/generate (legacy)
with fallback simulation adhering strictly to prompt rules when Ollama is offline.
"""

import requests
import json
import logging
import re
import time
from enum import Enum
from typing import Optional, Dict, Any, List

from config import (
    OLLAMA_BASE_URL, DEFAULT_MODEL, TIMEOUT_SECONDS,
    OLLAMA_CONNECT_TIMEOUT, OLLAMA_READ_TIMEOUT, OLLAMA_MAX_RETRIES,
    OLLAMA_KEEP_ALIVE, OLLAMA_NUM_CTX,
    OLLAMA_CLASSIFIER_TEMPERATURE, OLLAMA_RESPONSE_TEMPERATURE,
    OLLAMA_TOP_P,
)

logger = logging.getLogger("ollama_client")


class OllamaErrorKind(Enum):
    SERVER_UNAVAILABLE = "server_unavailable"
    CONNECTION_TIMEOUT = "connection_timeout"
    READ_TIMEOUT = "read_timeout"
    MODEL_NOT_INSTALLED = "model_not_installed"
    INVALID_RESPONSE = "invalid_response"
    JSON_PARSE_FAILURE = "json_parse_failure"


def classify_request_error(e: Exception) -> OllamaErrorKind:
    """Classifies a requests or network exception into an OllamaErrorKind."""
    if isinstance(e, requests.exceptions.ConnectTimeout):
        return OllamaErrorKind.CONNECTION_TIMEOUT
    if isinstance(e, requests.exceptions.ReadTimeout):
        return OllamaErrorKind.READ_TIMEOUT
    err_str = str(e).lower()
    if any(k in err_str for k in ["connection refused", "winerror 10061", "econnrefused", "actively refused", "failed to establish a new connection"]):
        return OllamaErrorKind.SERVER_UNAVAILABLE
    if isinstance(e, requests.exceptions.ConnectionError):
        return OllamaErrorKind.SERVER_UNAVAILABLE
    return OllamaErrorKind.INVALID_RESPONSE


class OllamaClient:
    def __init__(self, base_url: str = OLLAMA_BASE_URL, default_model: str = DEFAULT_MODEL):
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self._offline_until = 0.0
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=20)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def startup_health_check(self) -> Dict[str, Any]:
        """
        Comprehensive startup health check:
        1. Connectivity test: GET /api/tags
        2. Model availability test: Check if default_model is installed
        3. Response validity test: Minimal inference ping to /api/chat
        """
        start_time = time.time()
        result: Dict[str, Any] = {
            "online": False,
            "connectivity": False,
            "model_available": False,
            "inference_working": False,
            "models": [],
            "active_model": self.default_model,
            "base_url": self.base_url,
            "latency_ms": 0,
            "error_kind": None,
            "error_message": None,
        }

        # Step 1: Connectivity & tags
        try:
            resp = self.session.get(
                f"{self.base_url}/api/tags",
                timeout=(OLLAMA_CONNECT_TIMEOUT, 5.0)
            )
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name") for m in data.get("models", [])]
                result["connectivity"] = True
                result["models"] = models
                logger.info(f"Ollama connected at {self.base_url}. Installed models: {models}")
            else:
                result["error_kind"] = OllamaErrorKind.INVALID_RESPONSE.value
                result["error_message"] = f"HTTP {resp.status_code} from /api/tags: {resp.text[:200]}"
                logger.warning(f"Ollama startup health check: {result['error_message']}")
                result["latency_ms"] = int((time.time() - start_time) * 1000)
                return result
        except Exception as e:
            kind = classify_request_error(e)
            result["error_kind"] = kind.value
            result["error_message"] = f"{kind.value}: {str(e)}"
            logger.warning(f"Ollama startup health check failed on {self.base_url}/api/tags: [{kind.value}] {e}")
            result["latency_ms"] = int((time.time() - start_time) * 1000)
            return result

        # Step 2: Model availability
        # Check either exact match or prefix match (e.g. qwen2.5:32b vs qwen2.5:32b-instruct)
        model_found = any(
            self.default_model == m or m.startswith(self.default_model) or self.default_model.split(":")[0] == m.split(":")[0]
            for m in result["models"]
        )
        result["model_available"] = model_found
        if not model_found:
            result["error_kind"] = OllamaErrorKind.MODEL_NOT_INSTALLED.value
            result["error_message"] = f"Model '{self.default_model}' not found in installed models: {result['models']}"
            logger.warning(f"Ollama startup health check: {result['error_message']}")
            result["latency_ms"] = int((time.time() - start_time) * 1000)
            return result

        # Step 3: Response validity ping test
        ping_payload = {
            "model": self.default_model,
            "messages": [{"role": "user", "content": "ping"}],
            "stream": False,
            "options": {"num_predict": 1}
        }
        try:
            ping_resp = self.session.post(
                f"{self.base_url}/api/chat",
                json=ping_payload,
                timeout=(OLLAMA_CONNECT_TIMEOUT, OLLAMA_READ_TIMEOUT)
            )
            if ping_resp.status_code == 200:
                result["inference_working"] = True
                result["online"] = True
                logger.info(f"Ollama startup health check PASSED. Model '{self.default_model}' responsive.")
            elif ping_resp.status_code == 404:
                result["error_kind"] = OllamaErrorKind.MODEL_NOT_INSTALLED.value
                result["error_message"] = f"HTTP 404 when pinging model '{self.default_model}'"
                logger.warning(f"Ollama startup ping failed: {result['error_message']}")
            else:
                result["error_kind"] = OllamaErrorKind.INVALID_RESPONSE.value
                result["error_message"] = f"HTTP {ping_resp.status_code} from /api/chat ping: {ping_resp.text[:200]}"
                logger.warning(f"Ollama startup ping failed: {result['error_message']}")
        except Exception as e:
            kind = classify_request_error(e)
            result["error_kind"] = kind.value
            result["error_message"] = f"Inference ping failed: [{kind.value}] {str(e)}"
            logger.warning(f"Ollama startup ping failed: [{kind.value}] {e}")

        result["latency_ms"] = int((time.time() - start_time) * 1000)
        return result

    def check_health(self) -> dict:
        """Checks if Ollama is running and retrieves list of installed models."""
        shc = self.startup_health_check()
        return {
            "online": shc["online"],
            "models": shc["models"],
            "model_available": shc["model_available"],
            "active_model": self.default_model,
            "base_url": self.base_url,
            "error_kind": shc.get("error_kind"),
            "message": shc.get("error_message") or ("Ollama service online." if shc["online"] else "Ollama service offline. Rule-based simulation engine active.")
        }

    def generate(self, prompt: str, model: str = None, options: dict = None) -> dict:
        """
        Sends generation request to Ollama /api/generate.
        If Ollama is unreachable, uses fallback engine adhering to prompt guidelines.
        """
        payload = {
            "model": target_model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "options": {
                "num_ctx": OLLAMA_NUM_CTX,
                "num_predict": 180,
                "temperature": OLLAMA_RESPONSE_TEMPERATURE,
            }
        }
        if options:
            payload["options"].update(options)

        endpoint = f"{self.base_url}/api/generate"

        for attempt in range(1 + OLLAMA_MAX_RETRIES):
            try:
                resp = self.session.post(
                    endpoint, json=payload,
                    timeout=(OLLAMA_CONNECT_TIMEOUT, OLLAMA_READ_TIMEOUT)
                )
                if resp.status_code == 200:
                    data = resp.json()
                    response_text = data.get("response", "").strip()
                    return {
                        "success": True,
                        "response": response_text,
                        "source": "ollama",
                        "model": target_model,
                        "total_duration": data.get("total_duration", 0)
                    }
                elif resp.status_code == 404:
                    logger.error(f"[{OllamaErrorKind.MODEL_NOT_INSTALLED.value}] Model '{target_model}' not found at {endpoint} (HTTP 404)")
                    break
                else:
                    logger.warning(f"[{OllamaErrorKind.INVALID_RESPONSE.value}] Ollama /api/generate HTTP {resp.status_code} (attempt {attempt + 1}): {resp.text[:200]}")
            except requests.exceptions.RequestException as e:
                kind = classify_request_error(e)
                logger.warning(f"[{kind.value}] Ollama connection error on {endpoint} (attempt {attempt + 1}): {e}")
                if kind in (OllamaErrorKind.CONNECTION_TIMEOUT, OllamaErrorKind.SERVER_UNAVAILABLE) and attempt >= OLLAMA_MAX_RETRIES:
                    break

        # Fail closed without customer-facing simulated responses
        logger.warning(f"Ollama generate: service unavailable for model '{target_model}' after retries.")
        return {
            "success": False,
            "response": "",
            "source": "ollama_error",
            "model": target_model,
            "fallback_used": False,
            "error": f"Ollama service unavailable or model '{target_model}' not responding."
        }

    # ── New /api/chat Methods (Phase 3) ──────────────────────────────────

    def classify(self, messages: list, schema: dict, model: str = None,
                 temperature: float = None, max_retries: int = None) -> dict:
        """
        Sends a structured classification request to Ollama /api/chat.
        Uses 'format' parameter for constrained JSON output.

        Returns:
            {
                "success": bool,
                "result": dict,        # Parsed JSON from model
                "source": str,         # "ollama" or "fallback"
                "model": str,
                "latency_ms": int,
                "fallback_used": bool,
                "error_kind": Optional[str]
            }
        """
        target_model = model or self.default_model
        if time.time() < getattr(self, "_offline_until", 0.0):
            return {
                "success": False,
                "result": {},
                "source": "fallback",
                "model": target_model,
                "latency_ms": 0,
                "fallback_used": True,
                "error_kind": OllamaErrorKind.SERVER_UNAVAILABLE.value,
            }

        temp = temperature if temperature is not None else OLLAMA_CLASSIFIER_TEMPERATURE
        retries = max_retries if max_retries is not None else OLLAMA_MAX_RETRIES
        payload = {
            "model": target_model,
            "messages": messages,
            "stream": False,
            "format": schema,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "options": {
                "temperature": temp,
                "top_p": OLLAMA_TOP_P,
                "num_ctx": OLLAMA_NUM_CTX,
                "num_predict": 120,
            }
        }

        endpoint = f"{self.base_url}/api/chat"
        last_error_kind = None

        for attempt in range(1 + retries):
            try:
                start = time.time()
                resp = self.session.post(
                    endpoint, json=payload,
                    timeout=(OLLAMA_CONNECT_TIMEOUT, OLLAMA_READ_TIMEOUT)
                )
                latency_ms = int((time.time() - start) * 1000)

                if resp.status_code == 200:
                    self._offline_until = 0.0
                    data = resp.json()
                    content = data.get("message", {}).get("content", "")
                    try:
                        parsed = json.loads(content)
                        return {
                            "success": True,
                            "result": parsed,
                            "source": "ollama",
                            "model": target_model,
                            "latency_ms": latency_ms,
                            "fallback_used": False,
                        }
                    except json.JSONDecodeError as jde:
                        last_error_kind = OllamaErrorKind.JSON_PARSE_FAILURE.value
                        logger.warning(f"[{last_error_kind}] Ollama classify returned non-JSON: {content[:200]} (Error: {jde})")
                        return {
                            "success": False,
                            "result": {},
                            "source": "fallback",
                            "model": target_model,
                            "latency_ms": latency_ms,
                            "fallback_used": True,
                            "error_kind": last_error_kind,
                        }
                elif resp.status_code == 404:
                    last_error_kind = OllamaErrorKind.MODEL_NOT_INSTALLED.value
                    logger.error(f"[{last_error_kind}] Model '{target_model}' not found at {endpoint} (HTTP 404)")
                    break
                else:
                    last_error_kind = OllamaErrorKind.INVALID_RESPONSE.value
                    logger.warning(f"[{last_error_kind}] Ollama classify HTTP {resp.status_code} (attempt {attempt + 1}): {resp.text[:200]}")

            except requests.exceptions.RequestException as e:
                kind = classify_request_error(e)
                last_error_kind = kind.value
                logger.warning(f"[{kind.value}] Ollama classify connection error on {endpoint} (attempt {attempt + 1}): {e}")
                if kind in (OllamaErrorKind.CONNECTION_TIMEOUT, OllamaErrorKind.SERVER_UNAVAILABLE):
                    self._offline_until = time.time() + 10.0
                    break

        # All retries exhausted — return fallback
        logger.info(f"Ollama classify: all retries exhausted ([{last_error_kind}]), returning fallback.")
        return {
            "success": False,
            "result": {},
            "source": "fallback",
            "model": target_model,
            "latency_ms": 0,
            "fallback_used": True,
            "error_kind": last_error_kind,
        }

    def chat_completions(self, messages: list, model: str = None,
                         temperature: float = None, top_p: float = None, max_retries: int = None) -> dict:
        """
        Sends an OpenAI-compatible chat completion request to /v1/chat/completions.
        """
        target_model = model or self.default_model
        temp = temperature if temperature is not None else OLLAMA_RESPONSE_TEMPERATURE
        p_val = top_p if top_p is not None else OLLAMA_TOP_P
        retries = max_retries if max_retries is not None else OLLAMA_MAX_RETRIES
        payload = {
            "model": target_model,
            "messages": messages,
            "stream": False,
            "temperature": temp,
            "top_p": p_val,
            "max_tokens": 180,
        }
        endpoint = f"{self.base_url}/v1/chat/completions"
        last_error_kind = None

        for attempt in range(1 + retries):
            try:
                start = time.time()
                resp = self.session.post(
                    endpoint, json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=(OLLAMA_CONNECT_TIMEOUT, OLLAMA_READ_TIMEOUT)
                )
                latency_ms = int((time.time() - start) * 1000)

                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    content = ""
                    if choices:
                        content = choices[0].get("message", {}).get("content", "").strip()
                    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
                    return {
                        "success": True,
                        "response": content,
                        "source": "ollama_v1",
                        "model": target_model,
                        "latency_ms": latency_ms,
                        "fallback_used": False,
                    }
                elif resp.status_code == 404:
                    last_error_kind = OllamaErrorKind.MODEL_NOT_INSTALLED.value
                    logger.error(f"[{last_error_kind}] Model '{target_model}' not found at {endpoint} (HTTP 404)")
                    break
                else:
                    last_error_kind = OllamaErrorKind.INVALID_RESPONSE.value
                    logger.warning(f"[{last_error_kind}] Ollama v1 chat completions HTTP {resp.status_code} (attempt {attempt + 1}): {resp.text[:200]}")
            except requests.exceptions.RequestException as e:
                kind = classify_request_error(e)
                last_error_kind = kind.value
                logger.warning(f"[{kind.value}] Ollama v1 error on {endpoint} (attempt {attempt + 1}): {e}")
                if kind in (OllamaErrorKind.CONNECTION_TIMEOUT, OllamaErrorKind.SERVER_UNAVAILABLE) and attempt >= retries:
                    break

        return {
            "success": False,
            "response": "",
            "source": "fallback",
            "model": target_model,
            "latency_ms": 0,
            "fallback_used": True,
            "error_kind": last_error_kind,
        }

    def compose(self, messages: list, model: str = None,
                temperature: float = None, top_p: float = None, max_retries: int = None) -> dict:
        """
        Sends a natural language response generation request.
        First attempts the OpenAI-compatible /v1/chat/completions endpoint,
        falling back to native /api/chat if needed.
        """
        target_model = model or self.default_model
        if time.time() < getattr(self, "_offline_until", 0.0):
            return {
                "success": False,
                "response": "",
                "source": "fallback",
                "model": target_model,
                "latency_ms": 0,
                "fallback_used": True,
                "error_kind": OllamaErrorKind.SERVER_UNAVAILABLE.value,
            }

        temp = temperature if temperature is not None else OLLAMA_RESPONSE_TEMPERATURE
        p_val = top_p if top_p is not None else OLLAMA_TOP_P
        retries = max_retries if max_retries is not None else OLLAMA_MAX_RETRIES
        payload = {
            "model": target_model,
            "messages": messages,
            "stream": False,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "options": {
                "temperature": temp,
                "top_p": p_val,
                "num_ctx": OLLAMA_NUM_CTX,
                "num_predict": 180,
            }
        }

        endpoint = f"{self.base_url}/api/chat"
        last_error_kind = None

        for attempt in range(1 + retries):
            try:
                start = time.time()
                resp = self.session.post(
                    endpoint, json=payload,
                    timeout=(OLLAMA_CONNECT_TIMEOUT, OLLAMA_READ_TIMEOUT)
                )
                latency_ms = int((time.time() - start) * 1000)

                if resp.status_code == 200:
                    self._offline_until = 0.0
                    data = resp.json()
                    content = data.get("message", {}).get("content", "").strip()
                    # Strip thinking tags if model emits them
                    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

                    return {
                        "success": True,
                        "response": content,
                        "source": "ollama",
                        "model": target_model,
                        "latency_ms": latency_ms,
                        "fallback_used": False,
                    }
                elif resp.status_code == 404:
                    last_error_kind = OllamaErrorKind.MODEL_NOT_INSTALLED.value
                    logger.error(f"[{last_error_kind}] Model '{target_model}' not found at {endpoint} (HTTP 404)")
                    break
                else:
                    last_error_kind = OllamaErrorKind.INVALID_RESPONSE.value
                    logger.warning(f"[{last_error_kind}] Ollama compose HTTP {resp.status_code} (attempt {attempt + 1}): {resp.text[:200]}")

            except requests.exceptions.RequestException as e:
                kind = classify_request_error(e)
                last_error_kind = kind.value
                logger.warning(f"[{kind.value}] Ollama compose error on {endpoint} (attempt {attempt + 1}): {e}")
                if kind in (OllamaErrorKind.CONNECTION_TIMEOUT, OllamaErrorKind.SERVER_UNAVAILABLE):
                    self._offline_until = time.time() + 10.0
                    break

        # All retries exhausted
        logger.info(f"Ollama compose: all retries exhausted ([{last_error_kind}]), returning empty.")
        return {
            "success": False,
            "response": "",
            "source": "fallback",
            "model": target_model,
            "latency_ms": 0,
            "fallback_used": True,
            "error_kind": last_error_kind,
        }

    def health(self) -> dict:
        """Alias for check_health for API consistency."""
        return self.check_health()


# Module-level default client
ollama_client = OllamaClient()

