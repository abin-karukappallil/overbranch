import os
import uuid
import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings

from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams, Distance, PointStruct,
    Filter, FieldCondition, MatchValue,
)

from chunker import semantic_chunk_latex

load_dotenv()

logger = logging.getLogger("vector_sync")
logging.basicConfig(level=logging.INFO)

router = APIRouter()
COLLECTION_NAME = "latex_chunks"

class SyncFileRequest(BaseModel):
    project_id: str = Field(..., description="Project ID or UUID")
    file_path: str = Field(..., description="Path of the TeX file")
    new_code: str = Field(..., description="Raw LaTeX code to chunk and embed")

_qdrant_client_instance: Optional[QdrantClient] = None

def get_qdrant_client() -> QdrantClient:
    global _qdrant_client_instance
    if _qdrant_client_instance is not None:
        return _qdrant_client_instance

    qdrant_url = os.getenv("QDRANT_URL")
    api_key = os.getenv("QDRANT_API_KEY")

    if not qdrant_url:
        raise ValueError("QDRANT_URL environment variable is missing.")

    client = QdrantClient(url=qdrant_url, api_key=api_key, timeout=10)
    logger.info(f"Connected directly to Qdrant Cloud DB at {qdrant_url}")
    _qdrant_client_instance = client
    return _qdrant_client_instance

def ensure_qdrant_collection(client: QdrantClient, vector_size: int = 2048):
    if not client.collection_exists(COLLECTION_NAME):
        logger.info(f"Creating Qdrant collection '{COLLECTION_NAME}' (size={vector_size}, Cosine)...")
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
        )
    else:
        try:
            info = client.get_collection(COLLECTION_NAME)
            curr_size = info.config.params.vectors.size if hasattr(info.config.params.vectors, 'size') else vector_size
            if curr_size != vector_size:
                logger.info(f"Recreating Qdrant collection '{COLLECTION_NAME}' with size={vector_size} (was {curr_size})...")
                client.delete_collection(COLLECTION_NAME)
                client.create_collection(
                    collection_name=COLLECTION_NAME,
                    vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
                )
        except Exception as e:
            logger.warning(f"Collection check warning: {e}")

    try:
        from qdrant_client.models import PayloadSchemaType
        for field in ["project_id", "file_path", "chunk_type", "file_hash"]:
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD,
            )
        logger.info("Ensured payload indexes for project_id, file_path, chunk_type, file_hash.")
    except Exception as idx_err:
        logger.debug(f"Payload index creation note: {idx_err}")

def get_nvidia_embeddings() -> NVIDIAEmbeddings:
    nvidia_api_key = os.getenv("NVIDIA_API_KEY")
    return NVIDIAEmbeddings(
        model="nvidia/nemotron-3-embed-1b",
        nvidia_api_key=nvidia_api_key
    )

def _check_file_hash_unchanged(
    client: QdrantClient,
    project_id: str,
    file_path: str,
    new_hash: str,
) -> bool:
    try:
        from qdrant_client.models import ScrollRequest
        result = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=Filter(
                must=[
                    FieldCondition(key="project_id", match=MatchValue(value=project_id)),
                    FieldCondition(key="file_path", match=MatchValue(value=file_path)),
                ]
            ),
            limit=1,
            with_payload=True,
            with_vectors=False,
        )
        points = result[0] if result else []
        if points:
            existing_hash = points[0].payload.get("file_hash", "") if points[0].payload else ""
            if existing_hash == new_hash:
                return True
    except Exception as e:
        logger.debug(f"File hash check note: {e}")
    return False

@router.post("/api/sync-file")
def sync_file(req: SyncFileRequest):
    try:
        chunks = semantic_chunk_latex(req.new_code, req.project_id, req.file_path)
        logger.info(f"Semantic chunker produced {len(chunks)} chunks for '{req.file_path}'")

        if not chunks:
            return {"synced": True, "total_chunks": 0, "skipped": False}

        qdrant = get_qdrant_client()
        ensure_qdrant_collection(qdrant, vector_size=2048)

        file_hash = chunks[0].get("file_hash", "")
        if file_hash and _check_file_hash_unchanged(qdrant, req.project_id, req.file_path, file_hash):
            return {
                "synced": True,
                "total_chunks": len(chunks),
                "skipped": True,
                "file_hash": file_hash,
                "chunks": [
                    {
                        "chunk_index": c.get("chunk_index", 0),
                        "chunk_type": c.get("chunk_type", "paragraph"),
                        "section": c.get("section", ""),
                        "content": c.get("content", ""),
                        "summary": c.get("summary", ""),
                    }
                    for c in chunks
                ],
            }

        try:
            qdrant.delete(
                collection_name=COLLECTION_NAME,
                points_selector=Filter(
                    must=[
                        FieldCondition(key="project_id", match=MatchValue(value=req.project_id)),
                        FieldCondition(key="file_path", match=MatchValue(value=req.file_path)),
                    ]
                )
            )
            logger.info(f"Deleted existing points for project '{req.project_id}', file '{req.file_path}'.")
        except Exception as del_err:
            logger.warning(f"Deletion note (may be empty collection): {del_err}")

        embeddings_model = get_nvidia_embeddings()
        chunk_texts = [c["content"] for c in chunks]

        BATCH_SIZE = 20
        all_embeddings = []
        for i in range(0, len(chunk_texts), BATCH_SIZE):
            batch = chunk_texts[i:i + BATCH_SIZE]
            batch_embeddings = embeddings_model.embed_documents(batch)
            all_embeddings.extend(batch_embeddings)

        dim = len(all_embeddings[0]) if all_embeddings else 2048
        ensure_qdrant_collection(qdrant, vector_size=dim)

        points = []
        for idx, (chunk_meta, vector) in enumerate(zip(chunks, all_embeddings)):
            point_id = str(uuid.uuid5(
                uuid.NAMESPACE_DNS,
                f"{req.project_id}_{req.file_path}_{idx}_{file_hash}"
            ))
            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "project_id": chunk_meta["project_id"],
                        "file_path": chunk_meta["file_path"],
                        "chunk_index": chunk_meta["chunk_index"],
                        "chunk_type": chunk_meta["chunk_type"],
                        "start_line": chunk_meta["start_line"],
                        "end_line": chunk_meta["end_line"],
                        "content": chunk_meta["content"],
                        "summary": chunk_meta["summary"],
                        "file_hash": chunk_meta["file_hash"],
                        "last_modified": chunk_meta["last_modified"],
                    }
                )
            )

        for i in range(0, len(points), BATCH_SIZE):
            batch = points[i:i + BATCH_SIZE]
            qdrant.upsert(collection_name=COLLECTION_NAME, points=batch)

        logger.info(f"Upserted {len(points)} vector points into Qdrant '{COLLECTION_NAME}' ({dim} dims).")

        return {
            "synced": True,
            "total_chunks": len(chunks),
            "skipped": False,
            "file_hash": file_hash,
            "chunks": [
                {
                    "chunk_index": c.get("chunk_index", 0),
                    "chunk_type": c.get("chunk_type", "paragraph"),
                    "section": c.get("section", ""),
                    "content": c.get("content", ""),
                    "summary": c.get("summary", ""),
                }
                for c in chunks
            ],
            "chunk_types": [c["chunk_type"] for c in chunks],
        }

    except Exception as e:
        logger.error(f"Error during vector sync: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Vector sync failed: {str(e)}"
        )
