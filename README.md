# DataPulse AI
### Intelligent Business Data Platform

DataPulse AI is an end-to-end business data platform built around a fictional e-commerce use case. It brings together data ingestion, orchestration, cloud warehousing, transformation, analytics, and an AI-powered interface for asking business questions.

> **Project status:** The planned development phases and Phase 9 monitoring work are reported complete in the local development workspace. The repository's tracked files are being aligned with that completed implementation.

## What it does

- Ingests business data from PostgreSQL, CSV files, and REST APIs.
- Validates incoming records before downstream processing.
- Uses Apache Airflow to orchestrate ingestion tasks with retries and execution timeouts.
- Loads analytical data into Google BigQuery.
- Uses dbt staging, intermediate, and mart models to shape warehouse data.
- Provides a web interface and FastAPI backend for business analytics questions.
- Uses retrieval-augmented generation (RAG) for business context and controlled, validated Text-to-SQL for warehouse-backed answers.
- Includes provider fallback configuration for Gemini, Groq, and local Ollama.
- Adds application health checks, request observability, sanitized logging, and pipeline resilience tests.

## Architecture

```text
PostgreSQL ─┐
CSV files ──┼──> Python ingestion & validation ──> Apache Airflow
REST APIs ──┘                                      │
                                                  v
                                           Google BigQuery
                                                  │
                                                  v
                                             dbt models
                                      (staging / intermediate / marts)
                                                  │
                           ┌──────────────────────┴─────────────────────┐
                           v                                            v
                    Power BI analytics                         FastAPI AI backend
                                                                    │
                                                   RAG + SQL validation/execution
                                                                    │
                                                                    v
                                                        Web-based AI interface
```

## Technology stack

| Layer | Technologies |
|---|---|
| Languages | Python, SQL, JavaScript, HTML, CSS |
| Data sources | PostgreSQL, CSV, DummyJSON REST API |
| Ingestion and validation | Python, pandas, psycopg, requests |
| Orchestration | Apache Airflow |
| Data warehouse | Google BigQuery |
| Transformation | dbt |
| Analytics | Power BI |
| AI application | FastAPI, RAG, controlled Text-to-SQL |
| LLM providers | Gemini, Groq, Ollama |
| SQL validation | SQLGlot |
| Containerization | Docker, Docker Compose |
| Testing | pytest |

## Repository layout

```text
DataPulse-AI/
├── ai_agent/
│   ├── backend/          # FastAPI, analytics, providers, RAG and SQL components
│   ├── frontend/         # Browser-based interface
│   └── knowledge/        # Business glossary and warehouse schema context
├── airflow/
│   ├── dags/             # Ingestion orchestration DAG
│   ├── Dockerfile
│   └── docker-compose.yaml
├── data/
│   └── sample/           # Sample input files
├── dbt/
│   ├── models/
│   │   ├── staging/
│   │   ├── intermediate/
│   │   └── marts/
│   └── dbt_project.yml
├── ingestion/
│   ├── api/
│   ├── bigquery/
│   ├── csv/
│   └── postgres/
├── tests/                # Automated tests
├── .env.example          # Environment variable template
├── requirements.txt
└── README.md
```

## Prerequisites

Install the tools required for the components you intend to run:

- Python 3.11+ (the development environment used for the reported test run was Python 3.13).
- PostgreSQL.
- Docker Desktop with Docker Compose, for containerized services.
- A Google Cloud project with BigQuery enabled and suitable credentials.
- A dbt installation and BigQuery adapter compatible with the dbt project configuration.
- An API key for at least one configured hosted LLM provider, or a local Ollama installation and model.

Power BI Desktop is required only for working with dashboard/report assets. A Power BI `.pbix` file is not included in the tracked repository snapshot.

## Configuration

1. Clone the repository:

   ```bash
   git clone https://github.com/Anujpawar05/DataPulse-AI.git
   cd DataPulse-AI
   ```

2. Create and activate a virtual environment:

   **Windows PowerShell**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   **macOS / Linux**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. Install Python dependencies:

   ```bash
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. Create your local environment file:

   **Windows PowerShell**
   ```powershell
   Copy-Item .env.example .env
   ```

   **macOS / Linux**
   ```bash
   cp .env.example .env
   ```

5. Edit `.env` with your own PostgreSQL credentials, AI provider API keys, and BigQuery settings. Never commit the real `.env` file or cloud service-account credentials.

The example environment file documents the expected variable names. Use credentials and project/dataset values belonging to your own environment; example values do not grant access to a cloud project.

## Running the AI backend

After configuring the environment and installing dependencies, start FastAPI from the repository root:

```bash
uvicorn ai_agent.backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Local endpoints:

- API root: http://127.0.0.1:8000/
- Health check: http://127.0.0.1:8000/health
- Interactive API docs: http://127.0.0.1:8000/docs

The analytics and ask routes depend on configured BigQuery access and AI provider settings.

## Running the ingestion pipeline

The repository includes an Airflow Docker Compose setup under `airflow/`. Review the Airflow configuration and create the required local `airflow/.env` file before starting it. The Compose configuration is intended for local development, not production deployment.

Typical workflow:

1. Configure Airflow environment variables and secrets locally.
2. Build the custom Airflow image from `airflow/Dockerfile`.
3. Initialize the Airflow metadata database using the Compose configuration.
4. Start the Airflow services.
5. Enable and trigger the DataPulse ingestion DAG from the Airflow UI.
6. Verify task outcomes and ingestion outputs before running downstream transformations.

Run Compose commands from `airflow/` and follow the Apache Airflow Docker Compose initialization guidance for the version configured in the project.

## dbt transformations

The `dbt/` directory contains staging, intermediate, and mart SQL models. Configure a local dbt profile for your own BigQuery project and dataset; profiles are deliberately excluded from version control.

From the dbt project directory:

```bash
dbt debug
dbt run
dbt test
```

A successful `dbt debug` confirms profile/warehouse connectivity; `dbt run` and `dbt test` execute transformations and declared data checks.

## AI question-answering design

The AI layer combines two complementary approaches:

- **RAG:** retrieves business glossary definitions and warehouse schema context to ground explanations in business terminology.
- **Controlled Text-to-SQL:** generates read-only analytical SQL for warehouse questions, validates the query before execution, and runs it against BigQuery.

The configured provider chain supports Gemini as the primary provider, Groq as a secondary provider, and Ollama as a local option. Configure each provider with credentials and model availability appropriate to your environment.

## Testing

Run the automated test suite from the repository root:

```bash
pytest
```

The Phase 9 completion report recorded **176 passing tests** in the local development workspace. This is reported local test evidence, not a GitHub Actions result for the repository's current remote commit.

## Security and operational notes

- Keep secrets, API keys, database passwords, service-account files, and local environment files out of Git.
- Use a least-privilege BigQuery identity and restrict accessible datasets.
- Apply query-cost limits and read-only permissions to the AI analytics layer.
- The Airflow Compose configuration is for local development; harden authentication, secrets, networking, persistence, and monitoring before production use.
- Do not expose the development API server directly to an untrusted network.

## Current limitations

- Cloud resources, credentials, dbt profiles, and deployment environments are not bundled in this repository.
- Dashboard publishing and live BigQuery/LLM behavior require configuration in the target environment.
- No production deployment or uptime/SLO claim is made by this README.

## License

No license file is currently included. Unless a license is added, the repository is not explicitly licensed for reuse or redistribution.
