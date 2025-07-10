import asyncio
import os
from dotenv import load_dotenv
from pathlib import Path

# Ensure the script can find the 'src' module
import sys
sys.path.append(str(Path(__file__).resolve().parent))

from src.ingestion_engine import ingest_repository

async def main():
    """Main function to run the ingestion test."""
    # Load environment variables from the .env file in the submodule root
    project_root = Path(__file__).resolve().parent
    dotenv_path = project_root / '.env'
    load_dotenv(dotenv_path, override=True)

    # --- Configuration ---
    # You can change this URL to any public repository you want to test.
    # Using a smaller repository is recommended for faster testing.
    repo_url = "https://github.com/langchain-ai/langgraph.git"
    
    # We will only test the 'docs' ingestion for now to avoid Neo4j dependency.
    ingest_types = ["docs"]

    print(f"--- Starting Ingestion Test for: {repo_url} ---")
    print(f"Ingestion types: {ingest_types}")

    # --- Run Ingestion ---
    try:
        result = await ingest_repository(repo_url, ingest_types)
        
        print("\n--- Ingestion Result ---")
        import json
        print(json.dumps(result, indent=2))

        if result.get("success"):
            print("\n--- Test Passed: Ingestion completed successfully. ---")
        else:
            print("\n--- Test Failed: Ingestion reported an error. ---")
            print(f"Error details: {result.get('error')}")

    except Exception as e:
        print(f"\n--- Test Failed: An unexpected exception occurred. ---")
        print(f"Exception: {e}")

if __name__ == "__main__":
    # Ensure you have the necessary environment variables set in .env:
    # SUPABASE_URL, SUPABASE_SERVICE_KEY, OPENAI_API_KEY
    asyncio.run(main())
