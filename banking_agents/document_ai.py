"""Pluggable AI pipeline for loan-document verification.

Feature connection: this module supports the optional AI-assisted document
review experience for loan applications. It is not the database layer; it
returns analysis results that the workflow can persist and review.

The baseline provider is intentionally non-decisive. Deploy an approved model
provider behind this interface before using document AI in a lending decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class DocumentAIResult:
    document_type: str
    provider: str
    model_version: str
    classification_confidence: float
    ocr_confidence: float
    tamper_risk: float
    extracted_fields: dict[str, str]
    recommendation: str  # PENDING, VALID, or INVALID
    reasons: list[str]


class DocumentAIProvider(Protocol):
    """Contract for the approved document-AI platform used by the bank."""

    def analyze(self, document_type: str, file_path: Path) -> DocumentAIResult: ...


class BaselineDocumentAIProvider:
    """Local safe baseline: validates file presence/format; never authenticates it."""

    allowed_extensions = {".pdf", ".png", ".jpg", ".jpeg"}

    def analyze(self, document_type: str, file_path: Path) -> DocumentAIResult:
        problems: list[str] = []
        if not file_path.exists() or file_path.stat().st_size == 0:
            problems.append("File is missing or empty.")
        if file_path.suffix.lower() not in self.allowed_extensions:
            problems.append("Unsupported file type.")
        return DocumentAIResult(
            document_type=document_type,
            provider="baseline-local",
            model_version="1.0",
            classification_confidence=0.0,
            ocr_confidence=0.0,
            tamper_risk=0.0,
            extracted_fields={},
            recommendation="INVALID" if problems else "PENDING",
            reasons=problems or ["Awaiting approved OCR, fraud-model, and human review."],
        )


class DocumentAIPipeline:
    """Runs deterministic file safety checks before unified GenAI review."""

    def __init__(self, provider: DocumentAIProvider | None = None) -> None:
        self.provider = provider or BaselineDocumentAIProvider()

    def verify(self, document_type: str, file_path: Path) -> DocumentAIResult:
        result = self.provider.analyze(document_type, file_path)
        if result.recommendation not in {"PENDING", "VALID", "INVALID"}:
            raise ValueError("Document AI provider returned an unsupported recommendation.")
        return result


# Production model requirements to implement behind DocumentAIProvider:
# - Document classification and OCR (e.g. an approved Document Intelligence,
#   Google Document AI, PaddleOCR, or DocTR deployment).
# - Field extraction and cross-document matching: name, DOB, PAN/Aadhaar,
#   account number, income figures, statement period, and document expiry.
# - Document/image fraud scoring: tampering, screenshots, altered text,
#   duplicate/reprint signals, and template consistency.
# - Optional face/liveness matching only with explicit consent and legal approval.
# - A deterministic policy layer and human review for low-confidence/high-risk
#   results. Model confidence alone must never approve a loan or document.
