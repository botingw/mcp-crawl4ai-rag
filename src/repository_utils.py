# Copyright (c) 2025 Boting Wang
# Copyright (c) 2025 Cole Medin
#
# SPDX-License-Identifier: MIT

from typing import Dict, Any, List, Optional
from pathlib import Path
import tempfile
import subprocess
import os

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
        subprocess.run(['git', 'clone', '--depth', '1', repo_url, temp_dir.name], check=True, capture_output=True, text=True)
        return temp_dir
    except subprocess.CalledProcessError as e:
        temp_dir.cleanup()
        error_message = f"Failed to clone repository. Git command failed with exit code {e.returncode}.\n"
        error_message += f"Stderr: {e.stderr.strip()}\n"
        error_message += f"Stdout: {e.stdout.strip()}"
        raise RuntimeError(error_message) from e

def get_repository_files(repo_path: str, include_folders: Optional[List[str]] = None) -> Dict[str, List[Path]]:
    """
    Get Python and documentation files from a repository, optionally filtering by included folders.
    """
    python_files = []
    doc_files = []
    
    exclude_dirs = {
        'tests', 'test', '__pycache__', '.git', 'venv', 'env',
        'node_modules', 'build', 'dist', '.pytest_cache',
        'examples', 'example', 'demo', 'benchmark'
    }
    
    doc_extensions = {'.md', '.mdx', '.rst', '.ipynb', '.txt'}
    
    # Normalize include_folders to be absolute paths from repo_path
    normalized_include_folders = []
    if include_folders:
        for folder in include_folders:
            normalized_include_folders.append(Path(repo_path) / folder)

    for root, dirs, files in os.walk(repo_path):
        current_path = Path(root)
        
        # Filter directories to traverse
        dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith('.')]
        
        

        for file in files:
            file_path = current_path / file
            # If include_folders are specified, check if the file is within one of them
            if normalized_include_folders:
                is_file_in_included_folder = False
                for included_folder_path in normalized_include_folders:
                    # Check if the file_path is within the included_folder_path
                    if file_path.is_relative_to(included_folder_path):
                        is_file_in_included_folder = True
                        break
                if not is_file_in_included_folder:
                    continue # Skip this file if it's not in an included folder

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

def process_document_files(doc_files: List[Path], repo_path: str) -> List[Dict[str, str]]:
    """Processes a list of documentation files, converting notebooks to markdown."""
    import nbconvert
    docs_content = []
    for doc_file in doc_files:
        try:
            relative_path = str(doc_file.relative_to(repo_path))
            if doc_file.suffix == '.ipynb':
                exporter = nbconvert.MarkdownExporter(exclude_output=False)
                markdown_content, _ = exporter.from_filename(doc_file)
                docs_content.append({"url": relative_path, "markdown": markdown_content})
            else:
                with open(doc_file, 'r', encoding='utf-8') as f:
                    docs_content.append({"url": relative_path, "markdown": f.read()})
        except Exception as e:
            print(f"Skipping file {doc_file} due to processing error: {e}")
    return docs_content