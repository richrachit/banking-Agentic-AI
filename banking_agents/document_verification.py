"""Explainable document completeness and status validation for loan applications.

Feature connection: this is the document-verification engine behind the loan
review and approval flow. It checks whether incoming evidence satisfies the
product-based document requirements before the loan can proceed.

This is a rules model. Production verification should combine it with approved
OCR, document-authenticity, KYC, and fraud-screening integrations.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .document_ai import DocumentAIPipeline, DocumentAIResult


REQUIRED_DOCUMENTS: dict[str, tuple[str, ...]] = {
    "PERSONAL": ("PAN", "AADHAAR", "ADDRESS_PROOF", "BANK_STATEMENT", "INCOME_PROOF"),
    "HOME": ("PAN", "AADHAAR", "ADDRESS_PROOF", "BANK_STATEMENT", "INCOME_PROOF", "PROPERTY_DOCUMENT"),
    "BUSINESS": ("PAN", "AADHAAR", "BUSINESS_REGISTRATION", "BANK_STATEMENT", "FINANCIAL_STATEMENT"),
}
VALID_STATUSES = {"VALID", "PENDING", "INVALID", "EXPIRED", "UNREADABLE"}


@dataclass(frozen=True)
class DocumentVerificationResult:
    required: list[str]
    valid: list[str]
    missing: list[str]
    invalid: list[str]

    @property
    def approved_for_document_stage(self) -> bool:
        return not self.missing and not self.invalid


class DocumentVerificationModel:
    def requirements_for(self, loan_product: str) -> tuple[str, ...]:
        try:
            return REQUIRED_DOCUMENTS[loan_product.upper()]
        except KeyError as error:
            raise ValueError(f"Unsupported loan product: {loan_product}. Use {', '.join(REQUIRED_DOCUMENTS)}.") from error

    def verify(self, loan_product: str, evidence: dict[str, str], additional_required: list[str] | None = None) -> DocumentVerificationResult:
        required = list(dict.fromkeys(item.upper().strip() for item in [*self.requirements_for(loan_product), *(additional_required or [])]))
        normalized = {name.upper().strip(): status.upper().strip() for name, status in evidence.items()}
        unsupported = set(normalized.values()) - VALID_STATUSES
        if unsupported:
            raise ValueError(f"Invalid document status: {', '.join(sorted(unsupported))}.")
        valid = [item for item in required if normalized.get(item) == "VALID"]
        missing = [item for item in required if item not in normalized or normalized[item] == "PENDING"]
        invalid = [item for item in required if normalized.get(item) in {"INVALID", "EXPIRED", "UNREADABLE"}]
        return DocumentVerificationResult(required, valid, missing, invalid)

    def verify_uploaded_file(self, document_type: str, file_path: Path, pipeline: DocumentAIPipeline | None = None) -> DocumentAIResult:
        """Runs document AI; callers must persist evidence and route it for review."""
        return (pipeline or DocumentAIPipeline()).verify(document_type, file_path)
