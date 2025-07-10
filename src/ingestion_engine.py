from typing import Dict, Any, List
from urllib.parse import urlparse
import os
from pathlib import Path
import tempfile
import git

# It's better to handle imports within the functions that use them to avoid circular dependencies
# and to make the engine more modular.

def validate_github_url(repo_url: str) -> Dict[str, Any]:
    """Validate GitHub repository URL."""
    if not repo_url or not isinstance(repo_url, str):
        return {"valid": False, "error": "Repository URL is required"}
    
    repo_url = repo_url.strip()
    
    if not ("github.com" in repo_url.lower() or repo_url.endswith(".git")):
        return {"valid": False, "error": "Please provide a valid GitHub repository URL"}
    
    if not (repo_url.startswith("https://") or repo_url.startswith("git@")):
        return {"valid": False, "error": "Repository URL must start with https:// or git@"}
    
    return {"valid": True, "repo_name": repo_url.split('/')[-1].replace('.git', '')}

def clone_repository(repo_url: str) -> tempfile.TemporaryDirectory:
    """Clones a repository to a temporary directory and returns the directory object."""
    temp_dir = tempfile.TemporaryDirectory()
    try:
        git.Repo.clone_from(repo_url, temp_dir.name)
        return temp_dir
    except git.exc.GitCommandError as e:
        temp_dir.cleanup()
        raise RuntimeError(f"Failed to clone repository: {e}") from e

def get_repository_files(repo_path: str) -> Dict[str, List[Path]]:
    """
    Get Python and documentation files from a repository.
    """
    python_files = []
    doc_files = []
    
    exclude_dirs = {
        'tests', 'test', '__pycache__', '.git', 'venv', 'env',
        'node_modules', 'build', 'dist', '.pytest_cache',
        'examples', 'example', 'demo', 'benchmark'
    }
    
    doc_extensions = {'.md', '.mdx', '.rst', '.ipynb'}
    
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith('.')]
        
        for file in files:
            file_path = Path(root) / file
            
            if file.endswith('.py') and not file.startswith('test_'):
                if (file_path.stat().st_size < 500_000 and 
                    file not in ['setup.py', 'conftest.py']):
                    python_files.append(file_path)
            
            elif file_path.suffix in doc_extensions:
                doc_files.append(file_path)
                
    return {
        "python_files": python_files,
        "doc_files": doc_files
    }

async def ingest_code_to_kg(repo_extractor, python_files: List[Path]) -> Dict[str, Any]:
    """Analyzes Python files and ingests them into the knowledge graph."""
    from .knowledge_graphs.parse_repo_into_neo4j import Neo4jCodeAnalyzer
    analyzer = Neo4jCodeAnalyzer()
    files_processed = 0
    for file_path in python_files:
        try:
            analysis_result = analyzer.analyze_python_file(str(file_path))
            await repo_extractor._create_graph_from_analysis(analysis_result)
            files_processed += 1
        except Exception as e:
            print(f"Skipping file {file_path} due to analysis error: {e}")
    return {"status": "success", "files_processed": files_processed}

async def ingest_docs_to_rag(supabase_client, doc_files: List[Path], source_id: str) -> Dict[str, Any]:
    """Processes documentation files and ingests them into the RAG system."""
    from .utils import add_documents_to_supabase, extract_source_summary, update_source_info, add_code_examples_to_supabase, extract_code_blocks
    from .crawl4ai_mcp import smart_chunk_markdown, extract_section_info, process_code_example

    docs_content = []
    for doc_file in doc_files:
        with open(doc_file, 'r', encoding='utf-8') as f:
            docs_content.append({"url": doc_file.as_uri(), "markdown": f.read()})

    urls, chunk_numbers, contents, metadatas = [], [], [], []
    source_content_map = {}
    source_word_counts = {}

    for doc in docs_content:
        source_url = doc['url']
        md = doc['markdown']
        chunks = smart_chunk_markdown(md)
        
        if source_id not in source_content_map:
            source_content_map[source_id] = md[:5000]
            source_word_counts[source_id] = 0

        for i, chunk in enumerate(chunks):
            urls.append(source_url)
            chunk_numbers.append(i)
            contents.append(chunk)
            
            meta = extract_section_info(chunk)
            meta["chunk_index"] = i
            meta["url"] = source_url
            meta["source"] = source_id
            metadatas.append(meta)
            
            source_word_counts[source_id] += meta.get("word_count", 0)

    url_to_full_document = {doc['url']: doc['markdown'] for doc in docs_content}
    
    source_summary = extract_source_summary(source_id, source_content_map.get(source_id, ""))
    update_source_info(supabase_client, source_id, source_summary, source_word_counts.get(source_id, 0))
    
    add_documents_to_supabase(supabase_client, urls, chunk_numbers, contents, metadatas, url_to_full_document)

    code_examples_found = 0
    if os.getenv("USE_AGENTIC_RAG", "false") == "true":
        all_code_blocks = []
        for doc in docs_content:
            all_code_blocks.extend(extract_code_blocks(doc['markdown']))
        
        if all_code_blocks:
            code_examples = [block['code'] for block in all_code_blocks]
            # This can be slow, consider parallel execution for production
            code_summaries = [process_code_example((block['code'], block['context_before'], block['context_after'])) for block in all_code_blocks]
            code_urls = [doc['url'] for doc in docs_content for _ in extract_code_blocks(doc['markdown'])]
            code_chunk_numbers = list(range(len(all_code_blocks)))
            code_metadatas = [{"source": source_id} for _ in all_code_blocks]

            add_code_examples_to_supabase(supabase_client, code_urls, code_chunk_numbers, code_examples, code_summaries, code_metadatas)
            code_examples_found = len(all_code_blocks)

    return {"status": "success", "files_processed": len(doc_files), "chunks_created": len(contents), "code_examples_found": code_examples_found}

async def ingest_repository(repo_url: str, ingest_types: List[str] = ["code", "docs"]):
    """Orchestrates the ingestion of a GitHub repository."""
    from .knowledge_graphs.parse_repo_into_neo4j import DirectNeo4jExtractor
    from .utils import get_supabase_client

    validation = validate_github_url(repo_url)
    if not validation["valid"]:
        return {"success": False, "error": validation["error"]}
    
    repo_name = validation["repo_name"]
    results = {}
    temp_dir = None

    try:
        temp_dir = clone_repository(repo_url)
        files = get_repository_files(temp_dir.name)
        
        if "code" in ingest_types and os.getenv("USE_KNOWLEDGE_GRAPH", "false") == "true":
            neo4j_uri = os.getenv("NEO4J_URI")
            neo4j_user = os.getenv("NEO4J_USER")
            neo4j_password = os.getenv("NEO4J_PASSWORD")
            repo_extractor = DirectNeo4jExtractor(neo4j_uri, neo4j_user, neo4j_password)
            await repo_extractor.initialize()
            results["code_ingestion"] = await ingest_code_to_kg(repo_extractor, files["python_files"])
            await repo_extractor.close()

        if "docs" in ingest_types:
            supabase_client = get_supabase_client()
            results["docs_ingestion"] = await ingest_docs_to_rag(supabase_client, files["doc_files"], f"github.com/{repo_name}")

        return {"success": True, "repo_url": repo_url, "results": results}

    except Exception as e:
        return {"success": False, "repo_url": repo_url, "error": str(e)}
    finally:
        if temp_dir:
            temp_dir.cleanup()

