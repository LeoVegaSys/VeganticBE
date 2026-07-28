"""
RAG Retrieval service.

Strategy:
    - Query BOTH collections (noc_v3_ietf + noc_v3_rfc) in parallel
    - Merge results, deduplicate
    - Pull approved feedback from production collections (type=feedback)
    - Return: feedback chunks first, then knowledge chunks
"""

from langchain_huggingface import HuggingFaceEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

import config as c 

class RAGAgent:
    def __init__(self):
        self.embedding_model = HuggingFaceEmbeddings(model_name=c.EMBED_MODEL)
        self.client = QdrantClient(url=c.QDRANT_URL)
        self.processed_ids = []
        self.global_idx = 1

    def _query_collection(self, col_name: str, q_vector: list, limit: int) -> list:
        """Query a single collection. Returns list of points or empty list."""
        try:
            result = self.client.query_points(
                collection_name=col_name,
                query=q_vector,
                limit=limit
            )
            return result.points
        except Exception as e:
            print(f"[rag_agent] Warning: could not query {col_name}: {e}")
            return []

    def _process_point_to_chunks(self, point):

        feedback_chunks = []
        knowledge_chunks = []

        # Deduplicate by point ID
        if point.id not in self.processed_ids:
            self.processed_ids.add(point.id)

            chunk_str = self._format_chunk(self.global_idx, point)
            self.global_idx += 1

            dtype = point.payload.get("type", "standard")

            if dtype == "feedback":
                feedback_chunks.append(chunk_str)
            else:
                knowledge_chunks.append(chunk_str)

        return {"knowledge": knowledge_chunks, "feedback": feedback_chunks}
    

    def _format_chunk(self, idx: int, point) -> str:
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


    def retrieve_context(self, query: str) -> str:
        """
            Main retrieval function.
            Searches all V3 collections, merges, separates feedback from knowledge.
            Returns formatted context string.
        """
        query_vector = self.embedding_model.embed_query(query)
        feedback_chunks  = []
        knowledge_chunks = []

        # Query every collection
        for collection_key, collection_name in c.COLLECTIONS.items():
            points = self._query_collection(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=c.TOP_K_PER_COLLECTION)

            for point in points:
                result_chunks = self._process_point_to_chunks(point)
                feedback_chunks.extend(result_chunks["feedback"])
                knowledge_chunks.extend(result_chunks["knowledge"])

       # Cap feedback dominance
        feedback_chunks = feedback_chunks[:c.TOP_K_FEEDBACK]
        # Feedback first → LLM treats it as ground truth
        all_chunks = feedback_chunks + knowledge_chunks
        return "\n\n".join(all_chunks) 


    def dump(self):
        pass