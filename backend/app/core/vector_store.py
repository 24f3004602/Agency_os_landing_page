"""
Qdrant vector store client for Agency OS.

Collections:
  research_briefs   — M6 competitive intelligence
  report_narratives — M3 past report context (future)
  outreach_context  — M8 lead personalisation context (future)

Embedding:
  Model is configurable via EMBED_MODEL in .env.
  Current approach: call Ollama HTTP API for embeddings if available,
  fall back to a simple hash-based stub for testing without GPU.

Each stored point has a payload dict that can be retrieved
alongside the vector for context injection into prompts.
"""
import hashlib
import logging
from typing import Any

import httpx
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    PointStruct,
    VectorParams,
)

from app.config import settings

logger = logging.getLogger(__name__)

# Collection names
RESEARCH_COLLECTION = "research_briefs"
REPORTS_COLLECTION = "report_narratives"
OUTREACH_COLLECTION = "outreach_context"

# Vector dimensions per model
VECTOR_DIMS = {
    "nomic-embed-text": 768,
    "default": 768,
}


def get_qdrant_client() -> QdrantClient:
    """Returns a Qdrant client connected to the homelab instance."""
    return QdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        timeout=30,
    )


async def get_embedding(text: str) -> list[float]:
    """
    Gets a vector embedding for text.

    Tries Ollama first (homelab running nomic-embed-text).
    Falls back to a deterministic stub if Ollama unreachable.
    The stub produces consistent (but not semantic) 768-dim vectors
    so the full pipeline can be tested without a running embed model.
    """
    ollama_url = getattr(settings, "ollama_host", "")

    if ollama_url and ollama_url != "http://localhost:11434":
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{ollama_url}/api/embeddings",
                    json={
                        "model": settings.embed_model or "nomic-embed-text",
                        "prompt": text,
                    },
                )
                response.raise_for_status()
                data = response.json()
                embedding = data.get("embedding", [])
                if embedding:
                    return embedding
        except Exception as e:
            logger.warning("Ollama embedding failed: %s — using stub", e)

    # Stub: deterministic 768-dim vector from text hash
    # Consistent across calls but NOT semantically meaningful
    hash_bytes = hashlib.sha256(text.encode()).digest()
    # Repeat hash bytes to fill 768 floats
    extended = (hash_bytes * 24)[:768]
    return [b / 255.0 - 0.5 for b in extended]


async def ensure_collection(collection_name: str, vector_size: int = 768) -> None:
    """
    Creates a Qdrant collection if it doesn't exist.
    Safe to call multiple times — no-op if collection exists.
    """
    try:
        client = get_qdrant_client()
        existing = [c.name for c in client.get_collections().collections]
        if collection_name not in existing:
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("Created Qdrant collection: %s", collection_name)
        else:
            logger.debug("Qdrant collection already exists: %s", collection_name)
    except Exception as e:
        logger.error("Failed to ensure Qdrant collection %s: %s", collection_name, e)


async def store_point(
    collection_name: str,
    point_id: str,
    text: str,
    payload: dict[str, Any],
) -> str:
    """
    Embeds text and stores it in Qdrant with the given payload.
    Returns the point_id stored.

    point_id must be a valid UUID string or integer string.
    """
    await ensure_collection(collection_name)

    embedding = await get_embedding(text)

    try:
        client = get_qdrant_client()
        client.upsert(
            collection_name=collection_name,
            points=[
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=payload,
                )
            ],
        )
        logger.info(
            "Stored point %s in collection %s",
            point_id,
            collection_name,
        )
        return point_id
    except Exception as e:
        logger.error("Qdrant upsert failed: %s", e)
        raise


async def search_similar(
    collection_name: str,
    query_text: str,
    top_k: int = 5,
    filter_payload: dict | None = None,
) -> list[dict]:
    """
    Semantic search in a Qdrant collection.
    Returns list of payload dicts for the top_k most similar points.

    filter_payload: optional Qdrant filter dict
    e.g. {"must": [{"key": "client_id", "match": {"value": "uuid..."}}]}
    """
    try:
        await ensure_collection(collection_name)
        embedding = await get_embedding(query_text)
        client = get_qdrant_client()

        search_params = {
            "collection_name": collection_name,
            "query_vector": embedding,
            "limit": top_k,
            "with_payload": True,
        }

        if filter_payload:
            from qdrant_client.http.models import Filter
            search_params["query_filter"] = filter_payload

        results = client.search(**search_params)
        return [
            {
                "score": r.score,
                "payload": r.payload,
                "id": r.id,
            }
            for r in results
        ]
    except Exception as e:
        logger.error("Qdrant search failed: %s", e)
        return []


async def delete_point(collection_name: str, point_id: str) -> None:
    """Removes a point from a Qdrant collection."""
    try:
        client = get_qdrant_client()
        client.delete(
            collection_name=collection_name,
            points_selector=[point_id],
        )
    except Exception as e:
        logger.warning("Qdrant delete failed for %s: %s", point_id, e)