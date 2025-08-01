# Copyright (c) 2025 Boting
#
# SPDX-License-Identifier: MIT

import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

import logging
# Suppress verbose logging from httpx and openai
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING) # httpx dependency

from src.ingestion_engine import ingest_repository
from src.stats_collector import stats_collector

async def main():
    """
    Builds a knowledge base for the LangGraph documentation by ingesting
    the code and docs from the official repository in two separate passes.
    """
    # Load environment variables from the .env file in the mcp-crawl4ai-rag submodule
    project_root = Path(__file__).resolve().parent
    dotenv_path = project_root / '.env'
    load_dotenv(dotenv_path, override=True)

    repo_url = "https://github.com/langchain-ai/langgraph.git"
    all_results = {}
    overall_success = True
    output_dir = Path("./reports")
    output_dir.mkdir(exist_ok=True)

    print(f"--- Starting Full Knowledge Base Build for: {repo_url} ---")

    # --- Pass 1: Code Ingestion ---
    print("\n--- [PASS 1/2] Ingesting Code for Knowledge Graph ---")
    stats_collector.reset()
    code_ingest_types = ["code"]
    code_include_folders = None
    print(f"Ingestion types: {code_ingest_types}")
    print(f"Included folders: {code_include_folders or 'All'}")
    
    code_result = await ingest_repository(repo_url, code_ingest_types, include_folders=code_include_folders)
    all_results['code_pass'] = code_result
    if not code_result.get("success"):
        overall_success = False
        print("--- Code Ingestion FAILED ---")
        print(f"Error details: {code_result.get('error')}")
    else:
        print("--- Code Ingestion Succeeded ---")
    
    # Save the report for the code pass
    code_report = stats_collector.get_report()
    code_report_filename = output_dir / "code_ingestion_report.json"
    with open(code_report_filename, 'w') as f:
        f.write(code_report)
    print(f"Code ingestion report saved to {code_report_filename}")


    # --- Pass 2: Documentation Ingestion ---
    print("\n--- [PASS 2/2] Ingesting Documentation for RAG ---")
    stats_collector.reset()
    docs_ingest_types = ["docs"]
    docs_include_folders = ["docs/docs"]
    print(f"Ingestion types: {docs_ingest_types}")
    print(f"Included folders: {docs_include_folders}")

    docs_result = await ingest_repository(repo_url, docs_ingest_types, include_folders=docs_include_folders)
    all_results['docs_pass'] = docs_result
    if not docs_result.get("success"):
        overall_success = False
        print("--- Documentation Ingestion FAILED ---")
        print(f"Error details: {docs_result.get('error')}")
    else:
        print("--- Documentation Ingestion Succeeded ---")

    # Save the report for the docs pass
    docs_report = stats_collector.get_report()
    docs_report_filename = output_dir / "docs_ingestion_report.json"
    with open(docs_report_filename, 'w') as f:
        f.write(docs_report)
    print(f"Docs ingestion report saved to {docs_report_filename}")


    # --- Final Summary ---
    print("\n--- Overall Knowledge Base Build Summary ---")
    import json
    print(json.dumps(all_results, indent=2))

    if overall_success:
        print("\n--- Knowledge Base built successfully. ---")
    else:
        print("\n--- Knowledge Base build FAILED. See errors above. ---")
        sys.exit(1)



if __name__ == "__main__":
    # Ensure you have the necessary environment variables set in .env:
    # SUPABASE_URL, SUPABASE_SERVICE_KEY, OPENAI_API_KEY
    asyncio.run(main())