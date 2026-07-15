"""Pluggable AI pipeline for loan-document verification.

The baseline provider is intentionally non-decisive. Deploy an approved model
provider behind this interface before using document AI in a lending decision.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
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


class QwenVisionDocumentAIProvider:
    """Optional local Qwen2.5-VL provider for image-based document triage.

    Its output remains PENDING: it cannot prove authenticity or replace human
    review, identity checks, or deterministic policy controls.
    """

    def __init__(self, model_id: str | None = None) -> None:
        self.model_id = model_id or os.getenv("DOCUMENT_AI_MODEL", "Qwen/Qwen2.5-VL-3B-Instruct")
        self._model = None
        self._processor = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            import torch
            from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration
        except ImportError as error:
            raise RuntimeError("Install optional AI dependencies: pip install -r requirements-ai.txt") from error
        self._processor = AutoProcessor.from_pretrained(self.model_id)
        self._model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            self.model_id, torch_dtype="auto", device_map="auto" if torch.cuda.is_available() else "cpu"
        )

    def analyze(self, document_type: str, file_path: Path) -> DocumentAIResult:
        if file_path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            return DocumentAIResult(document_type, "qwen2.5-vl", self.model_id, 0, 0, 0, {}, "PENDING", ["Convert PDF to image before visual-model analysis."])
        self._load()
        from PIL import Image
        image = Image.open(file_path).convert("RGB")
        prompt = ("Identify the expected bank document, readable key fields, expiry information, and visible quality or tampering concerns. "
                  "Do not approve or reject it. Respond with concise JSON. Expected document: " + document_type)
        messages = [{"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": prompt}]}]
        text = self._processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self._processor(text=[text], images=[image], padding=True, return_tensors="pt").to(self._model.device)
        generated = self._model.generate(**inputs, max_new_tokens=384)
        response = self._processor.batch_decode(generated[:, inputs.input_ids.shape[1]:], skip_special_tokens=True)[0]
        return DocumentAIResult(document_type, "qwen2.5-vl", self.model_id, 0, 0, 0, {"model_response": response}, "PENDING", ["Vision-model output requires deterministic validation and human review."])


class DocumentAIPipeline:
    """Combines the required model stages and enforces conservative decisions."""

    def __init__(self, provider: DocumentAIProvider | None = None) -> None:
        selected = os.getenv("DOCUMENT_AI_PROVIDER", "baseline").lower()
        self.provider = provider or (QwenVisionDocumentAIProvider() if selected == "qwen" else BaselineDocumentAIProvider())

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
