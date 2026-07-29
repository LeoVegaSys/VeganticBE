from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

import uuid
import glob
import config

embedding_model = HuggingFaceEmbeddings(
    model_name=config.EMBED_MODEL
)

documents = []

for file in glob.glob("rag_data_v2/*.txt"):
    loader = TextLoader(file)
    docs = loader.load()

    for doc in docs:
        doc.metadata["source"] = file

        fname = file.lower()

        if "additional" in fname:
            doc.metadata["type"] = "extended_terms"
        elif "disambiguation" in fname:
            doc.metadata["type"] = "disambiguation"
        elif "terms" in fname:
            doc.metadata["type"] = "core_terms"
        else:
            doc.metadata["type"] = "general"

    documents.extend(docs)

print(f"Loaded {len(documents)} documents")

splitter = RecursiveCharacterTextSplitter(
    chunk_size=config.CHUNK_SIZE,
    chunk_overlap=config.CHUNK_OVERLAP
)

docs = splitter.split_documents(documents)

client = QdrantClient(url=config.QDRANT_URL)

if client.collection_exists(config.COLLECTION_NAME):
    client.delete_collection(config.COLLECTION_NAME)

client.create_collection(
    collection_name=config.COLLECTION_NAME,
    vectors_config=VectorParams(size=384, distance=Distance.COSINE),
)

points = []

for doc in docs:
    vector = embedding_model.embed_query(doc.page_content)

    points.append(
        PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload={
                "text": doc.page_content,
                "source": doc.metadata["source"],
                "type": doc.metadata["type"],
                "version": "v2"
            }
        )
    )

client.upsert(config.COLLECTION_NAME, points)
print("V2 RAG index built")