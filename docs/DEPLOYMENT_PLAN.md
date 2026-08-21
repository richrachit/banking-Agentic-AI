# Deployment Plan

## 1. Purpose

This plan describes how to deploy Banking Operations AI safely from the current local reference implementation through controlled non-production environments and, after the required engineering and governance work, into production.

The repository is deployable today only as a local demonstration. It must not be connected to real customers, banking systems, identity providers, credit bureaus, KYC providers, payment rails, or regulatory processes until the production-readiness gates in this plan are complete.

## 2. Current deployment baseline

The current application consists of:

- a standard-library Python browser server on port 8000;
- a FastAPI application served by Uvicorn on port 8001;
- command-line and scheduled workflow scripts;
- local JSON, JSON Lines, SQLite, filesystem upload, and model-artifact storage;
- optional PostgreSQL 16 schema inspection through Docker Compose;
- optional local scikit-learn and PyTorch/Transformers runtimes.

The included PostgreSQL container does not replace the application's local persistence. A PostgreSQL repository and controlled migration mechanism must be implemented before a production deployment.

## 3. Deployment principles

Every deployment should follow these principles:

1. Separate development, test, staging, and production accounts, networks, data, keys, and credentials.
2. Promote the same immutable application artifact between environments.
3. Keep secrets outside source code and container images.
4. Apply database changes before application traffic only when backward compatible.
5. Default risky integrations and AI components to disabled until their approvals are recorded.
6. Preserve maker-checker controls and segregation of duties during deployment and operation.
7. Make every external operation idempotent, auditable, retryable, and reconcilable.
8. Use synthetic data outside approved production processing boundaries.
9. Support rapid application, configuration, policy, provider, and model rollback.
10. Block production promotion when security, compliance, model-risk, or operational evidence is incomplete.

## 4. Target production architecture

```text
Users / approved API clients
             |
     WAF / API gateway / TLS
             |
       Enterprise IdP
        SSO + MFA + RBAC
             |
   +---------+----------+
   |                    |
Web application      FastAPI service
   |                    |
   +------ private service network ------+
                         |
          Workflow/application services
                         |
       +-----------------+------------------+
       |                 |                  |
 PostgreSQL HA      Object storage      Message broker
 + migrations       + malware scan      + outbox/workers
 + read controls     + encryption        + retries/DLQ
       |                 |                  |
       +-----------------+------------------+
                         |
       Approved banking/provider adapters
  LOS / core / bureau / KYC / DMS / notifications
                         |
    Central logs, metrics, traces, SIEM and alerts
```

The exact cloud or on-premises products should be selected by the bank's platform and security architecture teams. The application should depend on capability contracts rather than a specific vendor.

## 5. Environment strategy

| Environment | Data | Purpose | Access |
| --- | --- | --- | --- |
| Local development | Synthetic only | Feature development and unit tests | Developer workstation |
| CI | Generated ephemeral data | Automated checks and artifact creation | CI service identities |
| Integration | Synthetic/provider sandbox | Adapter, migration, and contract testing | Engineering and QA |
| UAT | Masked or approved synthetic data | Business workflow and role validation | Named business testers |
| Pre-production | Production-like synthetic data | Performance, security, recovery, and release rehearsal | Restricted operations teams |
| Production | Approved live data | Controlled banking workload | Least-privilege operational access |

No production database, secret, model registry, object bucket, or provider credential should be shared with a lower environment.

## 6. Delivery phases

### Phase 0: Local demonstration

Goal: run and validate the existing reference application without real data.

Actions:

- create a Python virtual environment;
- install the required dependency groups;
- seed only fictional demo fixtures;
- run all automated tests;
- start the browser app and API locally;
- confirm `/api/v1/health`, `/docs`, authentication, role boundaries, and core workflows.

Exit criteria:

- dependency validation succeeds;
- all automated tests pass;
- no real customer information or production credentials are present;
- browser and API smoke tests pass.

### Phase 1: Deployment foundation

Goal: make the application buildable and repeatably deployable.

Required work:

- create production-grade container images for the web, API, and worker processes;
- pin and lock direct and transitive dependencies;
- generate an SBOM and provenance attestation;
- add dependency, secret, static-analysis, container, and license scanning;
- run processes as non-root with a read-only base filesystem;
- expose health, readiness, and graceful-shutdown behavior;
- externalize configuration and secrets;
- create infrastructure-as-code for networks, compute, databases, storage, queues, IAM, logging, and monitoring;
- define resource limits, autoscaling rules, timeouts, and availability targets.

Exit criteria:

- a signed immutable artifact is produced by CI;
- the same artifact can be promoted through integration and UAT;
- critical/high vulnerabilities have an approved disposition;
- recovery and rollback procedures have been rehearsed.

### Phase 2: Persistence and identity modernization

Goal: replace unsafe local runtime components.

Required work:

- implement transactional PostgreSQL repositories;
- introduce versioned database migrations rather than one-time schema initialization;
- add optimistic concurrency, idempotency keys, and transaction/outbox processing;
- move uploads to encrypted object storage with malware and content scanning;
- move audit evidence to immutable, retention-controlled storage;
- integrate the enterprise identity provider with SSO, MFA, short-lived tokens, revocation, and service authorization;
- remove static demo users, in-memory tokens, local signup, and administrator approval bypass;
- implement row/entity authorization in both service and persistence layers;
- configure managed secrets and key rotation.

Exit criteria:

- no authoritative production state depends on JSON, SQLite, local files, or process memory;
- backup/restore, point-in-time recovery, and migration rollback are tested;
- penetration testing and access-control testing pass;
- segregation-of-duties approval is recorded.

### Phase 3: Banking integrations

Goal: connect approved external systems through controlled adapters.

Integration order:

1. Read-only customer/loan/account reference data.
2. Document-management and notification services.
3. Consent, credit-bureau, KYC, fraud, and sanctions providers.
4. Approval/workflow platform.
5. Core/ledger posting, filing, claims, and payment boundaries.

Each adapter must provide:

- authenticated and encrypted transport;
- explicit timeouts and bounded retries;
- idempotency and duplicate protection;
- normalized error and unavailable states;
- circuit breaking and dead-letter handling;
- correlation IDs and audit evidence;
- reconciliation against the system of record;
- provider sandbox and contract tests;
- a tested manual fallback.

Exit criteria:

- business owners approve provider behavior and exception handling;
- reconciliation tests show no silent loss or duplicate action;
- failure-mode and disaster-recovery tests pass;
- legal, privacy, security, and compliance approvals are complete.

### Phase 4: AI and model productionization

Goal: deploy only independently approved advisory models.

Required work:

- establish governed training data, lineage, retention, and privacy controls;
- validate representativeness, bias, performance, stability, and explainability;
- use signed immutable model artifacts in an approved registry;
- separate training and inference permissions;
- pin serving dependencies and isolate artifact loading;
- capture model, feature, policy, provider, and prompt versions with every result;
- implement champion/challenger, shadow, canary, kill-switch, and rollback controls;
- monitor drift, data quality, latency, failures, overrides, and outcome disparities;
- preserve human authority for credit, KYC, compliance, and money movement.

Synthetic demo metrics and the bundled document model are not production-validation evidence.

Exit criteria:

- independent model-risk approval is recorded;
- the model card, validation report, monitoring thresholds, and rollback plan are approved;
- shadow evaluation succeeds before any user-facing advisory output;
- automatic high-risk decisions remain technically prohibited.

### Phase 5: Controlled production rollout

Goal: introduce production traffic with limited blast radius.

Recommended sequence:

1. Deploy with all external writes and optional AI components disabled.
2. Run database migrations and deployment verification.
3. Enable read-only workflows for internal pilot users.
4. Run shadow processing and compare results with existing operations.
5. Enable one low-risk workflow for a small approved cohort.
6. Expand through canary stages such as 5%, 25%, 50%, and 100% after review gates.
7. Enable additional integrations individually, never as one large cutover.
8. Maintain enhanced monitoring and an operations command center during stabilization.

Production release requires sign-off from Engineering, QA, Platform Operations, Information Security, Data/Model Risk, Legal/Privacy, Compliance, and the relevant business owner.

## 7. CI/CD pipeline

The existing GitHub workflow runs Python checks and should be expanded into the following gated pipeline:

```text
Pull request
  -> formatting and linting
  -> unit/integration/authorization tests
  -> type and static-security analysis
  -> dependency, license and secret scans
  -> build immutable containers
  -> container scan + SBOM + signing
  -> ephemeral migration and contract tests
  -> publish artifact
  -> deploy integration automatically
  -> integration/security/performance tests
  -> deploy UAT with approval
  -> deploy pre-production with approval
  -> release rehearsal and recovery checks
  -> production canary with dual approval
  -> automated smoke checks and monitored promotion
```

Production must deploy from a protected branch/tag using a CI service identity. Direct workstation deployment and direct modification of production configuration should be prohibited.

## 8. Database deployment

Use a migration tool and maintain forward-compatible, reviewed migrations. The recommended release sequence is expand, migrate, switch, and contract:

1. Back up and confirm restore readiness.
2. Apply backward-compatible additive changes.
3. Deploy application code that supports both old and new shapes.
4. Backfill data through observable, restartable jobs.
5. Verify counts, constraints, hashes, and reconciliation reports.
6. Switch reads/writes using controlled configuration.
7. Remove old fields only in a later release.

Destructive migrations must have explicit data-owner approval, a tested recovery plan, and a maintenance strategy. Database credentials must be short-lived or rotated and scoped separately for migration and application access.

## 9. Configuration and secrets

Maintain versioned, environment-specific non-secret configuration and store secrets in an approved secrets manager.

Configuration requiring formal change control includes:

- credit thresholds and adverse-action behavior;
- dormancy jurisdictions, dates, and filing rules;
- agent/model availability;
- model and provider versions;
- CORS and trusted client configuration;
- timeout, retry, queue, and rate-limit policies;
- retention and deletion schedules.

Never deploy the local demo password, HMAC key, static users, or Docker Compose database password to a shared or production environment.

## 10. Observability and operational readiness

Implement centralized structured logs, metrics, traces, dashboards, SIEM integration, and paging. Do not log passwords, tokens, PAN, Aadhaar, documents, full customer payloads, or unredacted model inputs.

Minimum service monitoring:

- availability, latency, throughput, saturation, and error rate;
- authentication and authorization failures;
- database health, connection pool, replication, and migration status;
- queue depth, retry rate, dead letters, and stuck workflows;
- provider latency, availability, and circuit state;
- object-scan failures and upload rejection rate;
- audit-pipeline delivery and reconciliation breaks;
- approval aging and workflow service-level objectives;
- model drift, data quality, inference failures, overrides, and kill-switch state.

Runbooks must cover service degradation, provider outage, data reconciliation, credential compromise, model disablement, database recovery, queue replay, and customer-impact communication.

## 11. Release validation checklist

Before every production release, confirm:

- approved change ticket and release scope;
- signed artifact, SBOM, and scan evidence;
- automated and UAT test results;
- backward compatibility of API, database, events, and provider contracts;
- migration backup and restore readiness;
- secrets and certificates are valid and rotation-safe;
- configuration and policy versions are approved;
- model approval is valid for the deployed artifact;
- dashboards, alerts, on-call coverage, and runbooks are ready;
- canary metrics and rollback thresholds are defined;
- no demo credentials, fixtures, or synthetic artifacts are enabled;
- business, compliance, security, and operational sign-offs are recorded.

## 12. Rollback plan

Rollback must be possible independently for application code, configuration, policy, provider adapters, and models.

Rollback triggers include:

- elevated error or latency rate;
- authorization or data-exposure failure;
- incorrect workflow transitions or duplicate external actions;
- database integrity or reconciliation failure;
- provider instability;
- model drift, invalid output, or unexplained override spike;
- inability to produce required audit evidence.

Rollback procedure:

1. Stop traffic promotion and disable affected integrations or agents.
2. Route traffic to the last known-good application artifact.
3. Preserve logs, events, and evidence for investigation.
4. Pause queue consumers when replay could duplicate an external action.
5. Reconcile partially completed workflows with authoritative systems.
6. Restore data only when forward correction is unsafe and restore approval is granted.
7. Validate health, permissions, audit delivery, and business totals.
8. Communicate status and complete incident review before redeployment.

Database rollback should normally use forward-compatible correction. Restoring an old database snapshot can lose valid transactions and therefore requires incident-command and data-owner authorization.

## 13. Ownership

| Area | Accountable owner |
| --- | --- |
| Application build and release | Engineering lead |
| Infrastructure and runtime | Platform/SRE lead |
| Tests and release evidence | QA lead |
| Identity, secrets, network, and vulnerability risk | Information Security |
| Data classification, retention, and consent | Privacy/Data Governance |
| Credit and workflow policy | Business and Credit Risk owners |
| Dormancy and regulatory rules | Compliance/Legal owners |
| Model validation and monitoring | Independent Model Risk Management |
| Production approval and incident command | Change authority/Operations |

No single technical administrator should be able to deploy code, change business policy, approve a model, and approve a banking decision without independent controls.

## 14. Indicative delivery sequence

The plan should be estimated after architecture and regulatory review. A reasonable sequence is:

| Stage | Indicative focus |
| --- | --- |
| 1 | Containerization, dependency locking, CI security gates, and infrastructure design |
| 2 | PostgreSQL repositories, migrations, identity integration, object storage, and audit pipeline |
| 3 | Integration adapters, queues/outbox, reconciliation, and operational dashboards |
| 4 | Security, performance, recovery, business, and compliance validation |
| 5 | Model validation and shadow deployment for separately approved AI capabilities |
| 6 | Internal pilot, production canary, staged workflow enablement, and stabilization |

The timeline depends primarily on enterprise integration access, data governance, regulatory approval, and production-control implementation—not on starting the current local Python processes.

## 15. Local demonstration runbook

For an isolated workstation using fictional data:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-api.txt -r requirements-training.txt
.\.venv\Scripts\python.exe -m banking_agents seed-demo
.\.venv\Scripts\python.exe scripts\seed_credit_bureau_demo.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Start the browser application:

```powershell
.\.venv\Scripts\python.exe -m banking_agents.web_app
```

Start the API in a separate terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn banking_agents.api_app:app --host 127.0.0.1 --port 8001
```

Verify `http://127.0.0.1:8000`, `http://127.0.0.1:8001/api/v1/health`, and `http://127.0.0.1:8001/docs`. This runbook is not a production deployment method.
