"""
Generates embeddings for catalog items using a local sentence-transformers
model — local, runs on CPU fine for scale (~500 items).

Embeddings are computed from a combination of description + style_tags (created in tagger),
since that's the text users' free-form theme/style language should match
against semantically.
"""

import hashlib
import numpy as np # storing the embedded data
from sentence_transformers import SentenceTransformer

_model: SentenceTransformer | None = None # sentence transformers used for embedding creation.


def get_model() -> SentenceTransformer:
    """Lazy-load the model once per process — loading is the slow part."""
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def build_embedding_text(description: str | None, style_tags: list[str]) -> str:
    """
    Combines the fields that should drive semantic matching into one
    string. Style tags are repeated/weighted slightly by being stated
    plainly, since short tag words can otherwise get diluted by a much
    longer description in the embedding.
    """
    parts = []
    if style_tags:
        parts.append("Style: " + ", ".join(style_tags) + ".")
    if description:
        parts.append(description)
    return " ".join(parts).strip()


def text_hash(text: str) -> str:
    """Used to detect whether source text changed since the last embed,
    so refresh runs don't re-embed unchanged items."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def embed_text(text: str) -> bytes:
    """Returns the embedding as raw bytes, ready to store in a BLOB column."""
    model = get_model()
    vector = model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
    return vector.astype(np.float32).tobytes()


def embedding_from_bytes(blob: bytes) -> np.ndarray:
    """Reconstructs a numpy array from a stored BLOB."""
    return np.frombuffer(blob, dtype=np.float32)


if __name__ == "__main__":
    sample_text = build_embedding_text(
        description="Mouth blown vase, perfect for long-stemmed flowers.",
        style_tags=["minimalist", "scandinavian"],
    )
    print("Embedding text:", sample_text)
    vec_bytes = embed_text(sample_text)
    vec = embedding_from_bytes(vec_bytes)
    print("Embedding dim:", vec.shape, "| hash:", text_hash(sample_text)[:12])
