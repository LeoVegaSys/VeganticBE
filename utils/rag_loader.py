import os
import uuid
import glob

from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

import config as c


def load_docs(file_path: str, allowed_extensions: list[str], collection: str):
    RagLoader(path=file_path, extensions=allowed_extensions).load(to_collection_name=collection)


class RagLoader:
    def __init__(self, path: str = "", extensions: list = []):
        """
        Class to load documents into RAG
        Inputs:
            path (str) : Relative or Absolute path of source folder, not ending in /
            extensions (list) : List of valid file extensions to include.
                                Eg.: ["txt","pdf"]
        """
        self.embed_model = HuggingFaceEmbeddings(model_name=c.EMBED_MODEL)
        self.src_path = path
        self.allowed_extensions = extensions
        self.client = QdrantClient(url=c.QDRANT_URL)

    def load(self, to_collection_name: str):
        docs = self.parse_docs()
        split_docs = self.process_docs(docs)
        self.check_collection(to_collection_name)
        points = self.vectorize(split_docs)
        self.client.upsert(to_collection_name, points)

    def vectorize(self, docs: list = []):
        points = []
        for doc in docs:
            vector = self.embed_model.embed_query(doc.page_content)

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
        return points
        

    def check_collection(self, collection_name: str):
        if self.client.collection_exists(collection_name):
            self.client.delete_collection(collection_name)
        self.client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )


    def process_docs(self, docs: list) -> list:        
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=c.CHUNK_SIZE,
            chunk_overlap=c.CHUNK_OVERLAP
        )
        docs = splitter.split_documents(docs)
        return docs


    def parse_docs(self) -> list:
        documents = []
        for ext in self.allowed_extensions:
            # for file in glob.glob(f"{self.src_path}/*.{ext}"):
            ext = f"*.{ext}"
            for file in glob.glob(os.path.join(self.src_path, ext)):
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
        return documents
