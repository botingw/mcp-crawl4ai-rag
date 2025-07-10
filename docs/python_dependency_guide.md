# Python Dependency and Import Guide

This guide provides a clear overview of how to manage Python dependencies and handle imports within the `crawl4ai-mcp` project. Following these conventions is crucial for avoiding common import errors and ensuring a smooth development workflow.

## 1. Project Structure

This project uses a standard `src` layout, which helps maintain a clean separation between the source code and other project files (like tests, documentation, and scripts).

```
mcp-crawl4ai-rag/
├── src/
│   ├── __init__.py
│   ├── crawl4ai_mcp.py
│   ├── ingestion_engine.py
│   └── ... (other modules)
├── tests/
│   └── test_ingestion.py
├── pyproject.toml
└── README.md
```

The `pyproject.toml` file is the heart of the project's packaging and dependency management. It defines the package name, version, and all required external libraries.

## 2. External Dependencies

All external Python libraries required by this project are listed under the `[project]` section of the `pyproject.toml` file.

To install new packages, you should always use the `uv` package manager: source .venv/bin/activate && uv pip install {new-package} 


## 5. Recommended Development Setup

To ensure that all imports work as expected, you should set up your development environment following README, then when develop and test:

1.  **test code a Virtual Environment**:
    ```bash
    source .venv/bin/activate && uv run python ingest_git_docs_task
    ```

By following these guidelines, we can ensure the project's import structure remains robust and easy to maintain.
