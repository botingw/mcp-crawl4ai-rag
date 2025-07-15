from typing import Dict, Any, List
import os
from pathlib import Path
import traceback


from repository_utils import clone_repository, get_repository_files, validate_github_url, process_document_files
from src.utils_botingw import add_documents_to_supabase, extract_source_summary, update_source_info, add_code_examples_to_supabase, extract_code_blocks, process_code_example
from src.crawl_utils import smart_chunk_markdown, extract_section_info

async def ingest_docs_to_rag(supabase_client, doc_files: List[Path], source_id: str, repo_path: str) -> Dict[str, Any]:
    """Processes documentation files and ingests them into the RAG system."""

    docs_content = process_document_files(doc_files, repo_path)

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
        code_urls = []
        code_chunk_numbers = []
        code_examples = []
        code_summaries = []
        code_metadatas = []

        for doc in docs_content:
            blocks = extract_code_blocks(doc['markdown'])
            for i, block in enumerate(blocks):
                all_code_blocks.append(block)
                code_urls.append(doc['url'])
                code_chunk_numbers.append(i)
                code_examples.append(block['code'])
                code_summaries.append(process_code_example((block['code'], block['context_before'], block['context_after'], doc['url'], i)))
                code_metadatas.append({
                    "source": source_id,
                    "url": doc['url'],
                    "chunk_index": i,
                    "char_count": len(block['code']),
                    "word_count": len(block['code'].split()),
                    "language": block['language']
                })

        if all_code_blocks:
            add_code_examples_to_supabase(supabase_client, code_urls, code_chunk_numbers, code_examples, code_summaries, code_metadatas)
            code_examples_found = len(all_code_blocks)

    return {"status": "success", "files_processed": len(doc_files), "chunks_created": len(contents), "code_examples_found": code_examples_found}

from typing import Dict, Any, List, Optional

async def ingest_repository(repo_url: str, ingest_types: List[str] = ["code", "docs"], include_folders: Optional[List[str]] = None):
    """Orchestrates the ingestion of a GitHub repository."""
    from knowledge_graphs.parse_repo_into_neo4j_botingw import DirectNeo4jExtractor
    from utils import get_supabase_client

    validation = validate_github_url(repo_url)
    if not validation["valid"]:
        return {"success": False, "error": validation["error"]}
    
    repo_name = validation["repo_name"]
    results = {}
    temp_dir_obj = None

    try:
        temp_dir_obj = clone_repository(repo_url)
        files = get_repository_files(temp_dir_obj.name, include_folders=include_folders)
        
        if "code" in ingest_types and os.getenv("USE_KNOWLEDGE_GRAPH", "false") == "true":
            neo4j_uri = os.getenv("NEO4J_URI")
            neo4j_user = os.getenv("NEO4J_USER")
            neo4j_password = os.getenv("NEO4J_PASSWORD")
            repo_extractor = DirectNeo4jExtractor(neo4j_uri, neo4j_user, neo4j_password)
            await repo_extractor.initialize()
            # We need to pass the repo_path to the analyze_repository function
            await repo_extractor.analyze_repository(repo_url, temp_dir_obj.name)
            results["code_ingestion"] = {"status": "success", "files_processed": len(files["python_files"])}
            await repo_extractor.close()

        if "docs" in ingest_types:
            supabase_client = get_supabase_client()
            results["docs_ingestion"] = await ingest_docs_to_rag(supabase_client, files["doc_files"], f"github.com/{repo_name}", temp_dir_obj.name)

        return {"success": True, "repo_url": repo_url, "results": results}

    except Exception as e:
        error_details = traceback.format_exc()
        print(f"An error occurred during repository ingestion:\n{error_details}")
        return {"success": False, "repo_url": repo_url, "error": str(e), "details": error_details}
    finally:
        if temp_dir_obj:
            temp_dir_obj.cleanup()
