"""
Ingestion + retrieval layer: takes a company's uploaded docs (PDF / TXT),
chunks them, and stores a per-tenant TF-IDF index for retrieval.

Why TF-IDF instead of a neural embedding model:
- Zero runtime model downloads — no dependency on HuggingFace Hub / model CDN
  being reachable at request time, which is a real reliability risk on
  free-tier hosting (this is exactly the failure mode this project hit
  during testing with chromadb's default ONNX downloader).
- No torch/sentence-transformers → keeps the deploy small and comfortably
  under Streamlit Community Cloud's free-tier memory limit (~1GB).
- Deterministic and fast — good enough for FAQ/product-doc style retrieval,
  which is the realistic scale for a small/medium company's support bot.
- Isolation: one index per tenant_id, stored as a separate pickle file, so
  companies' data never mixes.

Trade-off (say this openly in interviews): TF-IDF is lexical, not semantic —
it won't match "how do I get my money back" to "refund policy" as well as a
neural embedding would. The retrieval interface below is written so that
swapping in a real embedding model later (once you have infra for it) is a
one-file change, not a rewrite.
"""

import os
import pickle
from typing import List

import numpy as np
from pypdf import PdfReader
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

VECTORSTORE_DIR = os.path.join(os.path.dirname(__file__), "..", "vectorstores")
os.makedirs(VECTORSTORE_DIR, exist_ok=True)


def _index_path(tenant_id: str) -> str:
    return os.path.join(VECTORSTORE_DIR, f"{tenant_id}.pkl")


def _load_index(tenant_id: str) -> dict:
    path = _index_path(tenant_id)
    if not os.path.exists(path):
        return {"chunks": [], "sources": [], "vectorizer": None, "matrix": None}
    with open(path, "rb") as f:
        return pickle.load(f)


def _save_index(tenant_id: str, index: dict) -> None:
    with open(_index_path(tenant_id), "wb") as f:
        pickle.dump(index, f)


def _chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> List[str]:
    """Simple sliding-window chunker. Good enough for FAQ/product-doc style content."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return [c.strip() for c in chunks if c.strip()]


def _extract_text(file_path: str, filename: str) -> str:
    if filename.lower().endswith(".pdf"):
        reader = PdfReader(file_path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    else:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()


def ingest_file(tenant_id: str, file_path: str, filename: str) -> int:
    """Reads a file, chunks it, and adds it to the tenant's TF-IDF index.
    Returns number of chunks added."""
    text = _extract_text(file_path, filename)
    new_chunks = _chunk_text(text)
    if not new_chunks:
        return 0

    index = _load_index(tenant_id)
    index["chunks"].extend(new_chunks)
    index["sources"].extend([filename] * len(new_chunks))

    # Refit on the full corpus so the vector space stays consistent as more
    # docs get added. Fine at this scale (hundreds-few thousand chunks);
    # for a much larger corpus you'd move to incremental/neural embeddings.
    vectorizer = TfidfVectorizer(stop_words="english", max_features=20000)
    matrix = vectorizer.fit_transform(index["chunks"])
    index["vectorizer"] = vectorizer
    index["matrix"] = matrix

    _save_index(tenant_id, index)
    return len(new_chunks)


def retrieve(tenant_id: str, query: str, k: int = 4) -> str:
    """Retrieves top-k relevant chunks for a tenant's query. Used by the retrieval tool."""
    index = _load_index(tenant_id)
    if not index["chunks"] or index["vectorizer"] is None:
        return "No documents have been uploaded for this company yet."

    query_vec = index["vectorizer"].transform([query])
    scores = cosine_similarity(query_vec, index["matrix"])[0]
    top_k_idx = np.argsort(scores)[::-1][:k]
    top_k_idx = [i for i in top_k_idx if scores[i] > 0]  # drop zero-relevance matches

    if not top_k_idx:
        return "No relevant information found in the uploaded documents."

    formatted = []
    for i in top_k_idx:
        formatted.append(f"[Source: {index['sources'][i]}]\n{index['chunks'][i]}")
    return "\n\n---\n\n".join(formatted)


def doc_count(tenant_id: str) -> int:
    return len(_load_index(tenant_id)["chunks"])
