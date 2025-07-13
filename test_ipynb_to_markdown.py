import nbconvert
import pathlib

from src.utils_botingw import num_tokens_from_string

def convert_and_estimate_tokens(notebook_path: pathlib.Path, output_path: pathlib.Path):
    """
    Reads a Jupyter Notebook, calculates its original token count, converts it to 
    Markdown, calculates the new token count, and saves the result.
    """
    print(f"Reading notebook from: {notebook_path}")

    try:
        # 1. Read the raw .ipynb file and calculate its token count
        with open(notebook_path, 'r', encoding='utf-8') as f:
            original_content = f.read()
        original_tokens = num_tokens_from_string(original_content, model_name="gpt-4")
        print(f"Original .ipynb token count: {original_tokens}")

        # 2. Instantiate and configure the exporter
        exporter = nbconvert.MarkdownExporter(exclude_output=False)

        # 3. Perform the conversion from the file path
        markdown_content, resources = exporter.from_filename(notebook_path)

        # 4. Calculate the new token count for the Markdown content
        converted_tokens = num_tokens_from_string(markdown_content, model_name="gpt-4")
        print(f"Converted .md token count: {converted_tokens}")
        print(f'resources: {resources}')
        print(f'content: {markdown_content}')

        # 5. Write the resulting Markdown string to the output file
        print(f"Conversion successful. Saving to: {output_path}")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        # 6. Print the final comparison report
        print("\n--- Token Analysis Complete ---")
        reduction = original_tokens - converted_tokens
        reduction_percent = (reduction / original_tokens * 100) if original_tokens > 0 else 0
        print(f"Token reduction: {reduction} tokens ({reduction_percent:.2f}%)")
        print("Done.")

    except Exception as e:
        print(f"An error occurred during conversion: {e}")


# --- Main execution block ---
if __name__ == "__main__":
    
    # ====================   ACTION REQUIRED   ====================
    # 1. CHANGE THIS to the path of your .ipynb file.
    input_notebook_file = pathlib.Path("../langgraph/docs/docs/how-tos/autogen-integration.ipynb")
    
    # 2. CHANGE THIS to the desired name for your output .md file.
    output_markdown_file = pathlib.Path("autogen-integration.md")
    # =============================================================

    # Safety check to ensure the input file actually exists before trying to convert it.
    if not input_notebook_file.exists():
        print(f"Error: Input file not found at '{input_notebook_file}'")
        print("Please check that the path is correct.")
    else:
        # If the file exists, run the conversion and estimation function.
        convert_and_estimate_tokens(input_notebook_file, output_markdown_file)