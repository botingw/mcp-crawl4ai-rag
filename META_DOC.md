<!--
Copyright (c) 2025 Boting Wang

SPDX-License-Identifier: MIT
-->

# META DOC: The Developer's Guide to the Crawl4AI RAG & KG Server

This document is the single source of truth for the `mcp-crawl4ai-rag` server.
It is designed for developers and AI agents who need to understand, modify,
and extend its functionality.

## 1️⃣ Overview

The `mcp-crawl4ai-rag` repository is a standalone server that provides powerful
data ingestion, Retrieval-Augmented Generation (RAG), and Knowledge Graph (KG)
capabilities. Its primary function is to process unstructured and structured
data (from websites and code repositories) and transform it into queryable
knowledge for AI systems.

### Key features

*   **Dual Ingestion Pipelines:** Contains two parallel pipelines: one for
    ingesting documentation into a Supabase vector database for RAG, and
    another for parsing Python code into a Neo4j graph database for structural
    analysis.
*   **Modular & Reusable Engine:** Core logic is decoupled into a central
    `ingestion_engine.py`, making it testable, reusable, and independent of the
    server's tool-based API.
*   **Configurable Behavior:** Operation is heavily controlled by environment
    variables (`.env` file), allowing developers to enable/disable major
    features like the KG, agentic RAG, and embedding strategies.
*   **Robust Throttling & Statistics:** Includes a built-in token bucket rate
    limiter to proactively manage API calls and a `StatsCollector` to produce
    detailed JSON reports on token usage and performance.

### Table of contents

*   [1️⃣ Overview](#1️⃣-overview)
*   [2️⃣ Quick Start](#2️⃣-quick-start)
*   [3️⃣ System Architecture](#3️⃣-system-architecture)
*   [4️⃣ Key Modules & Data Flows](#4️⃣-key-modules--data-flows)
*   [5️⃣ Build & Run](#5️⃣-build--run)
*   [6️⃣ Deployment Pipeline](#6️⃣-deployment-pipeline)
*   [7️⃣ Operational Playbook](#7️⃣-operational-playbook)
*   [8️⃣ Contribution Guide](#8️⃣-contribution-guide)
*   [9️⃣ ADR Index](#9️⃣-adr-index)
*   [Changelog](#changelog)

## 2️⃣ Quick start

To work on this server, navigate into its directory and set up the environment.

```bash
# Navigate into the submodule directory
cd mcp-crawl4ai-rag

# Create and populate your environment file
cp .env.example .env
# ==> EDIT .env with your API keys (OPENAI_API_KEY, SUPABASE_URL, etc.) <==

# virtual env setup
uv venv
source .venv/bin/activate
uv pip install -e .
crawl4ai-setup

# Install dependencies using uv (or pip)
uv pip install -r requirements.txt

# Run the primary test script to verify functionality
uv run python test_build_langgraph_docs_knowledge.py

# To run the server continuously
bash start_mcp_server.sh
```

### Status badges

![Docker Build](https://img.shields.io/badge/Docker-Supported-blue)
![CI Pipeline](https://img.shields.io/badge/CI-Not%20Yet%20Implemented-lightgrey)

## 3️⃣ System architecture

The server's architecture is designed around a central orchestration engine
that delegates tasks to specialized modules for processing and storage.

```mermaid
graph TD
    subgraph "API & Tool Layer"
        A[crawl4ai_mcp.py]
    end

    subgraph "Core Logic"
        B[src/ingestion_engine.py]
    end

    subgraph "Utility Modules"
        C[src/repository_utils.py]
        D[src/utils_botingw.py]
    end

    subgraph "Processing Pipelines"
        E[knowledge_graphs/parse_repo_into_neo4j.py]
        F[RAG Pipeline]
    end

    subgraph "External Services"
        G[Supabase (Vector DB)]
        H[Neo4j (Graph DB)]
        I[OpenAI API (Embeddings/Summaries)]
    end

    A -- "Calls" --> B
    B -- "Uses" --> C
    B -- "Uses" --> D
    B -- "Invokes" --> E
    B -- "Invokes" --> F

    C -- "Clones/Reads Files" --> Git
    D -- "Chunks/Embeds" --> I
    E -- "Parses & Writes" --> H
    F -- "Stores" --> G
```

### Component walk-through

*   **`crawl4ai_mcp_botingw.py` (API & Tool Layer):** Exposes the server's functionality
    as tools for an external agent (like Gemini). This is a thin wrapper that
    calls the ingestion engine.
*   **`ingestion_engine.py` (Core Logic):** The orchestrator. It manages the
    end-to-end process of ingesting a repository, deciding which pipelines
    (KG or RAG) to run based on configuration.
*   **`repository_utils.py` (Utility):** Handles low-level, reusable git and
    filesystem operations, like cloning a repository and discovering files.
*   **`utils_botingw.py` (Utility):** Contains data processing helpers, such as
    the `StatsCollector`, token bucket rate limiter, and functions for
    chunking and embedding documents.
*   **`parse_repo_into_neo4j_botingw.py` (KG Pipeline):** Responsible for taking Python
    files, parsing their Abstract Syntax Trees (ASTs), and writing the code
    structure (classes, methods, etc.) to the Neo4j database.
*   **RAG Pipeline:** A conceptual pipeline within the engine that uses helpers
    from `utils_botingw.py` to process documentation, create embeddings via the
    OpenAI API, and store the results in Supabase.

## 4️⃣ Key modules & data flows

This table details the core files and their roles within the server.

| File/Folder | Responsibilities | Key Contracts & Data | Testing Strategy |
| :--- | :--- | :--- | :--- |
| **`src/ingestion_engine.py`** | Orchestrates the entire ingestion workflow from cloning to reporting. | `ingest_repository()` is the main entry point. Returns a JSON summary. | `test_build_langgraph_docs_knowledge.py` |
| **`src/crawl4ai_mcp_botingw.py`** | Defines the public-facing tools for AI agents. | `ingest_github_repository()` tool. | Tested via agent interaction. |
| **`src/repository_utils.py`** | Handles all `git` and file system interactions. | `clone_repository()`, `get_repository_files()` | Unit tests (future). |
| **`src/utils_botingw.py`** | Provides core data processing utilities. | `StatsCollector`, `TokenBucketRateLimiter`, `smart_chunk_markdown`. | Tested implicitly via the main test script. |
| **`knowledge_graphs/`** | Contains the logic for parsing Python code and interacting with Neo4j. | `DirectNeo4jExtractor` class. | Tested implicitly. |
| **`test_build_langgraph_docs_knowledge.py`** | The primary script for end-to-end testing of the ingestion engine. | N/A | Run directly: `python test_...` |

## 5️⃣ Build & run

### Environment variables

This server will not function without a correctly configured `.env` file.

```bash
# Credentials (Required)
OPENAI_API_KEY=...
SUPABASE_URL=https://...
SUPABASE_SERVICE_KEY=...
NEO4J_URI=neo4j+s://...
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=...

# Core Feature Flags (Boolean)
USE_KNOWLEDGE_GRAPH=true
USE_AGENTIC_RAG=true
USE_HYBRID_SEARCH=true
USE_RERANKING=true
USE_CONTEXTUAL_EMBEDDINGS=true
```

### Key commands

*   **Install:** `uv pip install -r requirements.txt`
*   **Run main test:** `uv python test_build_langgraph_docs_knowledge.py`
*   **Start server:** `bash start_mcp_server.sh`
*   **Stop server:** Find the process ID (`ps aux | grep mcp_server`) and `kill <PID>`.

## 6️⃣ Deployment pipeline

This server is designed to be deployed as a standalone microservice.

*   **Containerization:** A `Dockerfile` is provided for building a container
    image of the server.
*   **Deployment:** The image can be deployed to any container orchestration
    platform (e.g., Kubernetes, AWS ECS, Google Cloud Run).
*   **CI/CD:** A pipeline should be configured to:
    1.  Build the Docker image on push to `main`.
    2.  Run unit and integration tests against the image.
    3.  Push the image to a container registry (e.g., Docker Hub, GCR).
    4.  Trigger a deployment in the target environment.

## 7️⃣ Operational playbook

### Logging & diagnostics

*   **Server Logs:** `mcp_server.log` (stdout) and `mcp_server.err` (stderr).
*   **Ingestion Report:** The most critical diagnostic tool is the JSON report
    generated by the `StatsCollector` (`langgraph_doc_rag.json`). It provides a
    granular breakdown of every API call, token counts, and errors.

### Runbooks

*   **Problem: Ingestion fails.**
    *   **Diagnose:** Check `mcp_server.err` for the Python traceback. Then,
        examine the `langgraph_doc_rag.json` report to see which file or step
        failed. The error will be logged there.
    *   **Mitigate:** Common causes are invalid API keys, network issues, or a
        malformed file in the target repository that the parser cannot handle.

*   **Problem: High token usage / API costs.**
    *   **Diagnose:** This is a known challenge. The primary tool is the
        `langgraph_doc_rag.json` report. Compare
        `total_tokens_from_raw_docs` to `total_billed_tokens`. The per-chunk
        and per-call stats will reveal where token amplification occurs (e.g.,
        summarization prompts, contextual embedding overhead).
    *   **Mitigate:** See `doc_crawl4ai/task_2_token_usage_analysis_plan.md`.
        Consider disabling `USE_CONTEXTUAL_EMBEDDINGS` or refining the prompts
        in `src/utils_botingw.py`.

*   **Problem: OpenAI Rate Limit Errors.**
    *   **Diagnose:** The server will log `openai.RateLimitError`.
    *   **Mitigate:** The `TokenBucketRateLimiter` in `src/utils_botingw.py`
        should prevent most of these. If they still occur, the bucket capacity
        (`TPM_LIMIT`) may be set higher than your actual OpenAI tier limit.
        Verify your limits and adjust the constant in the code.

## 8️⃣ Contribution guide

not provided yet

## 9️⃣ ADR index

| ADR ID | Title | Status |
| :--- | :--- | :--- |
| ADR-002 | Decouple Ingestion Logic into a Standalone Engine | Accepted |
| ADR-003 | Implement Token Bucket for Proactive Rate Limiting | Accepted |

## Changelog

See `CHANGELOG.md` (to be created) for a detailed history of changes.
