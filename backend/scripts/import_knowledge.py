#!/usr/bin/env python3
"""Import health knowledge documents into the RAG vector index.

Supported inputs:
- Local PDF / HTML / TXT / Markdown files
- HTTP(S) URLs pointing to PDF or HTML pages
- JSON / JSONL files with records containing title/content/source/metadata

Example:
    python scripts/import_knowledge.py \
        --input ./knowledge/sleep_guideline.pdf \
        --input https://example.org/health-guide.html \
        --category lifestyle \
        --topic sleep \
        --metadata authority=example \
        --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import mimetypes
import re
import sys
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.rag.knowledge_base import KnowledgeBase
from app.rag.retriever import rag_retriever

logger = logging.getLogger("import_knowledge")


@dataclass
class RawDocument:
    title: str
    content: str
    source: str
    source_type: str
    metadata: dict[str, Any] = field(default_factory=dict)


def parse_key_value(items: list[str] | None) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for item in items or []:
        if "=" not in item:
            raise ValueError(f"Metadata must use key=value format: {item}")
        key, value = item.split("=", 1)
        metadata[key.strip()] = value.strip()
    return metadata


def stable_id(*parts: str) -> str:
    text = "::".join(part for part in parts if part)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def clean_text(text: str) -> str:
    """Normalize extracted text and remove common low-value boilerplate."""
    text = text.replace("\x00", " ")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    cleaned_lines: list[str] = []
    boilerplate_patterns = [
        r"^\s*\d+\s*$",
        r"^\s*page\s+\d+\s*(of\s+\d+)?\s*$",
        r"^\s*第\s*\d+\s*页\s*$",
        r"^\s*(copyright|all rights reserved)\b",
    ]
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append("")
            continue
        lowered = stripped.lower()
        if any(re.search(pattern, lowered, re.IGNORECASE) for pattern in boilerplate_patterns):
            continue
        cleaned_lines.append(stripped)

    text = "\n".join(cleaned_lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf_text(data: bytes) -> tuple[str, dict[str, Any]]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("PDF import requires pypdf. Install requirements.txt first.") from exc

    reader = PdfReader(BytesIO(data))
    parts: list[str] = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text.strip():
            parts.append(page_text)

    metadata = {
        "page_count": len(reader.pages),
    }
    if reader.metadata:
        pdf_title = getattr(reader.metadata, "title", None)
        if pdf_title:
            metadata["pdf_title"] = str(pdf_title)

    return "\n\n".join(parts), metadata


def extract_html_text(data: bytes) -> tuple[str, str | None]:
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise RuntimeError("HTML import requires beautifulsoup4. Install requirements.txt first.") from exc

    soup = BeautifulSoup(data, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "header", "footer", "aside"]):
        tag.decompose()

    title = soup.title.get_text(" ", strip=True) if soup.title else None
    main = soup.find("article") or soup.find("main") or soup.body or soup
    text = main.get_text("\n", strip=True)
    return text, title


def read_json_records(path: Path) -> list[RawDocument]:
    if path.suffix.lower() == ".jsonl":
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = payload if isinstance(payload, list) else payload.get("documents", [payload])

    documents: list[RawDocument] = []
    for index, record in enumerate(records, start=1):
        content = clean_text(str(record.get("content") or record.get("text") or ""))
        if not content:
            logger.warning("Skip empty JSON record %s in %s", index, path)
            continue
        title = str(record.get("title") or path.stem)
        metadata = record.get("metadata") or {}
        documents.append(
            RawDocument(
                title=title,
                content=content,
                source=str(record.get("source") or path),
                source_type="json",
                metadata=metadata,
            )
        )
    return documents


def detect_source_type(name: str, content_type: str | None = None) -> str:
    suffix = Path(urlparse(name).path or name).suffix.lower()
    content_type = (content_type or "").lower()
    if suffix == ".pdf" or "application/pdf" in content_type:
        return "pdf"
    if suffix in {".html", ".htm"} or "text/html" in content_type:
        return "html"
    if suffix in {".json", ".jsonl"}:
        return "json"
    return "text"


async def load_url(url: str, timeout: float = 30.0) -> list[RawDocument]:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()

    source_type = detect_source_type(url, response.headers.get("content-type"))
    data = response.content
    title = Path(urlparse(url).path).stem or urlparse(url).netloc
    metadata: dict[str, Any] = {"url": url}

    if source_type == "pdf":
        text, pdf_metadata = extract_pdf_text(data)
        metadata.update(pdf_metadata)
        title = str(pdf_metadata.get("pdf_title") or title)
    elif source_type == "html":
        text, html_title = extract_html_text(data)
        title = html_title or title
    else:
        text = data.decode(response.encoding or "utf-8", errors="ignore")

    return [
        RawDocument(
            title=title,
            content=clean_text(text),
            source=url,
            source_type=source_type,
            metadata=metadata,
        )
    ]


def load_local_file(path: Path) -> list[RawDocument]:
    source_type = detect_source_type(str(path), mimetypes.guess_type(path)[0])
    if source_type == "json":
        return read_json_records(path)

    data = path.read_bytes()
    title = path.stem
    metadata: dict[str, Any] = {"path": str(path)}

    if source_type == "pdf":
        text, pdf_metadata = extract_pdf_text(data)
        metadata.update(pdf_metadata)
        title = str(pdf_metadata.get("pdf_title") or title)
    elif source_type == "html":
        text, html_title = extract_html_text(data)
        title = html_title or title
    else:
        text = data.decode("utf-8", errors="ignore")

    return [
        RawDocument(
            title=title,
            content=clean_text(text),
            source=str(path),
            source_type=source_type,
            metadata=metadata,
        )
    ]


async def load_inputs(inputs: Iterable[str], recursive: bool = False) -> list[RawDocument]:
    documents: list[RawDocument] = []
    for item in inputs:
        if item.startswith(("http://", "https://")):
            documents.extend(await load_url(item))
            continue

        path = Path(item).expanduser().resolve()
        if path.is_dir():
            pattern = "**/*" if recursive else "*"
            supported = {".pdf", ".html", ".htm", ".txt", ".md", ".markdown", ".json", ".jsonl"}
            for child in sorted(path.glob(pattern)):
                if child.is_file() and child.suffix.lower() in supported:
                    documents.extend(load_local_file(child))
            continue

        if not path.exists():
            raise FileNotFoundError(f"Input does not exist: {item}")
        documents.extend(load_local_file(path))

    return documents


def build_documents(
    raw_documents: list[RawDocument],
    *,
    category: str | None,
    topic: str | None,
    global_metadata: dict[str, Any],
    chunk_size: int,
    chunk_overlap: int,
) -> list[dict[str, Any]]:
    """Clean, chunk, and convert raw documents to retriever documents."""
    chunker = KnowledgeBase(
        embedding_model=None,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        index_name="unused",
    )
    docs: list[dict[str, Any]] = []

    for raw in raw_documents:
        content = clean_text(raw.content)
        if not content:
            logger.warning("Skip empty document: %s", raw.source)
            continue

        chunks = chunker.chunk_text(content)
        total_chunks = len(chunks)
        for chunk in chunks:
            chunk_id = int(chunk.get("chunk_id", 0))
            metadata = {
                **global_metadata,
                **raw.metadata,
                "category": category or raw.metadata.get("category"),
                "topic": topic or raw.metadata.get("topic"),
                "document_title": raw.title,
                "source_type": raw.source_type,
                "chunk_id": chunk_id,
                "chunk_index": chunk_id,
                "chunk_total": total_chunks,
                "chunk_start": chunk.get("start", 0),
                "chunk_end": chunk.get("end", 0),
            }
            metadata = {key: value for key, value in metadata.items() if value not in (None, "")}

            docs.append(
                {
                    "id": stable_id(raw.source, raw.title, str(chunk_id), chunk["text"]),
                    "title": raw.title,
                    "content": chunk["text"],
                    "source": raw.source,
                    "metadata": metadata,
                }
            )

    return docs


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import PDF/HTML/text knowledge into the RAG vector index.")
    parser.add_argument("--input", "-i", action="append", required=True, help="File, directory, or URL. Can repeat.")
    parser.add_argument("--recursive", action="store_true", help="Recursively scan input directories.")
    parser.add_argument("--category", help="Knowledge category, e.g. nutrition, exercise, lifestyle.")
    parser.add_argument("--topic", help="Knowledge topic, e.g. sleep, aerobic, blood_pressure.")
    parser.add_argument("--metadata", action="append", help="Extra metadata in key=value format. Can repeat.")
    parser.add_argument("--chunk-size", type=int, default=700, help="Maximum chunk size in characters.")
    parser.add_argument("--chunk-overlap", type=int, default=80, help="Chunk overlap in characters.")
    parser.add_argument("--dry-run", action="store_true", help="Parse and chunk only; do not write to Elasticsearch.")
    parser.add_argument("--preview", type=int, default=3, help="Number of chunks to preview.")
    return parser


async def run_import(args: argparse.Namespace) -> list[str]:
    raw_documents = await load_inputs(args.input, recursive=args.recursive)
    documents = build_documents(
        raw_documents,
        category=args.category,
        topic=args.topic,
        global_metadata=parse_key_value(args.metadata),
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )

    logger.info("Loaded %d source documents; built %d chunks", len(raw_documents), len(documents))
    for index, doc in enumerate(documents[: args.preview], start=1):
        logger.info(
            "Preview %d: title=%s source=%s content=%s",
            index,
            doc["title"],
            doc["source"],
            doc["content"][:160].replace("\n", " "),
        )

    if args.dry_run:
        logger.info("Dry run enabled; skip vector index import")
        return [doc["id"] for doc in documents]

    indexed_ids = await rag_retriever.add_documents(documents)
    logger.info("Imported %d chunks into RAG index", len(indexed_ids))
    return indexed_ids


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    args = build_arg_parser().parse_args()
    if args.chunk_overlap >= args.chunk_size:
        raise SystemExit("--chunk-overlap must be smaller than --chunk-size")
    asyncio.run(run_import(args))


if __name__ == "__main__":
    main()
