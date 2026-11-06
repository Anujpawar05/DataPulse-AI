# DataPulse AI — Project Status & Continuity File

> **Purpose:** This is the shared source of truth for the DataPulse AI project. Update it whenever a feature, function, phase, architecture decision, or task is added, changed, completed, or removed.
>
> **How to use:** Keep this file at the root of the `DataPulse-AI` repository as `PROJECT_STATUS.md`. At the start of a future ChatGPT session, upload this file or share the latest version so work can continue from the recorded state. Do not rely on chat memory as the project record.

---

## 1. Project overview

**Project name:** DataPulse AI — Intelligent Business Data Platform
**Resume title:** DataPulse AI – End-to-End Cloud Data Engineering & AI Analytics Platform

**Aim:** Build an end-to-end data platform for a fictional e-commerce company. It collects data from APIs, CSV files, and PostgreSQL; orchestrates ingestion and processing; stores data in a cloud warehouse; transforms and tests it; presents business dashboards; and provides an AI agent for natural-language business questions.

**Target outcome:**
- Automated data ingestion and orchestration.
- Centralized cloud data warehouse.
- Tested, analytics-ready data models.
- Power BI dashboards for business performance.
- AI-powered business Q&A grounded in warehouse data and business documentation.
- Monitoring for pipeline failures and data freshness.
- Reproducible deployment and clear GitHub documentation.

## 2. Agreed technology stack

| Area | Technology |
|---|---|
| Programming | Python, SQL |
| Data sources | REST APIs, CSV, PostgreSQL |
| Orchestration | Apache Airflow |
| Cloud warehouse | Google BigQuery |
| Transformation and testing | dbt |
| Dashboard | Power BI |
| AI | LLM, RAG, controlled text-to-SQL agent |
| Version control | GitHub |
| Packaging/deployment | Docker |

**Architecture note:** Use RAG for business definitions, metric documentation, and explanations. Use a controlled, read-only text-to-SQL layer for questions requiring live warehouse calculations. Validate generated SQL, restrict accessible datasets/tables, and apply query limits before execution.

## 3. Planned repository structure

```text
DataPulse-AI/
├── data/
│   ├── raw/
│   └── processed/
├── ingestion/
│   ├── api_ingestion.py
│   ├── csv_ingestion.py
│   └── postgres_ingestion.py
├── airflow/
│   └── dags/
├── warehouse/
│   └── bigquery/
├── dbt_project/
│   ├── models/
│   │   ├── staging/
│   │   └── marts/
│   └── tests/
├── dashboard/
├── ai_agent/
│   ├── rag/
│   ├── sql_agent/
│   └── main.py
├── monitoring/
├── docker-compose.yml
├── README.md
└── PROJECT_STATUS.md
```

This is the planned structure, not confirmation that these folders/files already exist. Adjust it as implementation decisions are made.

## 4. Development order and phases

| Phase | Scope | Completion evidence | Status |
|---|---|---|---|
| 1. Data foundation | Design PostgreSQL schema; create customers, products, orders, payments, and sales data; generate realistic sample records; prepare CSV/API inputs | Database schema, sample data, source files, and basic validation checks work | Done |
| 2. Python ingestion | Build API, CSV, and PostgreSQL extraction; clean, validate, and load data | Each ingestion function runs successfully and handles errors | In progress |
| 3. Airflow orchestration | Create DAGs, schedules, dependencies, retries, and logs | Pipeline runs on schedule and can be monitored in Airflow | Not started |
| 4. BigQuery warehouse | Create project/dataset structure and load raw data | Data lands in BigQuery with expected schemas and row counts | Not started |
| 5. dbt transformations | Build staging and mart models; add schema and business-rule tests | `dbt run` and `dbt test` pass; documented business models exist | Not started |
| 6. Power BI dashboard | Connect to curated warehouse models; build revenue, profit, customer, product, and sales views | Dashboard visuals reconcile with warehouse queries | Not started |
| 7. AI agent | Add business-document RAG and safe, read-only text-to-SQL analytics | Representative business questions return grounded, verifiable answers | Not started |
| 8. Packaging and deployment | Dockerize services; document setup and deployment; maintain GitHub repository | A fresh setup can be reproduced using project instructions | Not started |
| 9. Monitoring and hardening | Add pipeline failure alerts, freshness checks, logging, and operational safeguards | Failures and stale data are detectable and documented | Not started |

**Implementation rule:** Complete and verify each phase's acceptance evidence before treating that phase as complete. A folder or code file existing is not, by itself, proof that a feature works.

## 5. Initial business data model

The initial dataset scope is five subject areas:

- **Customers:** customer ID, name, location, registration date.
- **Products:** product ID, category, selling price, cost.
- **Orders:** order ID, customer ID, order date, order status.
- **Payments:** payment ID, order ID, payment method, amount, payment status.
- **Sales:** order/product-level quantity, revenue, profit, and discount.

The exact columns, relationships, constraints, and grain must be finalized during Phase 1. Avoid duplicating facts across tables without defining the intended data grain.

## 6. Current project status

**Overall status:** Implementation in progress.
**Current phase:** Phase 2 — Python ingestion.
**Last updated:** 2026-11-03

**Completed:** Phase 1 — Data foundation. PostgreSQL database `datapulse_db` contains the five approved tables and verified sample data:
- customers: 1,000 rows
- products: 100 rows
- orders: 5,000 rows
- sales: 5,000 rows
- payments: 5,000 rows

User confirmed final validation: invalid payment references = 0 and payment-to-sales amount mismatches = 0. Earlier sales checks also returned zero invalid order and product references; orders had zero invalid customer references.

**In progress:** Phase 2 — Python ingestion. No ingestion function is marked complete yet.

**Immediate next task:** Inspect the existing `DataPulse-AI` project directory and Python environment before creating or changing files. Confirm the current repository structure, Python version, and installed dependencies. Do not overwrite existing project files or introduce a different architecture without first reviewing it.

### Progress snapshot

| Phase | Status | Notes |
|---|---|---|
| 1. Data foundation | Done | PostgreSQL schema and all five tables populated; final checks user-confirmed |
| 2. Python ingestion | In progress | First task: inspect repository and Python environment; then implement and test ingestion in the agreed order |
| 3. Airflow | Not started | Depends on working ingestion functions |
| 4. BigQuery | Not started | Target warehouse selected |
| 5. dbt | Not started | Depends on warehouse tables |
| 6. Power BI | Not started | Depends on curated models |
| 7. AI agent | Not started | Depends on governed warehouse access |
| 8. Docker/GitHub | Not started | Build and document progressively |
| 9. Monitoring | Not started | Add progressively; complete hardening later |

## 7. Function and task change log

Record meaningful changes here. Keep entries newest first.

| 2026-11-03 | Phase 2 | Started Python ingestion phase; first task is repository/environment inspection before implementation | In progress | No files or architecture changed yet |
| 2026-11-03 | Phase 1 | User confirmed final validation: target counts met across all five tables; invalid payment references = 0; mismatched payments = 0 | Done | Phase 1 – Data Foundation closed; Phase 2 may begin |
| 2026-11-03 | Phase 1 | User confirmed final validation: target counts met across all five tables; invalid payment references = 0; mismatched payments = 0 | Done | Phase 1 – Data Foundation marked complete; proceed to the next phase in the agreed sequence |
| 2026-11-03 | Phase 1 | Payments verification returned total_payments=5,000, orders_with_payments=5,000, total_payment_amount=475,854,154.52 | Done | Payment volume and order coverage confirmed; final FK and amount reconciliation checks still required |
| 2026-11-03 | Phase 1 | Verified sales: 5,000 lines, 5,000 orders with sales, 100 products sold, 20,000 units; invalid order references=0 and invalid product references=0 | Done | Sales stage accepted; proceed to payments |
| 2026-11-03 | Phase 1 | User confirmed `total_orders = 5000`; orders stage accepted after prior FK validation returned zero invalid customer references | Done | Proceed to sales generation |
| 2026-11-03 | Phase 1 | User shared orders FK validation result: `invalid_customer_references = 0` | Partial verification | Referential integrity is clean for existing orders; need total_orders count to confirm target 5,000 |
| 2026-11-03 | Phase 1 | Corrected orders query after SQLSTATE 42703: `r` was referenced in CASE but not projected by the source query | In progress | New generated CTE explicitly selects `random() AS r`; verify orders count before executing corrected INSERT |
| 2026-11-03 | Phase 1 | Orders INSERT rejected by FK `orders_customer_id_fkey`: generated customer_id 368 does not exist; previous SQL incorrectly assumed IDs 1–1000 | Blocked | Query actual customer IDs and orders count; revised INSERT must select IDs from customers table |
| 2026-11-03 | Phase 1 | Inserted and verified 100 products; query returned total_products=100, unique_products=100, categories=8, price range 557.33–49940.53 | Done | Product stage accepted; proceed to orders |
| 2026-11-03 | Phase 1 | Inserted and verified 1,000 customers; query returned total_customers=1000, unique_emails=1000, cities=16 | Done | Customer stage accepted; proceed to product generation |
| 2026-11-03 | Phase 1 | Fresh Query Tool screenshot reconfirms customers=0, products=0, orders=0, payments=0, sales=0 | Done | Safe baseline established; bulk seed script will not be retried; staged loading begins with customers |
| 2026-11-03 | Phase 1 | User closed original seed-script Query Tool tab; noted that closing the session rolls back uncommitted work and the first error cannot be recovered from that tab | In progress | Recheck all five counts in a fresh `datapulse_db` Query Tool before controlled staged loading |
| 2026-11-03 | Phase 1 | Clarified pgAdmin Query Tool tabs may use separate sessions; `ROLLBACK` must be executed in the same tab/session that has the aborted transaction | In progress | User uses a new Query Tool tab for each code; inspect first error in seed-script tab |
| 2026-11-03 | Phase 1 | User reported SQLSTATE 25P02 during seed execution; explained it is a secondary aborted-transaction error and instructed separate `ROLLBACK;` followed by locating the first error | Blocked | Do not rerun until root cause is identified |
| 2026-11-03 | Phase 1 | Diagnostic COUNT query confirmed all five tables contain 0 rows; code review found missing semicolon after `END` in seed-script DO block; prepared v3 | In progress | Safe to retry because all target tables are empty; v3 not yet executed |
| 2026-11-03 | Phase 1 | Latest verification screenshot shows NULL revenue/cost/profit aggregates; likely empty sales table despite earlier 5,000-row insert | In progress | Requested standalone COUNT(*) query for all five tables; no destructive action or blind reseed |
| 2026-11-03 | Phase 1 | User shared pgAdmin success message: `INSERT 0 5000`; query completed successfully in 3.077 seconds | In progress | Confirms one 5,000-row insert; exact statement and remaining table counts not yet established; verification required |
| 2026-11-03 | Phase 1 | Reviewed latest screenshot: PostgreSQL now reports end-of-input at `CASE`; complete v2 file includes subsequent `WHEN` clauses, `END`, and remaining inserts | Blocked | Confirm full script is present in pgAdmin editor and entire script is submitted; no data completion claimed |
| Date | Phase | Change / function | Status | Verification / notes |
|---|---|---|---|---|
| 2026-11-03 | Phase 1 | Executed PostgreSQL schema in `datapulse_db` and verified `customers`, `products`, `orders`, `payments`, and `sales` in pgAdmin | Done | User confirmed all five tables are visible under `public → Tables` |
| 2026-11-03 | Phase 1 | Reviewed user's pgAdmin screenshots: seed script reported syntax error near order-date expression; verification's revenue/profit query returned NULL, indicating no sales rows | Blocked | Corrected timestamp expression in v2 seed script; must confirm table counts before rerunning |
| 2026-11-03 | Phase 1 | Prepared sample-data generator for 1,000 customers, 100 products, 5,000 orders, one initial payment per order, and 1–3 sales lines per order; prepared verification queries | In progress | Scripts created; not yet executed in the user's PostgreSQL database |
| 2026-11-03 | Phase 1 | User approved the five-table schema; prepared PostgreSQL DDL for customers, products, orders, payments, and sales | In progress | SQL artifact created; not yet executed against PostgreSQL |
| 2026-11-03 | Planning | Created initial project blueprint and continuity-file plan | Done | Initial scope and sequence captured |

## 8. Decisions and open questions

### Confirmed decisions
- Fictional e-commerce company is the business use case.
- Initial sources: REST APIs, CSV, and PostgreSQL.
- BigQuery is the selected warehouse.
- dbt is the transformation/testing layer.
- Power BI is the dashboard tool.
- AI uses RAG for business knowledge and controlled text-to-SQL for warehouse metrics.
- Build the data foundation and reliable pipeline before implementing the AI agent.

### To decide during implementation
- Exact PostgreSQL schema, column types, keys, constraints, and table grain.
- Which public/demo API or locally hosted mock API will supply source data.
- Dataset size and date range for realistic test scenarios.
- BigQuery project, dataset naming, region, credentials, and cost controls.
- Airflow deployment approach and local development setup.
- LLM/provider, embedding model, vector store, and AI application framework.
- Authentication, authorization, and deployment target.

## 9. Update protocol (for every future work session)

Whenever a function, feature, folder, dependency, or architecture decision is added, modified, or removed:

1. Update the relevant phase status and progress snapshot.
2. Record the change in the log with date and verification result.
3. Update the repository structure if files/folders changed.
4. Record important decisions, unresolved issues, and the exact next task.
5. Mark a feature **Done** only after it has been run/tested; note the command or evidence.
6. If something is removed or replaced, record what changed and why. Do not silently erase important history.

### Status labels
- **Not started** — no implementation yet.
- **In progress** — currently being built.
- **Blocked** — cannot proceed; blocker must be stated.
- **Done** — implemented and verified.
- **Deferred** — intentionally postponed, with reason.

**Continuity rule:** This file is the project handoff record. Before continuing work in a new session, read the latest version and use it to establish completed work, current blockers, and the next task. Update and return the revised file after each meaningful implementation milestone.
