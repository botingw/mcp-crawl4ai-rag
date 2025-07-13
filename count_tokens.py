import os
from pathlib import Path
import sys

# Add the parent directory of 'mcp-crawl4ai-rag' to the Python path
# This is necessary for the imports to work
# sys.path.append(str(Path(__file__).resolve().parent / "mcp-crawl4ai-rag"))

from src.repository_utils import clone_repository, get_repository_files
from src.utils_botingw import num_tokens_from_string

def count_tokens_in_repo(repo_url: str, include_folders: list[str] = None) -> tuple[int, int]:
    """
    Clones a GitHub repository, counts the tokens in its documentation files
    (markdown, text, ipynb), and returns the total tokens and file count.
    """
    total_tokens = 0
    file_count = 0

    print(f"Cloning repository: {repo_url}")
    with clone_repository(repo_url) as temp_repo_dir:
        repo_path = temp_repo_dir
        print(f"Repository cloned to: {repo_path}")

        print("Getting documentation files...")
        files_in_repo = get_repository_files(repo_path, include_folders=include_folders)
        doc_files = files_in_repo.get("doc_files", [])
        
        print(f"Found {len(doc_files)} documentation files.")

        for file_path in doc_files:
            file_count += 1
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                # Using a common model name for token counting, adjust if needed
                num_tokens = num_tokens_from_string(content, model_name="gpt-4")
                total_tokens += num_tokens
            except Exception as e:
                print(f"Could not process file {file_path}: {e}")

    return total_tokens, file_count

if __name__ == "__main__":
    # Example Usage:
    # Replace with the actual GitHub repository URL you want to analyze
    github_repo_url = "https://github.com/langchain-ai/langgraph.git"
    # Specify folders to include, relative to the repository root
    # For LangGraph docs, it's typically 'docs/docs'
    # folders_to_include = ["docs/docs/how-tos/http"]
    folders_to_include = ["docs/docs"]


    print(f"\n--- Starting Token Count for {github_repo_url} ---")
    print(f"Including folders: {folders_to_include}")

    try:
        total_tokens, file_count = count_tokens_in_repo(github_repo_url, include_folders=folders_to_include)
        print(f"\nTotal documentation files processed: {file_count}")
        print(f"Total estimated tokens for documentation: {total_tokens}")
    except Exception as e:
        print(f"An error occurred: {e}")