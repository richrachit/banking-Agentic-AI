"""India-oriented KYC orchestration with conservative AI-assisted decisions.

This module does not connect to UIDAI, NSDL/Protean, CKYCR, sanctions, or V-CIP
vendors. Those checks must be performed by approved bank integrations; AI only
assists triage and cannot establish identity by itself.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from .document_ai import DocumentAIResult


class KycStatus(str, Enum):
    PENDING_EXTERNAL_VERIFICATION = "PENDING_EXTERNAL_VERIFICATION"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    REJECTED = "REJECTED"
    VERIFIED = "VERIFIED"


@dataclass(frozen=True)
class KycInput:
    consent_recorded: bool
    pan: str
    aadhaar: str | None = None
    ckyc_identifier: str | None = None
    pan_verified_by_issuer: bool = False
    aadhaar_verified_by_authorised_flow: bool = False
    vcip_completed: bool = False
    face_match_score: float | None = None
    sanctions_screening_clear: bool | None = None
    document_results: list[DocumentAIResult] = field(default_factory=list)


@dataclass(frozen=True)
class KycDecision:
    status: KycStatus
    reasons: list[str]
    required_actions: list[str]
    policy_version: str = "RBI KYC Direction, 2016 (as amended; review current RBI update before deployment)"


class IndiaKycAIAgent:
    """Combines deterministic prerequisites with document-AI triage outputs."""

    _pan_pattern = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
    _aadhaar_pattern = re.compile(r"^[0-9]{12}$")

    def assess(self, payload: KycInput) -> KycDecision:
        reasons: list[str] = []
        actions: list[str] = []
        if not payload.consent_recorded:
            return KycDecision(KycStatus.REJECTED, ["Explicit KYC consent is not recorded."], ["Obtain consent before processing identity data."])
        if not self._pan_pattern.fullmatch(payload.pan.upper()):
            return KycDecision(KycStatus.REJECTED, ["PAN format is invalid."], ["Correct PAN and retry."])
        if payload.aadhaar and (not self._aadhaar_pattern.fullmatch(payload.aadhaar) or not self._verhoeff_valid(payload.aadhaar)):
            return KycDecision(KycStatus.REJECTED, ["Aadhaar checksum is invalid."], ["Correct Aadhaar through an authorised customer journey."])
        if any(result.recommendation == "INVALID" for result in payload.document_results):
            reasons.append("At least one document failed safety or quality checks.")
            actions.append("Route the case to KYC operations for document review.")
        if any(result.tamper_risk >= 0.40 for result in payload.document_results):
            reasons.append("Document-AI tamper-risk threshold reached.")
            actions.append("Open fraud investigation; do not rely on the document for CDD.")
        if payload.face_match_score is not None and payload.face_match_score < 0.85:
            reasons.append("Face-match confidence is below the configured review threshold.")
            actions.append("Perform authorised V-CIP or manual identity review.")
        if payload.sanctions_screening_clear is False:
            return KycDecision(KycStatus.MANUAL_REVIEW, reasons + ["Screening requires escalation."], actions + ["Escalate under the AML/CFT policy."])
        if not payload.pan_verified_by_issuer:
            actions.append("Verify PAN through the issuing-authority/DigiLocker-approved integration.")
        if not (payload.aadhaar_verified_by_authorised_flow or payload.ckyc_identifier or payload.vcip_completed):
            actions.append("Complete authorised Aadhaar/OVD, CKYCR, or V-CIP verification.")
        if reasons:
            return KycDecision(KycStatus.MANUAL_REVIEW, reasons, actions)
        if actions:
            return KycDecision(KycStatus.PENDING_EXTERNAL_VERIFICATION, ["KYC prerequisites remain outstanding."], actions)
        return KycDecision(KycStatus.VERIFIED, ["All supplied deterministic and approved-provider KYC checks passed."], [])

    @staticmethod
    def _verhoeff_valid(number: str) -> bool:
        # Verhoeff checksum is a local format check, not Aadhaar authentication.
        multiplication = ((0,1,2,3,4,5,6,7,8,9),(1,2,3,4,0,6,7,8,9,5),(2,3,4,0,1,7,8,9,5,6),(3,4,0,1,2,8,9,5,6,7),(4,0,1,2,3,9,5,6,7,8),(5,9,8,7,6,0,4,3,2,1),(6,5,9,8,7,1,0,4,3,2),(7,6,5,9,8,2,1,0,4,3),(8,7,6,5,9,3,2,1,0,4),(9,8,7,6,5,4,3,2,1,0))
        permutation = ((0,1,2,3,4,5,6,7,8,9),(1,5,7,6,2,8,3,0,9,4),(5,8,0,3,7,9,6,1,4,2),(8,9,1,6,0,4,3,5,2,7),(9,4,5,3,1,2,6,8,7,0),(4,2,8,6,5,7,3,9,0,1),(2,7,9,3,8,0,6,4,1,5),(7,0,4,6,9,1,3,2,5,8))
        check = 0
        for index, char in enumerate(reversed(number)):
            check = multiplication[check][permutation[index % 8][int(char)]]
        return check == 0
