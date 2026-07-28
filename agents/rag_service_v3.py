"""
rag_service_v3.py

Retrieval service for V3.

Strategy:
    - Query BOTH collections (noc_v3_ietf + noc_v3_rfc) in parallel
    - Merge results, deduplicate
    - Pull approved feedback from production collections (type=feedback)
    - Return: feedback chunks first, then knowledge chunks
"""

from langchain_huggingface import HuggingFaceEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
import config_v3 as config


# ===============================
# INIT
# ===============================
embedding_model = HuggingFaceEmbeddings(model_name=config.EMBED_MODEL)
client = QdrantClient(url=config.QDRANT_URL)


# ===============================
# RETRIEVE FROM ONE COLLECTION
# ===============================
def _query_collection(collection_name: str, query_vector: list, limit: int) -> list:
    """Query a single collection. Returns list of points or empty list."""
    try:
        result = client.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=limit
        )
        return result.points
    except Exception as e:
        print(f"[rag_service] Warning: could not query {collection_name}: {e}")
        return []


# ===============================
# FORMAT CHUNK
# ===============================
def _format_chunk(idx: int, point) -> str:
    """Format a Qdrant point into a context chunk string."""
    payload = point.payload

    dtype       = payload.get("type", "standard")
    source_file = payload.get("source_file", "unknown")
    collection  = payload.get("collection", "unknown")
    rfc_id      = payload.get("rfc_id", "")
    title       = payload.get("title", "")
    text        = payload.get("text", "")

    # Build a clean source label
    if rfc_id:
        source_label = f"{rfc_id} — {title}" if title else rfc_id
    else:
        source_label = source_file

    chunk = f"""[CHUNK {idx}]
[TYPE: {dtype}]
[SOURCE: {source_label}]
[COLLECTION: {collection}]
{text}"""

    return chunk


# ===============================
# RETRIEVE CONTEXT
# ===============================
def retrieve_context(query: str) -> str:
    """
    Main retrieval function.
    Searches all V3 collections, merges, separates feedback from knowledge.
    Returns formatted context string.
    """

    query_vector = embedding_model.embed_query(query)

    feedback_chunks  = []
    knowledge_chunks = []
    seen_ids         = set()

    global_idx = 1

    # Query every collection
    for collection_key, collection_name in config.COLLECTIONS.items():

        points = _query_collection(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=config.TOP_K_PER_COLLECTION
        )

        for point in points:

            # Deduplicate by point ID
            if point.id in seen_ids:
                continue
            seen_ids.add(point.id)

            chunk_str = _format_chunk(global_idx, point)
            global_idx += 1

            dtype = point.payload.get("type", "standard")

            if dtype == "feedback":
                feedback_chunks.append(chunk_str)
            else:
                knowledge_chunks.append(chunk_str)

    # Cap feedback dominance
    feedback_chunks = feedback_chunks[:config.TOP_K_FEEDBACK]

    # Feedback first → LLM treats it as ground truth
    all_chunks = feedback_chunks + knowledge_chunks
    return "\n\n".join(all_chunks)