from typing import Dict, Any, List
from pathlib import Path
import tempfile
import subprocess
import os

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

