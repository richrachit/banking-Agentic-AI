from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from .audit import AuditLog
from .automation_agent import OperationsAutomationAgent
from .dormancy_agent import DormancyAgent
from .loan_agent import LoanExceptionAgent
from .models import Account, LoanApplication
from .policy import PolicyConfig
from .repository import LocalRepository

ROOT = Path.cwd(); DATA = ROOT / "data"


def services() -> tuple[LocalRepository, AuditLog, LoanExceptionAgent, DormancyAgent]:
    repo = LocalRepository(DATA / "state.json"); audit = AuditLog(DATA / "audit.jsonl"); policy = PolicyConfig()
    return repo, audit, LoanExceptionAgent(repo, audit, policy), DormancyAgent(repo, audit, policy)


def emit(value: object) -> None:
    print(json.dumps(value, default=lambda item: item.__dict__, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description="Local banking operations resolution agents")
    command = parser.add_subparsers(dest="command", required=True)
    command.add_parser("seed-demo"); command.add_parser("reset-demo")
    loan = command.add_parser("run-loan"); loan.add_argument("--application-id", required=True)
    dormancy = command.add_parser("run-dormancy"); dormancy.add_argument("--as-of", required=True)
    automated = command.add_parser("run-automation"); automated.add_argument("--as-of", required=True)
    decision = command.add_parser("decide"); decision.add_argument("--approval-id", required=True); decision.add_argument("--actor", required=True); decision.add_argument("--approve", action="store_true"); decision.add_argument("--note", default="")
    command.add_parser("execute-transfers"); command.add_parser("execute-claims"); command.add_parser("list-approvals"); command.add_parser("list-events")
    claim = command.add_parser("request-claim"); claim.add_argument("--account-id", required=True); claim.add_argument("--claim-id", required=True); claim.add_argument("--validated", action="store_true")
    args = parser.parse_args(); repo, audit, loan_agent, dormancy_agent = services()
    if args.command in ("seed-demo", "reset-demo"):
        repo.seed([
            LoanApplication("LN-1001", "MISSING_DOCUMENT", requested_documents=["PAN", "BANK_STATEMENT"], documents=["PAN"], relationship_manager="rm-1"),
            LoanApplication("LN-1002", "INCOME_VARIANCE", declared_income=1000000, verified_income=780000, relationship_manager="rm-2"),
            LoanApplication("LN-1003", "VERIFY_TRANSIENT_FAILURE", relationship_manager="rm-3"),
        ], [Account("AC-2001", "CUST-1", "IN-RBI-DEA", 15250.0, "2016-07-01"), Account("AC-2002", "CUST-2", "IN-RBI-DEA", 800.0, "2016-08-01")])
        (DATA / "audit.jsonl").unlink(missing_ok=True); print("Demo data initialized."); return
    if args.command == "run-loan": emit(loan_agent.apply_approved_deviation(args.application_id) if repo.get_loan(args.application_id).status == "AWAITING_APPROVAL" else loan_agent.run(args.application_id)); return
    if args.command == "run-dormancy": emit(dormancy_agent.run(date.fromisoformat(args.as_of))); return
    if args.command == "run-automation": emit(OperationsAutomationAgent(repo, audit, loan_agent, dormancy_agent).run_cycle(date.fromisoformat(args.as_of))); return
    if args.command == "decide":
        approval = repo.get_approval(args.approval_id)
        if approval.required_role != args.actor:
            raise SystemExit(f"Actor must be {approval.required_role}")
        approval.status, approval.decision_by, approval.decision_note = ("APPROVED" if args.approve else "REJECTED"), args.actor, args.note
        repo.save_approval(approval); audit.write(args.actor, "approval.decided", approval.entity_id, approval.status, {"approval_id": approval.approval_id}); emit(approval); return
    if args.command == "execute-transfers": emit(dormancy_agent.execute_approved_transfers()); return
    if args.command == "request-claim": emit(dormancy_agent.request_claim(args.account_id, args.claim_id, args.validated)); return
    if args.command == "execute-claims": emit(dormancy_agent.execute_approved_claims()); return
    if args.command == "list-approvals": emit(repo.list_approvals()); return
    if args.command == "list-events":
        path = DATA / "audit.jsonl"; print(path.read_text(encoding="utf-8") if path.exists() else "")


if __name__ == "__main__":
    main()
