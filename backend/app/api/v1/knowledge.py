import logging
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.config import settings
from app.models.user import User
from app.rag.retriever import rag_retriever
from scripts.import_knowledge import RawDocument, build_documents, clean_text, extract_pdf_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

class KnowledgeImportResponse(BaseModel):
    status: str = Field(..., description="Import status: completed or dry_run")
    filename: str
    title: str
    source_type: str
    category: str | None = None
    topic: str | None = None
    source_document_count: int
    chunk_count: int
    imported_count: int
    index_name: str
    dry_run: bool = False
    preview_ids: list[str] = Field(default_factory=list)


def _is_pdf(file: UploadFile) -> bool:
    filename = (file.filename or "").lower()
    content_type = (file.content_type or "").lower()
    return filename.endswith(".pdf") or content_type == "application/pdf"

def _is_markdown(file: UploadFile) -> bool:
    filename = (file.filename or "").lower()
    content_type = (file.content_type or "").lower()
    if filename:
        return filename.endswith((".md", ".markdown"))
    return content_type in {"text/markdown", "text/x-markdown", "text/plain"}

def _detect_upload_type(file: UploadFile) -> str:
    if _is_pdf(file):
        return "pdf"
    if _is_markdown(file):
        return "markdown"
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只支持上传 PDF 或 Markdown 文件")

def _extract_uploaded_text(file: UploadFile, data: bytes, source_type: str) -> tuple[str, str, dict[str, Any]]:
    if source_type == "pdf":
        try:
            text, metadata = extract_pdf_text(data)
        except Exception as exc:
            logger.exception("[KnowledgeImport] Failed to extract PDF text: filename=%s", file.filename)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"PDF 解析失败：{exc}") from exc
        title = str(metadata.get("pdf_title") or file.filename or "uploaded_pdf")
        return title, text, metadata

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("utf-8", errors="ignore")
    title = file.filename.rsplit(".", 1)[0] if file.filename else "uploaded_markdown"
    return title, text, {}

async def _import_file_to_knowledge_base(
    *,
    file: UploadFile,
    category: str | None,
    topic: str | None,
    chunk_size: int,
    chunk_overlap: int,
    dry_run: bool,
    current_user: User,
) -> KnowledgeImportResponse:
    source_type = _detect_upload_type(file)
    display_type = "PDF" if source_type == "pdf" else "Markdown"

    if chunk_size <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="chunk_size 必须大于 0")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="chunk_overlap 必须小于 chunk_size")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{display_type} 文件为空")
    if len(data) > settings.max_knowledge_pdf_bytes:
        max_mb = settings.max_knowledge_pdf_bytes // (1024 * 1024)
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=f"{display_type} 文件不能超过 {max_mb} MB")

    title, text, extracted_metadata = _extract_uploaded_text(file, data, source_type)
    cleaned_text = clean_text(text)
    if not cleaned_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{display_type} 未解析出可入库的文本内容")

    metadata: dict[str, Any] = {
        **extracted_metadata,
        "filename": file.filename,
        "uploaded_by": current_user.username,
        "upload_channel": "admin_file_upload",
    }
    raw_documents = [
        RawDocument(
            title=title,
            content=cleaned_text,
            source=f"admin-upload://{file.filename}",
            source_type=source_type,
            metadata=metadata,
        )
    ]
    documents = build_documents(
        raw_documents,
        category=category,
        topic=topic,
        global_metadata={},
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    if not documents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{display_type} 内容切分后没有可入库片段")

    if dry_run:
        indexed_ids = [doc["id"] for doc in documents]
    else:
        try:
            indexed_ids = await rag_retriever.add_documents(documents)
        except Exception as exc:
            logger.exception("[knowledgeImport] Failed to index chunks: filename=%s", file.filename)
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"向量数据库入库失败：{exc}") from exc

    return KnowledgeImportResponse(
        status="dry_run" if dry_run else "completed",
        filename=file.filename or f"uploaded.{source_type}",
        title=title,
        source_type=source_type,
        category=category,
        topic=topic,
        source_document_count=len(raw_documents),
        chunk_count=len(documents),
        imported_count=0 if dry_run else len(indexed_ids),
        index_name=settings.rag_index_name,
        dry_run=dry_run,
        preview_ids=indexed_ids[:5]
    )

@router.post("/import-file", response_model=KnowledgeImportResponse)
async def import_file_to_knowledge_base(
    file: UploadFile = File(..., description="PDF or Markdown knowledge document"),
    category: str | None = Form(default="health"),
    topic: str | None = Form(default=None),
    chunk_size: int = Form(default=700),
    chunk_overlap: int = Form(default=80),
    dry_run: bool = Form(default=False),
    current_user: User = Depends(get_current_user),
) -> KnowledgeImportResponse:
    """Parse an uploaded PDF or Markdown file and import it into the RAG vector index."""
    return await _import_file_to_knowledge_base(
        file=file,
        category=category,
        topic=topic,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        dry_run=dry_run,
        current_user=current_user,
    )

@router.post("/import-pdf", response_model=KnowledgeImportResponse)
async def import_pdf_to_knowledge_base(
    file: UploadFile = File(..., description="PDF guideline or knowledge document"),
    category: str | None = Form(default="health"),
    topic: str | None = Form(default=None),
    chunk_size: int = Form(default=700),
    chunk_overlap: int = Form(default=80),
    dry_run: bool = Form(default=False),
    current_user: User = Depends(get_current_user),
) -> KnowledgeImportResponse:
    """Backward-compatible PDF import endpoint."""
    if not _is_pdf(file):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只支持上传 PDF 文件")
    return await _import_file_to_knowledge_base(
        file=file,
        category=category,
        topic=topic,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        dry_run=dry_run,
        current_user=current_user,
    )