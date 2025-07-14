import os
from pathlib import Path
import sys

# Add the parent directory of 'mcp-crawl4ai-rag' to the Python path
# This is necessary for the imports to work
# sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.repository_utils import clone_repository, get_repository_files, process_document_files
from src.utils_botingw import num_tokens_from_string, extract_code_blocks
from src.crawl4ai_mcp_botingw import smart_chunk_markdown
from src.config import MAX_TOKENS_PER_REQUEST

def count_tokens_in_repo(repo_url: str, include_folders: list[str] = None) -> tuple[int, int, int, int, int]:
    """
    Clones a GitHub repository, counts the tokens in its documentation files,
    and estimates the prompt tokens for all summarization and contextual embedding tasks.
    """
    total_raw_tokens = 0
    total_source_prompt_tokens = 0
    total_chunk_prompt_tokens = 0
    total_code_summary_prompt_tokens = 0
    file_count = 0

    print(f"Cloning repository: {repo_url}")
    with clone_repository(repo_url) as temp_repo_dir:
        repo_path = temp_repo_dir
        print(f"Repository cloned to: {repo_path}")

        print("Getting documentation files...")
        files_in_repo = get_repository_files(repo_path, include_folders=include_folders)
        doc_files = files_in_repo.get("doc_files", [])
        
        print(f"Found {len(doc_files)} documentation files.")

        processed_docs = process_document_files(doc_files, repo_path)

        for doc in processed_docs:
            file_count += 1
            content = doc['markdown']
            
            # 1. Count raw tokens
            raw_tokens = num_tokens_from_string(content, model_name="gpt-4")
            total_raw_tokens += raw_tokens

            # 2. Estimate prompt tokens for source summary
            source_id = doc['url']
            truncated_content = content[:MAX_TOKENS_PER_REQUEST]
            prompt = f"""<source_content>\n{truncated_content}\n</source_content>\n\nThe above content is from the documentation for '{source_id}'. Please provide a concise summary (3-5 sentences) that describes what this library/tool/framework is about. The summary should help understand what the library/tool/framework accomplishes and the purpose.\n"""
            total_source_prompt_tokens += num_tokens_from_string(prompt, model_name="gpt-4")

            # 3. Estimate prompt tokens for chunk contextual embeddings
            chunks = smart_chunk_markdown(content)
            for chunk in chunks:
                prompt = f"""<document>\n{content[:MAX_TOKENS_PER_REQUEST]}\n</document>\nHere is the chunk we want to situate within the whole document\n<chunk>\n{chunk}\n</chunk>\nPlease give a short succinct context to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk. Answer only with the succinct context and nothing else."""
                total_chunk_prompt_tokens += num_tokens_from_string(prompt, model_name="gpt-4")

            # 4. Estimate prompt tokens for code example summaries
            code_blocks = extract_code_blocks(content)
            for block in code_blocks:
                prompt = f"""<context_before>\n{block['context_before'][-500:]}\n</context_before>\n\n<code_example>\n{block['code'][:MAX_TOKENS_PER_REQUEST]}\n</code_example>\n\n<context_after>\n{block['context_after'][:500]}\n</context_after>\n\nBased on the code example and its surrounding context, provide a concise summary (2-3 sentences) that describes what this code example demonstrates and its purpose. Focus on the practical application and key concepts illustrated.\n"""
                total_code_summary_prompt_tokens += num_tokens_from_string(prompt, model_name="gpt-4")

    return total_raw_tokens, total_source_prompt_tokens, total_chunk_prompt_tokens, total_code_summary_prompt_tokens, file_count

if __name__ == "__main__":
    github_repo_url = "https://github.com/langchain-ai/langgraph.git"
    folders_to_include = ["docs/docs"]

    print(f"\n--- Starting Token Count for {github_repo_url} ---")
    print(f"Including folders: {folders_to_include}")

    try:
        raw_tokens, source_prompts, chunk_prompts, code_prompts, file_count = count_tokens_in_repo(github_repo_url, include_folders=folders_to_include)
        
        print(f"\n--- Analysis Complete ---")
        print(f"Total documentation files processed: {file_count}")
        print(f"Total estimated RAW tokens for documentation: {raw_tokens}")
        print("--------------------------------------------------")
        print(f"Total estimated PROMPT tokens for source summarization: {source_prompts}")
        print(f"Total estimated PROMPT tokens for chunk contextualization: {chunk_prompts}")
        print(f"Total estimated PROMPT tokens for code example summarization: {code_prompts}")
        
        total_prompt_tokens = source_prompts + chunk_prompts + code_prompts
        print("--------------------------------------------------")
        print(f"Total estimated PROMPT tokens (all sources): {total_prompt_tokens}")
        
        if raw_tokens > 0:
            print(f"\nEstimated prompt overhead factor: {total_prompt_tokens / raw_tokens:.2f}x")

    except Exception as e:
        print(f"An error occurred: {e}")