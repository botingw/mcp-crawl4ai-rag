from typing import Dict, Any, Optional
import os
import json
from pathlib import Path
import asyncio

# Assuming DirectNeo4jExtractor is available in knowledge_graphs
# We need to ensure knowledge_graphs is in sys.path for this to work
# For a standalone script, we might need to add it explicitly or adjust imports
from knowledge_graphs.parse_repo_into_neo4j import DirectNeo4jExtractor

def validate_github_url(repo_url: str) -> Dict[str, Any]:
    """Validate GitHub repository URL."""
    if not repo_url or not isinstance(repo_url, str):
        return {"valid": False, "error": "Repository URL is required"}
    
    repo_url = repo_url.strip()
    
    # Basic GitHub URL validation
    if not ("github.com" in repo_url.lower() or repo_url.endswith(".git")):
        return {"valid": False, "error": "Please provide a valid GitHub repository URL"}
    
    # Check URL format
    if not (repo_url.startswith("https://") or repo_url.startswith("git@")):
        return {"valid": False, "error": "Repository URL must start with https:// or git@"}
    
    return {"valid": True, "repo_name": repo_url.split('/')[-1].replace('.git', '')}

async def ingest_github_repository_core(repo_url: str) -> Dict[str, Any]:
    """
    Core logic to parse a GitHub repository into the Neo4j knowledge graph.
    This function is designed to be called by both the MCP tool and a standalone CLI.
    """
    try:
        # Check if knowledge graph functionality is enabled
        knowledge_graph_enabled = os.getenv("USE_KNOWLEDGE_GRAPH", "false") == "true"
        if not knowledge_graph_enabled:
            return {
                "success": False,
                "error": "Knowledge graph functionality is disabled. Set USE_KNOWLEDGE_GRAPH=true in environment."
            }
        
        # Validate repository URL
        validation = validate_github_url(repo_url)
        if not validation["valid"]:
            return {
                "success": False,
                "repo_url": repo_url,
                "error": validation["error"]
            }
        
        repo_name = validation["repo_name"]
        
        # Initialize repository extractor
        # This part assumes NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD are set in environment
        neo4j_uri = os.getenv("NEO4J_URI")
        neo4j_user = os.getenv("NEO4J_USER")
        neo4j_password = os.getenv("NEO4J_PASSWORD")

        if not (neo4j_uri and neo4j_user and neo4j_password):
            return {
                "success": False,
                "error": "Neo4j credentials not configured. Set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD in environment."
            }

        repo_extractor = DirectNeo4jExtractor(neo4j_uri, neo4j_user, neo4j_password)
        await repo_extractor.initialize() # Initialize the driver connection

        try:
            # Parse the repository (this includes cloning, analysis, and Neo4j storage)
            print(f"Starting repository analysis for: {repo_name}")
            await repo_extractor.analyze_repository(repo_url)
            print(f"Repository analysis completed for: {repo_name}")
            
            # Query Neo4j for statistics about the parsed repository
            async with repo_extractor.driver.session() as session:
                # Get comprehensive repository statistics
                stats_query = """
                MATCH (r:Repository {name: $repo_name})
                OPTIONAL MATCH (r)-[:CONTAINS]->(f:File)
                OPTIONAL MATCH (f)-[:DEFINES]->(c:Class)
                OPTIONAL MATCH (c)-[:HAS_METHOD]->(m:Method)
                OPTIONAL MATCH (f)-[:DEFINES]->(func:Function)
                OPTIONAL MATCH (c)-[:HAS_ATTRIBUTE]->(a:Attribute)
                WITH r, 
                     count(DISTINCT f) as files_count,
                     count(DISTINCT c) as classes_count,
                     count(DISTINCT m) as methods_count,
                     count(DISTINCT func) as functions_count,
                     count(DISTINCT a) as attributes_count
                
                // Get some sample module names
                OPTIONAL MATCH (r)-[:CONTAINS]->(sample_f:File)
                WITH r, files_count, classes_count, methods_count, functions_count, attributes_count,
                     collect(DISTINCT sample_f.module_name)[0..5] as sample_modules
                
                RETURN 
                    r.name as repo_name,
                    files_count,
                    classes_count, 
                    methods_count,
                    functions_count,
                    attributes_count,
                    sample_modules
                """
                
                result = await session.run(stats_query, repo_name=repo_name)
                record = await result.single()
                
                if record:
                    stats = {
                        "repository": record['repo_name'],
                        "files_processed": record['files_count'],
                        "classes_created": record['classes_count'],
                        "methods_created": record['methods_count'], 
                        "functions_created": record['functions_count'],
                        "attributes_created": record['attributes_count'],
                        "sample_modules": record['sample_modules'] or []
                    }
                else:
                    return {
                        "success": False,
                        "repo_url": repo_url,
                        "error": f"Repository '{repo_name}' not found in database after parsing"
                    }
            
            return {
                "success": True,
                "repo_url": repo_url,
                "repo_name": repo_name,
                "message": f"Successfully parsed repository '{repo_name}' into knowledge graph",
                "statistics": stats,
                "ready_for_validation": True,
                "next_steps": [
                    "Repository is now available for hallucination detection",
                    f"Use check_ai_script_hallucinations to validate scripts against {repo_name}",
                    "The knowledge graph contains classes, methods, and functions from this repository"
                ]
            }
        finally:
            await repo_extractor.close() # Close the driver connection
        
    except Exception as e:
        return {
            "success": False,
            "repo_url": repo_url,
            "error": f"Repository parsing failed: {str(e)}"
        }
