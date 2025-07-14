

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

# Add the parent directory of 'mcp-crawl4ai-rag' to the Python path
# This is necessary for the import of 'ingest_repository' to work
# sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.ingestion_engine import ingest_repository
from src.stats_collector import stats_collector

async def main():
    """
    Builds a knowledge base for the LangGraph documentation by ingesting
    the docs/docs folder from the official repository.
    """
    # Load environment variables from the .env file in the mcp-crawl4ai-rag submodule
    project_root = Path(__file__).resolve().parent.parent / "mcp-crawl4ai-rag"
    dotenv_path = project_root / '.env'
    load_dotenv(dotenv_path, override=True)

    # --- Configuration ---
    repo_url = "https://github.com/langchain-ai/langgraph.git"
    ingest_types = ["docs"]
    include_folders = ["docs/docs/how-tos/http"]

    print(f"--- Starting Knowledge Base Build for: {repo_url} ---")
    print(f"Ingestion types: {ingest_types}")
    print(f"Included folders: {include_folders}")

    # --- Reset Stats Collector ---
    stats_collector.reset()

    # --- Run Ingestion ---
    result = await ingest_repository(repo_url, ingest_types, include_folders=include_folders)
    
    print("\n--- Knowledge Base Build Result ---")
    import json
    print(json.dumps(result, indent=2))

    if result.get("success"):
        print("\n--- Knowledge Base built successfully. ---")
    else:
        print("\n--- Knowledge Base build failed. ---")
        print(f"Error details: {result.get('error')}")

    # --- Print Stats Report ---
    print("\n--- Ingestion Statistics Report ---")
    print(stats_collector.get_report())

if __name__ == "__main__":
    # Ensure you have the necessary environment variables set in .env:
    # SUPABASE_URL, SUPABASE_SERVICE_KEY, OPENAI_API_KEY
    asyncio.run(main())

