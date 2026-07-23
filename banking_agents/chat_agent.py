from __future__ import annotations

"""Read-only, role-aware assistant for browser and API clients."""

from dataclasses import asdict, dataclass
import re
from typing import Any

from .auth_service import AuthenticatedUser
from .document_verification import DocumentVerificationModel
from .models import Account, Approval, LoanApplication
from .repository import LocalRepository


@dataclass(frozen=True)
class ChatAction:
    label: str
    path: str


@dataclass(frozen=True)
class ChatAssistantResult:
    reply: str
    intent: str
    source: str
    suggested_prompts: list[str]
    actions: list[ChatAction]
    agent_name: str = "Banking Support Assistant"
    mode: str = "DETERMINISTIC_RETRIEVAL"
    read_only: bool = True
    authority_boundary: str = (
        "The assistant explains authorised workflow data only. It cannot submit, approve, reject, verify KYC, "
        "change a credit decision, disburse a loan, transfer funds, or update an account."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BankingSupportChatAgent:
    """Answers bounded support questions using role-scoped local workflow data."""

    mutating_patterns = (
        r"\b(?:can|could|will|please)\s+you\s+(?:approve|reject|disburse|override|transfer|verify)\b",
        r"\b(?:approve|reject|disburse|override|transfer)\s+(?:this|the|my|application|loan|account|claim|funds?)\b",
        r"\b(?:change (?:my )?score|verify my kyc|pay (?:the )?claim)\b",
    )

    def __init__(self, repository: LocalRepository) -> None:
        self.repository = repository
        self.document_model = DocumentVerificationModel()
        self._mode = "DETERMINISTIC_RETRIEVAL"

    def respond(self, message: str, current: AuthenticatedUser) -> ChatAssistantResult:
        text = " ".join(message.lower().split())
        trained_intent = "FALLBACK"
        loans = self._visible_loans(current)
        accounts = self._visible_accounts(current)
        approvals = self._visible_approvals(current)
        loan = self._mentioned_loan(text, loans)
        account = self._mentioned_account(text, accounts)

        if trained_intent == "ACTION_BOUNDARY" or any(re.search(pattern, text) for pattern in self.mutating_patterns):
            return self._result(
                "ACTION_BOUNDARY",
                "I can explain the workflow and show where an authorised user can act, but I cannot perform or "
                "simulate approvals, rejections, KYC verification, credit overrides, disbursement, or money movement.",
                current,
                self._role_actions(current.role),
            )
        if trained_intent == "WELCOME" or not text or text in {"hi", "hello", "hey", "help", "start"}:
            return self._result("WELCOME", self._welcome(current.role), current, self._role_actions(current.role))
        if trained_intent == "CREDIT_GUIDANCE" or any(term in text for term in {"cibil", "credit score", "bureau score", "credit bureau"}):
            return self._credit_response(current, loan)
        if trained_intent == "DOCUMENT_GUIDANCE" or any(term in text for term in {"document", "documents", "upload", "salary slip", "bank statement", "aadhaar", "pan"}):
            return self._document_response(current, text, loan)
        if trained_intent == "DORMANCY_STATUS" or any(term in text for term in {"dormant", "dormancy", "inactive account", "reactivate", "reactivation", "dea fund", "unclaimed"}):
            return self._dormancy_response(current, accounts, account)
        if trained_intent == "APPROVAL_QUEUE" or any(term in text for term in {"approval", "approvals", "pending decision", "my queue", "review queue"}):
            return self._approval_response(current, approvals)
        if trained_intent == "LOAN_STATUS" or any(term in text for term in {"status", "loan", "application", "progress", "next step", "where is"}):
            return self._loan_response(current, loans, loan)
        if trained_intent == "AI_EXPLANATION" or any(term in text for term in {"ai model", "model registry", "agent", "automation", "how ai"}):
            actions = [ChatAction("Open AI registry", "/models")] if current.role == "ADMIN" else []
            return self._result(
                "AI_EXPLANATION",
                "The system uses bounded agents for bureau routing, document checks, loan exceptions, KYC controls, "
                "dormancy, and automation. Learned models are advisory only; policy and human approval remain authoritative.",
                current,
                actions,
            )
        return self._result(
            "FALLBACK",
            "I could not map that question to an authorised workflow topic. Ask about loan status, documents, the "
            "credit-bureau assessment, pending approvals, AI agents, or dormant-account reactivation.",
            current,
            self._role_actions(current.role),
        )

    def _credit_response(self, current: AuthenticatedUser, loan: LoanApplication | None) -> ChatAssistantResult:
        if current.role == "COMPLIANCE":
            return self._result("CREDIT_SCOPE", "Credit-bureau information is outside the Compliance workspace.", current)
        if loan:
            score = str(loan.credit_score) if loan.credit_score is not None else "no score returned"
            reply = (
                f"Application {loan.application_id} has bureau result {score}, band "
                f"{loan.credit_score_band.replace('_', ' ').lower()}, and decision "
                f"{loan.credit_score_decision.replace('_', ' ').lower()}. A high score only continues the workflow; "
                "it does not approve the loan."
            )
            return self._result("CREDIT_STATUS", reply, current, [ChatAction("Open application", f"/loans/{loan.application_id}")])
        return self._result(
            "CREDIT_GUIDANCE",
            "The customer supplies PAN and explicit consent; the configured bureau adapter retrieves the score. "
            "Customers never enter a score, and review paths remain human-governed.",
            current,
            [ChatAction("View loan applications", "/loans")],
        )

    def _document_response(self, current: AuthenticatedUser, text: str, loan: LoanApplication | None) -> ChatAssistantResult:
        product = loan.loan_product if loan else self._product_from_text(text)
        required = list(self.document_model.requirements_for(product))
        if loan:
            missing = [name for name in required if loan.document_evidence.get(name) != "VALID"]
            detail = ", ".join(item.replace("_", " ").title() for item in missing) or "none"
            reply = (
                f"For {loan.application_id}, the {product.lower()}-loan documents still needing valid evidence are: {detail}. "
                "Each file remains pending until approved verification and review are complete."
            )
            actions = [ChatAction("Open application", f"/loans/{loan.application_id}")]
        else:
            names = ", ".join(item.replace("_", " ").title() for item in required)
            reply = f"The configured {product.lower()}-loan document set is: {names}. Extra evidence can still be requested for an exception."
            actions = [ChatAction("View loan applications", "/loans")]
        return self._result("DOCUMENT_GUIDANCE", reply, current, actions)

    def _dormancy_response(
        self,
        current: AuthenticatedUser,
        accounts: list[Account],
        account: Account | None,
    ) -> ChatAssistantResult:
        if current.role not in {"CUSTOMER", "COMPLIANCE", "ADMIN"}:
            return self._result(
                "ACCOUNT_SCOPE",
                "Dormant-account information is available to the account holder, Compliance, and authorised administrators.",
                current,
            )
        if account:
            reply = self._account_reply(account)
        elif accounts:
            counts: dict[str, int] = {}
            for item in accounts:
                counts[item.status] = counts.get(item.status, 0) + 1
            summary = ", ".join(f"{count} {status.replace('_', ' ').lower()}" for status, count in sorted(counts.items()))
            reply = f"Your authorised account view contains {len(accounts)} account(s): {summary}."
        else:
            reply = "No dormant-account records are visible to your current role and identity."
        return self._result("DORMANCY_STATUS", reply, current, [ChatAction("Open dormant accounts", "/accounts")])

    def _approval_response(self, current: AuthenticatedUser, approvals: list[Approval]) -> ChatAssistantResult:
        if current.role == "CUSTOMER":
            return self._result(
                "APPROVAL_GUIDANCE",
                "Bank approval queues are not exposed to customers. Your application shows its customer-safe status and required action.",
                current,
                [ChatAction("View my applications", "/loans")],
            )
        pending = [item for item in approvals if item.status == "PENDING"]
        kinds: dict[str, int] = {}
        for item in pending:
            kinds[item.kind] = kinds.get(item.kind, 0) + 1
        detail = ", ".join(f"{count} {kind.replace('_', ' ').lower()}" for kind, count in sorted(kinds.items())) or "none"
        return self._result(
            "APPROVAL_QUEUE",
            f"There are {len(pending)} pending item(s) in your authorised queue: {detail}. Decisions must be recorded "
            "on the approval workbench with the required authority and justification.",
            current,
            [ChatAction("Open approvals", "/approvals")],
        )

    def _loan_response(
        self,
        current: AuthenticatedUser,
        loans: list[LoanApplication],
        loan: LoanApplication | None,
    ) -> ChatAssistantResult:
        if current.role == "COMPLIANCE":
            return self._result(
                "LOAN_SCOPE",
                "Loan details are outside the Compliance workspace. I can help with dormant accounts and compliance approvals.",
                current,
                [ChatAction("Open dormant accounts", "/accounts")],
            )
        if loan:
            return self._result(
                "LOAN_STATUS",
                self._loan_reply(loan),
                current,
                [ChatAction("Open application", f"/loans/{loan.application_id}")],
            )
        if loans:
            latest = sorted(loans, key=lambda item: item.application_id)[-1]
            return self._result(
                "LOAN_STATUS",
                f"I found {len(loans)} application(s) visible to you. The latest is {latest.application_id}. {self._loan_reply(latest)}",
                current,
                [ChatAction("View loan applications", "/loans")],
            )
        return self._result(
            "LOAN_STATUS",
            "No loan applications are visible to your current role and identity.",
            current,
            [ChatAction("View loan applications", "/loans")],
        )

    def _visible_loans(self, current: AuthenticatedUser) -> list[LoanApplication]:
        if current.role == "COMPLIANCE":
            return []
        loans = self.repository.list_loans()
        if current.role == "CUSTOMER":
            return [item for item in loans if item.submitted_by == current.username]
        return loans

    def _visible_accounts(self, current: AuthenticatedUser) -> list[Account]:
        if current.role not in {"CUSTOMER", "COMPLIANCE", "ADMIN"}:
            return []
        accounts = self.repository.list_accounts()
        if current.role == "CUSTOMER":
            return [item for item in accounts if item.customer_id == current.customer_id]
        return accounts

    def _visible_approvals(self, current: AuthenticatedUser) -> list[Approval]:
        approvals = self.repository.list_approvals()
        if current.role == "CREDIT":
            return [item for item in approvals if item.required_role == "credit.manager"]
        if current.role == "COMPLIANCE":
            return [item for item in approvals if item.required_role == "compliance.officer"]
        if current.role == "LOAN":
            kinds = {"LOAN_DEVIATION", "CREDIT_SCORE_REVIEW", "CREDIT_BUREAU_UNAVAILABLE", "CREDIT_RECONSIDERATION"}
            return [item for item in approvals if item.kind in kinds]
        return approvals if current.role == "ADMIN" else []

    @staticmethod
    def _mentioned_loan(message: str, loans: list[LoanApplication]) -> LoanApplication | None:
        return next((item for item in loans if item.application_id.lower() in message), None)

    @staticmethod
    def _mentioned_account(message: str, accounts: list[Account]) -> Account | None:
        return next((item for item in accounts if item.account_id.lower() in message), None)

    @staticmethod
    def _product_from_text(message: str) -> str:
        if re.search(r"\b(home|mortgage|property)\b", message):
            return "HOME"
        if re.search(r"\b(business|company|enterprise)\b", message):
            return "BUSINESS"
        return "PERSONAL"

    @staticmethod
    def _loan_reply(loan: LoanApplication) -> str:
        next_steps = {
            "AWAITING_CUSTOMER": "Upload or replace the requested documents shown on the application.",
            "AWAITING_APPROVAL": "An authorised bank reviewer must record the pending decision.",
            "READY_FOR_MAIN_JOURNEY": "The exception stage is complete and the application can continue to the bank's main journey.",
            "REJECTED": "Review the recorded reason. A low-score rejection can be submitted for governed reconsideration.",
            "HELD": "The agent or Loan Operations must resolve the recorded exception.",
            "REOPENED": "The case has been reopened for evidence and policy reassessment.",
        }
        diagnosis = loan.diagnosis or "No additional diagnosis is recorded."
        next_step = next_steps.get(loan.status, "Open the application for the recorded next action.")
        return (
            f"Application {loan.application_id} is {loan.status.replace('_', ' ').lower()}. "
            f"Recorded explanation: {diagnosis} Next step: {next_step}"
        )

    @staticmethod
    def _account_reply(account: Account) -> str:
        next_steps = {
            "ACTIVE": "No reactivation is required.",
            "OUTREACH": "Confirm customer activity or complete the bank's re-engagement step.",
            "DORMANT": "The account holder can request reactivation after confirming current KYC.",
            "TRANSFER_PENDING": "Compliance approval remains pending; eligible reactivation can still be requested.",
            "TRANSFERRED": "A customer reclaim must follow the bank's claim and compliance process.",
            "CLAIM_PENDING": "The claim is awaiting its authorised review or execution step.",
            "CLAIM_PAID": "The recorded claim workflow is complete.",
        }
        next_step = next_steps.get(account.status, "Open the account workspace for the recorded next action.")
        return f"Account {account.account_id} is {account.status.replace('_', ' ').lower()}. Next step: {next_step}"

    @staticmethod
    def _welcome(role: str) -> str:
        copy = {
            "CUSTOMER": "I can explain your loan status, documents, bureau step, or dormant-account reactivation.",
            "LOAN": "I can summarize loan exceptions, document requirements, credit routing, and visible approval context.",
            "CREDIT": "I can summarize credit-review cases, bureau routing, and decisions assigned to your role.",
            "COMPLIANCE": "I can summarize dormant accounts, reactivation, unclaimed balances, and compliance approvals.",
            "ADMIN": "I can summarize workflow status, approval queues, automation boundaries, and the AI registry.",
        }
        return copy.get(role, "I can explain authorised banking workflow information.")

    @staticmethod
    def suggestions_for(role: str) -> list[str]:
        suggestions = {
            "CUSTOMER": [
                "What is the status of my latest loan?",
                "Which documents are required for a personal loan?",
                "How do I reactivate a dormant account?",
                "How does the credit-bureau step work?",
            ],
            "LOAN": [
                "Summarize my loan exception queue",
                "Which documents are required for a home loan?",
                "Explain the credit-bureau review path",
                "What can the AI agent automate?",
            ],
            "CREDIT": [
                "How many approvals are pending?",
                "Explain low-score reconsideration",
                "Show the latest loan status",
                "What actions remain human-controlled?",
            ],
            "COMPLIANCE": [
                "Summarize dormant accounts",
                "How does reactivation work?",
                "How many compliance approvals are pending?",
                "Explain the unclaimed-balance workflow",
            ],
            "ADMIN": [
                "Summarize pending approvals",
                "Explain all AI agents",
                "Show the latest loan status",
                "How is automation governed?",
            ],
        }
        return suggestions.get(role, ["What can you help me with?"])

    @staticmethod
    def _role_actions(role: str) -> list[ChatAction]:
        actions = [ChatAction("Open dashboard", "/dashboard")]
        if role in {"CUSTOMER", "LOAN", "CREDIT", "ADMIN"}:
            actions.append(ChatAction("View loans", "/loans"))
        if role in {"CUSTOMER", "COMPLIANCE", "ADMIN"}:
            actions.append(ChatAction("View dormant accounts", "/accounts"))
        if role in {"LOAN", "CREDIT", "COMPLIANCE", "ADMIN"}:
            actions.append(ChatAction("Open approvals", "/approvals"))
        return actions

    def _result(
        self,
        intent: str,
        reply: str,
        current: AuthenticatedUser,
        actions: list[ChatAction] | None = None,
    ) -> ChatAssistantResult:
        return ChatAssistantResult(
            reply=reply,
            intent=intent,
            source="ROLE_SCOPED_LOCAL_WORKFLOW_DATA",
            suggested_prompts=self.suggestions_for(current.role),
            actions=actions or [],
            mode=self._mode,
        )
