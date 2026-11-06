import hashlib
import math
import os

from google import genai
from google.genai import types


EMBEDDING_MODEL = "gemini-embedding-001"


def generate_lead_embedding(normalized_text: str) -> dict:
    """Generate a real Gemini vector, or explicitly report degraded keyword-only mode."""
    if not isinstance(normalized_text, str) or not normalized_text.strip():
        return {
            "status": "failed",
            "message": "Normalized text is empty; cannot generate an embedding.",
        }

    content_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {
            "status": "degraded",
            "embedding_metadata": {
                "model_id": EMBEDDING_MODEL,
                "content_hash": content_hash,
                "status": "unavailable",
            },
            "message": "GEMINI_API_KEY is missing; semantic matching is unavailable.",
        }

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=normalized_text,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=768,
            ),
        )
        embeddings = response.embeddings or []
        vector = embeddings[0].values if embeddings else None
        if not vector or any(
            isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
            for value in vector
        ):
            raise ValueError("Embedding provider returned an empty or invalid vector.")
        return {
            "status": "success",
            "vector": list(vector),
            "embedding_metadata": {
                "model_id": EMBEDDING_MODEL,
                "content_hash": content_hash,
                "vector_dimension": len(vector),
                "status": "generated",
            },
            "message": "Semantic embedding generated.",
        }
    except Exception as exc:
        return {
            "status": "degraded",
            "error": str(exc),
            "embedding_metadata": {
                "model_id": EMBEDDING_MODEL,
                "content_hash": content_hash,
                "status": "unavailable",
            },
            "message": "Embedding provider failed; exact and rule-based matching will be used.",
        }


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
