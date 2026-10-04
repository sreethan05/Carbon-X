"""Azure Document Intelligence wrapper for document OCR.

Uses the ``prebuilt-document`` model to extract text, tables and
key-value pairs from uploaded document images / PDFs.

Config (backend/.env):
    AZURE_URL      - Document Intelligence endpoint URL
    AZURE_DOC_KEY  - Document Intelligence API key
"""
import os

MODEL_ID = (os.getenv("AZURE_DOC_MODEL") or "prebuilt-layout").strip()
MAX_FILE_BYTES = 10 * 1024 * 1024

FALLBACK_ACTIONS = [
    {
        "id": "retry",
        "label": "Try again",
        "description": "The scanning service may recover shortly. Re-upload the document to retry.",
    },
    {
        "id": "send_to_fpo",
        "label": "Send to FPO",
        "description": "Forward the document photo to your FPO for manual verification instead.",
    },
]


def azure_unavailable_response(reason: str | None = None) -> dict:
    """JSON fallback when Azure Document Intelligence cannot be reached.

    Tells the caller to either retry the upload or send the document to
    their FPO for manual verification.
    """
    body = {
        "success": False,
        "fallback": True,
        "message": (
            "Document scanning service is temporarily unreachable. "
            "Please try again, or send the document to your FPO for manual verification."
        ),
        "actions": FALLBACK_ACTIONS,
    }
    if reason:
        body["detail"] = reason
    return body


def _read_config() -> tuple[str, str]:
    endpoint = (os.getenv("AZURE_URL") or "").strip()
    key = (os.getenv("AZURE_DOC_KEY") or "").strip()
    if not endpoint or not key:
        raise RuntimeError(
            "Azure Document Intelligence is not configured. "
            "Set AZURE_URL and AZURE_DOC_KEY in backend/.env."
        )
    return endpoint, key


def get_client():
    """Build a DocumentIntelligenceClient from env config."""
    try:
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.core.credentials import AzureKeyCredential
    except ImportError as exc:
        raise RuntimeError(
            "Azure Document Intelligence SDK is not installed. "
            "Run: pip install azure-ai-documentintelligence"
        ) from exc
    endpoint, key = _read_config()
    return DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(key))


def validate_upload(content_type: str | None, file_bytes: bytes) -> None:
    """Validate an uploaded file. Raises ValueError on rejection."""
    ctype = (content_type or "").lower()
    if not (ctype.startswith("image/") or ctype == "application/pdf"):
        raise ValueError(f"Unsupported file type: {content_type}. Upload an image or PDF.")
    if not file_bytes:
        raise ValueError("Uploaded file is empty.")
    if len(file_bytes) > MAX_FILE_BYTES:
        raise ValueError("File too large. Maximum size is 10 MB.")


def _polygon_to_points(polygon) -> list[dict] | None:
    if not polygon:
        return None
    pts = list(polygon)
    return [{"x": pts[i], "y": pts[i + 1]} for i in range(0, len(pts) - 1, 2)]


def analyze_document_bytes(file_bytes: bytes, filename: str | None = None) -> dict:
    """Send raw file bytes to Azure and return the extracted text as JSON-serializable dict."""
    client = get_client()
    try:
        poller = client.begin_analyze_document(model_id=MODEL_ID, body=file_bytes)
        result = poller.result()
    except Exception as exc:
        raise RuntimeError(f"Azure analysis failed: {exc}") from exc

    pages = []
    for page in result.pages or []:
        pages.append(
            {
                "page_number": page.page_number,
                "width": page.width,
                "height": page.height,
                "unit": page.unit,
                "lines": [
                    {"content": line.content, "polygon": _polygon_to_points(line.polygon)}
                    for line in page.lines or []
                ],
            }
        )

    tables = []
    for table in result.tables or []:
        tables.append(
            {
                "row_count": table.row_count,
                "column_count": table.column_count,
                "cells": [
                    {"row_index": c.row_index, "column_index": c.column_index, "content": c.content}
                    for c in table.cells or []
                ],
            }
        )

    key_values = []
    for kv in result.key_value_pairs or []:
        key_values.append(
            {
                "key": kv.key.content if kv.key else None,
                "value": kv.value.content if kv.value and kv.value.content else None,
            }
        )

    return {
        "success": True,
        "model": MODEL_ID,
        "filename": filename,
        "content": result.content,
        "pages": pages,
        "tables": tables,
        "key_value_pairs": key_values,
    }
