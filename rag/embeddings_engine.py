"""
Dense Neural Embeddings Engine for Kepler Tech SalesAI.
Generates, caches, and indexes dense vector representations of catalog products,
specifications, and customer queries using local Ollama embedding models (e.g. nomic-embed-text / bge-m3).
Supports fast cosine similarity computation and hybrid dense+sparse retrieval.
"""

import os
import time
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import requests

from config import OLLAMA_BASE_URL, EMBEDDING_MODEL, USE_NEURAL_EMBEDDINGS

logger = logging.getLogger("rag.embeddings")

DEFAULT_CACHE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "product_embeddings.npz"
)


class EmbeddingsEngine:
    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        model: str = EMBEDDING_MODEL,
        cache_path: str = DEFAULT_CACHE_PATH,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.cache_path = cache_path
        self.embeddings: Optional[np.ndarray] = None  # shape: (N, D)
        self.doc_ids: List[str] = []
        self.session = requests.Session()
        self._is_available: Optional[bool] = None

    def is_available(self) -> bool:
        """Checks if the embedding endpoint and model are responsive."""
        if not USE_NEURAL_EMBEDDINGS:
            return False
        if self._is_available is not None:
            return self._is_available
        try:
            resp = self.session.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": "ping"},
                timeout=3.0,
            )
            if resp.status_code == 200:
                self._is_available = True
                return True
            # Fallback to older /api/embeddings endpoint
            resp2 = self.session.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": "ping"},
                timeout=3.0,
            )
            self._is_available = (resp2.status_code == 200)
            return self._is_available
        except Exception as e:
            logger.warning(f"Ollama embeddings model '{self.model}' not reachable: {e}")
            self._is_available = False
            return False

    def embed_text(self, text: str) -> Optional[np.ndarray]:
        """Embeds a single string into a normalized 1D numpy vector."""
        if not text or not text.strip():
            return None
        text_clean = text.strip().replace("\n", " ")[:2000]
        try:
            # Try batch endpoint /api/embed first
            resp = self.session.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": text_clean},
                timeout=5.0,
            )
            if resp.status_code == 200:
                embs = resp.json().get("embeddings", [])
                if embs and len(embs) > 0:
                    vec = np.array(embs[0], dtype=np.float32)
                    norm = np.linalg.norm(vec)
                    return vec / (norm + 1e-9) if norm > 0 else vec

            # Fallback to /api/embeddings
            resp2 = self.session.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text_clean},
                timeout=5.0,
            )
            if resp2.status_code == 200:
                emb = resp2.json().get("embedding", [])
                if emb:
                    vec = np.array(emb, dtype=np.float32)
                    norm = np.linalg.norm(vec)
                    return vec / (norm + 1e-9) if norm > 0 else vec
        except Exception as e:
            logger.debug(f"Failed to generate embedding for query: {e}")
        return None

    def embed_batch(self, texts: List[str], batch_size: int = 32) -> Optional[np.ndarray]:
        """Embeds a list of texts in batches and returns a 2D numpy array (N, D)."""
        if not texts:
            return None
        all_vecs: List[List[float]] = []
        for i in range(0, len(texts), batch_size):
            chunk = [t.strip().replace("\n", " ")[:2000] for t in texts[i : i + batch_size]]
            try:
                resp = self.session.post(
                    f"{self.base_url}/api/embed",
                    json={"model": self.model, "input": chunk},
                    timeout=30.0,
                )
                if resp.status_code == 200:
                    embs = resp.json().get("embeddings", [])
                    all_vecs.extend(embs)
                else:
                    # Fallback one-by-one
                    for t in chunk:
                        vec = self.embed_text(t)
                        if vec is not None:
                            all_vecs.append(vec.tolist())
                        else:
                            all_vecs.append([0.0] * 768)
            except Exception as e:
                logger.warning(f"Batch embed error on chunk {i}: {e}")
                for t in chunk:
                    vec = self.embed_text(t)
                    if vec is not None:
                        all_vecs.append(vec.tolist())
                    else:
                        all_vecs.append([0.0] * 768)

        if not all_vecs:
            return None
        arr = np.array(all_vecs, dtype=np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1e-9
        return arr / norms

    def load_or_build_index(
        self,
        doc_ids: List[str],
        doc_texts: List[str],
        force_rebuild: bool = False,
    ) -> bool:
        """
        Loads cached embeddings from disk if available and matching.
        Otherwise builds embeddings via Ollama and saves cache.
        """
        self.doc_ids = list(doc_ids)
        if not force_rebuild and os.path.exists(self.cache_path):
            try:
                data = np.load(self.cache_path, allow_pickle=True)
                cached_ids = list(data["doc_ids"])
                cached_embs = data["embeddings"]
                if cached_ids == self.doc_ids and cached_embs.shape[0] == len(doc_ids):
                    self.embeddings = cached_embs
                    logger.info(
                        f"Loaded cached neural embeddings from {self.cache_path} "
                        f"(shape={self.embeddings.shape}, model={self.model})"
                    )
                    return True
                logger.info("Cached embeddings ID mismatch or count changed. Re-indexing...")
            except Exception as e:
                logger.warning(f"Could not load cached embeddings: {e}")

        # Check availability before running full index build
        if not self.is_available():
            logger.info("Ollama embedding model offline — skipping neural embeddings build.")
            return False

        logger.info(f"Generating neural embeddings for {len(doc_texts)} items using {self.model}...")
        t0 = time.time()
        arr = self.embed_batch(doc_texts, batch_size=32)
        if arr is not None and arr.shape[0] == len(doc_ids):
            self.embeddings = arr
            try:
                os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
                np.savez_compressed(
                    self.cache_path,
                    doc_ids=np.array(self.doc_ids, dtype=object),
                    embeddings=self.embeddings,
                )
                logger.info(
                    f"Saved {len(doc_ids)} embeddings to {self.cache_path} in {time.time()-t0:.2f}s"
                )
                return True
            except Exception as e:
                logger.warning(f"Could not save embeddings cache to {self.cache_path}: {e}")
                return True
        return False

    def compute_similarity(
        self,
        query: str,
        top_k: int = 10,
    ) -> List[Tuple[int, float]]:
        """
        Computes cosine similarities between query and all catalog documents.
        Returns list of (doc_index, similarity_score) sorted descending.
        """
        if self.embeddings is None:
            return []
        q_vec = self.embed_text(query)
        if q_vec is None:
            return []
        # Cosine similarity since vectors are L2-normalized: dot product
        scores = np.dot(self.embeddings, q_vec)
        # Get top-k indices
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [(int(idx), float(scores[idx])) for idx in top_indices if scores[idx] > 0.0]


# Global singleton instance
embeddings_engine = EmbeddingsEngine()
