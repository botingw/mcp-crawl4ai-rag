import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

# This script is designed to be run from the root of the langgraph-dev-navigator project.

# Add the mcp-crawl4ai-rag directory to the Python path to allow imports
sys.path.append(str(Path(__file__).resolve().parent))

from src.utils_botingw import get_supabase_client, search_documents
from neo4j import GraphDatabase

def run_stage_1_checks():
    """Runs checks for environment variables and basic connectivity."""
    print("--- Running Stage 1: Environment and Connection Checks ---")
    
    # 1. Check Environment Variables
    print("\n--- [1/3] Checking Environment Variables ---")
    project_root = Path(__file__).resolve().parent
    dotenv_path = project_root / '.env'
    if not dotenv_path.exists():
        print(f"FAILURE: .env file not found at {dotenv_path}")
        sys.exit(1)

    load_dotenv(dotenv_path, override=True)

    required_vars = [
        "SUPABASE_URL", "SUPABASE_SERVICE_KEY",
        "NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD",
        "OPENAI_API_KEY"
    ]
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        print(f"FAILURE: The following required environment variables are not set:")
        for var in missing_vars: print(f"  - {var}")
        sys.exit(1)
    print("SUCCESS: All required environment variables are set.")

    # 2. Check Supabase Connection
    print("\n--- [2/3] Checking Supabase Connection ---")
    try:
        supabase_client = get_supabase_client()
        supabase_client.from_("sources").select("source_id").limit(1).execute()
        print("SUCCESS: Connected to Supabase successfully.")
    except Exception as e:
        print(f"FAILURE: Could not connect to Supabase. Check your SUPABASE_URL and SUPABASE_SERVICE_KEY.\n{e}")
        sys.exit(1)

    # 3. Check Neo4j Connection
    print("\n--- [3/3] Checking Neo4j Connection ---")
    try:
        uri, user, password = os.getenv("NEO4J_URI"), os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")
        driver = GraphDatabase.driver(uri, auth=(user, password))
        with driver.session() as session:
            session.run("MATCH (n) RETURN count(n)")
        driver.close()
        print("SUCCESS: Connected to Neo4j successfully.")
    except Exception as e:
        print(f"FAILURE: Could not connect to Neo4j. Check your NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD.\n{e}")
        sys.exit(1)
    
    print("\n--- ✅ Stage 1 Checks Passed Successfully! ---")
    return supabase_client, driver

def run_stage_2_checks(supabase_client, driver):
    """Runs checks for data integrity after ingestion."""
    print("\n--- Running Stage 2: Data Integrity and RAG Checks ---")

    # 1. Check for Supabase Data
    print("\n--- [1/3] Checking for Data in Supabase ---")
    try:
        response = supabase_client.from_('crawled_pages').select('id', count='exact').limit(1).execute()
        if response.count > 0:
            print(f"SUCCESS: Found {response.count} rows in 'crawled_pages' table.")
        else:
            print("FAILURE: No data found in 'crawled_pages' table. Did the data ingestion run correctly?")
            sys.exit(1)
    except Exception as e:
        print(f"FAILURE: Querying Supabase for data failed.\n{e}")
        sys.exit(1)

    # 2. Check for Neo4j Data
    print("\n--- [2/3] Checking for Data in Neo4j ---")
    try:
        with driver.session() as session:
            result = session.run("MATCH (n) RETURN count(n) AS count").single()
            node_count = result['count']
            if node_count > 0:
                print(f"SUCCESS: Found {node_count} nodes in the Neo4j database.")
            else:
                print("FAILURE: No nodes found in Neo4j. Did the data ingestion run correctly?")
                sys.exit(1)
    except Exception as e:
        print(f"FAILURE: Querying Neo4j for data failed.\n{e}")
        sys.exit(1)
    finally:
        driver.close()

    # 3. Perform a Sample RAG Query
    print("\n--- [3/3] Performing Sample RAG Query ---")
    try:
        results = search_documents(client=supabase_client, query="what is LangGraph?", match_count=1)
        if results:
            print("SUCCESS: RAG query returned results.")
        else:
            print("FAILURE: RAG query did not return any results. This indicates an issue with the embedding or search function.")
            sys.exit(1)
    except Exception as e:
        print(f"FAILURE: RAG query failed.\n{e}")
        sys.exit(1)

    print("\n--- ✅ Stage 2 Checks Passed Successfully! ---")

def main():
    parser = argparse.ArgumentParser(description="Run validation checks for the MCP server setup.")
    parser.add_argument("--stage", type=int, choices=[1, 2], default=1, help="Specify the validation stage to run (1 for connections, 2 for data integrity). Default is 1.")
    args = parser.parse_args()

    supabase_client, driver = run_stage_1_checks()

    if args.stage == 2:
        run_stage_2_checks(supabase_client, driver)
    
    print("\nValidation complete.")

if __name__ == "__main__":
    main()