


import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# This script is designed to be run from the root of the langgraph-dev-navigator project.

# Add the mcp-crawl4ai-rag directory to the Python path to allow imports
sys.path.append(str(Path(__file__).resolve().parent))

from src.utils import get_supabase_client, search_documents
from neo4j import GraphDatabase

def main():
    """
    Runs a series of checks to validate the MCP server setup.
    """
    print("--- Running Setup Validation ---")

    # 1. Check Environment Variables
    print("\n--- [1/4] Checking Environment Variables ---")
    project_root = Path(__file__).resolve().parent
    dotenv_path = project_root / '.env'
    if not dotenv_path.exists():
        print(f"FAILURE: .env file not found at {dotenv_path}")
        sys.exit(1)

    load_dotenv(dotenv_path, override=True)

    required_vars = [
        "SUPABASE_URL",
        "SUPABASE_SERVICE_KEY",
        "NEO4J_URI",
        "NEO4J_USER",
        "NEO4J_PASSWORD",
        "OPENAI_API_KEY"
    ]

    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        print(f"FAILURE: The following required environment variables are not set:")
        for var in missing_vars:
            print(f"  - {var}")
        sys.exit(1)

    print("SUCCESS: All required environment variables are set.")

    # 2. Check Supabase Connection
    print("\n--- [2/4] Checking Supabase Connection ---")
    try:
        supabase_client = get_supabase_client()
        # Perform a simple query to test the connection
        supabase_client.from_("sources").select("source_id").limit(1).execute()
        print("SUCCESS: Connected to Supabase successfully.")
    except Exception as e:
        print(f"FAILURE: Could not connect to Supabase.")
        print(e)
        sys.exit(1)

    # 3. Check Neo4j Connection
    print("\n--- [3/4] Checking Neo4j Connection ---")
    try:
        uri = os.getenv("NEO4J_URI")
        user = os.getenv("NEO4J_USER")
        password = os.getenv("NEO4J_PASSWORD")
        driver = GraphDatabase.driver(uri, auth=(user, password))
        with driver.session() as session:
            session.run("MATCH (n) RETURN count(n)")
        driver.close()
        print("SUCCESS: Connected to Neo4j successfully.")
    except Exception as e:
        print(f"FAILURE: Could not connect to Neo4j.")
        print(e)
        sys.exit(1)

    # 4. Perform a Sample RAG Query
    print("\n--- [4/4] Performing Sample RAG Query ---")
    try:
        results = search_documents(client=supabase_client, query="what is LangGraph?", match_count=1)
        if results:
            print("SUCCESS: RAG query returned results.")
        else:
            print("FAILURE: RAG query did not return any results.")
            sys.exit(1)
    except Exception as e:
        print("FAILURE: RAG query failed.")
        print(e)
        sys.exit(1)

    print("\n--- ✅ All Checks Passed Successfully! ---")

if __name__ == "__main__":
    main()


