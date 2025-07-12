import asyncio
import os
from dotenv import load_dotenv
from pathlib import Path
import sys
import logging
import argparse

# Ensure the script can find the 'src' module
sys.path.append(str(Path(__file__).resolve().parent))

# Suppress verbose logging from httpx and openai
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING) # httpx dependency

# print(f"sys.path in test_ingestion.py (before import): {sys.path}")

# from src.ingestion_engine import ingest_repository
from src.ingestion_engine import ingest_repository

async def run_test_no_filter(repo_url: str, ingest_types: list):
    print("\n--- Running Ingestion without folder filter ---")
    result_no_filter = await ingest_repository(repo_url, ingest_types)
    print("\n--- Ingestion Result (No Filter) ---")
    import json
    print(json.dumps(result_no_filter, indent=2))
    return result_no_filter

async def run_test_with_filter(repo_url: str, ingest_types: list, include_folders: list):
    print("\n--- Running Ingestion with folder filter ---")
    result_with_filter = await ingest_repository(repo_url, ingest_types, include_folders=include_folders)
    print("\n--- Ingestion Result (With Filter) ---")
    import json
    print(json.dumps(result_with_filter, indent=2))
    return result_with_filter

async def main():
    """Main function to run the ingestion tests."""
    parser = argparse.ArgumentParser(description="Run ingestion tests.")
    parser.add_argument("--run-no-filter-test", action="store_true", help="Run the test without folder filter.")
    parser.add_argument("--run-with-filter-test", action="store_true", help="Run the test with folder filter.")
    args = parser.parse_args()

    # Load environment variables from the .env file in the submodule root
    project_root = Path(__file__).resolve().parent
    dotenv_path = project_root / ".env"
    load_dotenv(dotenv_path, override=True)

    # --- Configuration ---
    repo_url = "https://github.com/Ekultek/BlueKeep.git"
    ingest_types = ["docs"]

    print(f"--- Starting Ingestion Tests for: {repo_url} ---")
    print(f"Ingestion types: {ingest_types}")

    if args.run_no_filter_test:
        result_no_filter = await run_test_no_filter(repo_url, ingest_types)
        if result_no_filter.get("success"):
            print("\n--- Test Passed: Ingestion without folder filter completed successfully. ---")
        else:
            print("\n--- Test Failed: Ingestion without folder filter reported an error. ---")
            print(f"Error details (No Filter): {result_no_filter.get("error")}")

    if args.run_with_filter_test:
        include_folders = ["research", "not-exist-folder"]
        result_with_filter = await run_test_with_filter(repo_url, ingest_types, include_folders)
        if result_with_filter.get("success"):
            print("\n--- Test Passed: Ingestion with folder filter completed successfully. ---")
        else:
            print("\n--- Test Failed: Ingestion with folder filter reported an error. ---")
            print(f"Error details (With Filter): {result_with_filter.get("error")}")

    if not args.run_no_filter_test and not args.run_with_filter_test:
        print("No test specified. Use --run-no-filter-test or --run-with-filter-test.")


if __name__ == "__main__":
    # Ensure you have the necessary environment variables set in .env:
    # SUPABASE_URL, SUPABASE_SERVICE_KEY, OPENAI_API_KEY
    asyncio.run(main())
