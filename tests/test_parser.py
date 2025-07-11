import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

# Add knowledge_graphs to the Python path to allow direct import
import sys
knowledge_graphs_path = Path(__file__).resolve().parent / 'knowledge_graphs'
sys.path.append(str(knowledge_graphs_path))

try:
    from parse_repo_into_neo4j import DirectNeo4jExtractor
except ImportError as e:
    print(f"Failed to import DirectNeo4jExtractor: {e}")
    print("Please ensure you are running this script from the project root directory.")
    sys.exit(1)

async def main():
    """
    Initializes the extractor, runs the analysis, and cleans up.
    """
    # Load environment variables from .env file
    project_root = Path(__file__).resolve().parent
    dotenv_path = project_root / '.env'
    if dotenv_path.exists():
        print(f"Loading environment variables from {dotenv_path}")
        load_dotenv(dotenv_path, override=True)
    else:
        print(f"Warning: .env file not found at {dotenv_path}")

    # Check for Neo4j credentials
    neo4j_uri = os.getenv("NEO4J_URI")
    neo4j_user = os.getenv("NEO4J_USER")
    neo4j_password = os.getenv("NEO4J_PASSWORD")

    if not all([neo4j_uri, neo4j_user, neo4j_password]):
        print("Error: Neo4j environment variables (NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD) are not set.")
        print("Please create a .env file in the project root with these values.")
        return

    print("Neo4j credentials found. Initializing extractor...")
    
    # The repository to test
    repo_url = "https://github.com/langchain-ai/langgraph.git"
    
    extractor = None
    try:
        # Initialize the extractor
        extractor = DirectNeo4jExtractor(neo4j_uri, neo4j_user, neo4j_password)
        await extractor.initialize()
        print("✓ Extractor initialized successfully.")
        
        # Run the analysis
        print(f"\nStarting analysis for repository: {repo_url}")
        await extractor.analyze_repository(repo_url)
        print("\n✓ Repository analysis completed successfully!")
        
        repo_name = repo_url.split('/')[-1].replace('.git', '')
        print(f"\nTo verify, you can now use the query_knowledge_graph tool with the command: explore {repo_name}")

    except Exception as e:
        print(f"\n--- An error occurred during repository analysis ---")
        import traceback
        traceback.print_exc()
        print(f"----------------------------------------------------")

    finally:
        # Ensure the extractor connection is closed
        if extractor:
            await extractor.close()
            print("\n✓ Extractor connection closed.")

if __name__ == "__main__":
    # Check if git is installed
    if os.system("git --version > /dev/null 2>&1") != 0:
        print("Error: Git is not installed or not in the system's PATH.")
        print("Please install Git to proceed.")
    else:
        asyncio.run(main())
