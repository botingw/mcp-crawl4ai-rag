from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.utils_botingw import extract_code_blocks
# from typing import List, Dict, Any
# from markdown_it import MarkdownIt


# def extract_for_rag_enrichment(markdown_content: str) -> List[Dict[str, Any]]:
#     """
#     Parses a markdown document and extracts code blocks along with their
#     full preceding and succeeding text blocks for RAG enrichment.

#     Args:
#         markdown_content: The markdown string to parse.

#     Returns:
#         A list of dictionaries, where each dict contains a code block
#         and its full textual context.
#     """
#     md = MarkdownIt()
#     tokens = md.parse(markdown_content)

#     # Step 1: Create a simplified, sequential representation of the document
#     structured_blocks = []
#     current_text = ""
#     for token in tokens:
#         if token.type == 'fence':
#             # If there's pending text, save it before the code block
#             if current_text.strip():
#                 structured_blocks.append({'type': 'text', 'content': current_text.strip()})
#                 current_text = ""
            
#             # Add the code block
#             language = (token.info or "").split()[0] if token.info else None
#             structured_blocks.append({
#                 'type': 'code', 
#                 'content': token.content, 
#                 'language': language
#             })
#         elif token.content:
#             # Accumulate text from various other tokens
#             current_text += token.content
    
#     # Add any final text block at the end
#     if current_text.strip():
#         structured_blocks.append({'type': 'text', 'content': current_text.strip()})

#     # Step 2: Iterate through the structured blocks to find context for each code block
#     enriched_code_blocks = []
#     for i, block in enumerate(structured_blocks):
#         if block['type'] == 'code':
#             context_before = ""
#             # Look at the previous block if it exists and is text
#             if i > 0 and structured_blocks[i-1]['type'] == 'text':
#                 context_before = structured_blocks[i-1]['content']

#             context_after = ""
#             # Look at the next block if it exists and is text
#             if i < len(structured_blocks) - 1 and structured_blocks[i+1]['type'] == 'text':
#                 context_after = structured_blocks[i+1]['content']
            
#             enriched_code_blocks.append({
#                 'code': block['content'],
#                 'language': block['language'],
#                 'context_before': context_before,
#                 'context_after': context_after
#             })
            
#     return enriched_code_blocks


def main():
    """
    Main function to read a markdown file from the command line and extract
    code blocks along with their surrounding text context.
    """
    # # Set up the command-line argument parser
    # parser = argparse.ArgumentParser(
    #     description="Extract code blocks and their context from a markdown file."
    # )
    # parser.add_argument(
    #     "filepath", 
    #     type=str, 
    #     help="The path to the markdown file to be processed."
    # )
    # args = parser.parse_args()
    filepath = '../langgraph/docs/docs/how-tos/http/custom_lifespan.md'

    # Read the specified markdown file
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            print(f"Reading file: {filepath}\n")
            markdown_text = f.read()
    except FileNotFoundError:
        print(f"Error: The file '{filepath}' was not found.")
        return
    except Exception as e:
        print(f"An error occurred while reading the file: {e}")
        return

    # Extract the data using our function
    extracted_data = extract_code_blocks(markdown_text, min_code_words=30)

    if not extracted_data:
        print("No code blocks were found in the document.")
        return

    # Print the results in a clear format
    print(f"Found {len(extracted_data)} code block(s).\n")
    for i, item in enumerate(extracted_data, 1):
        print(f"================== BLOCK {i} ==================")
        
        # Print Context Before
        print("\n--- Context Before Code ---")
        if item['context_before']:
            print(item['context_before'])
        else:
            print("(No preceding text context found)")

        # Print the Code Block
        print(f"\n--- Code Block (language: {item['language']}) ---")
        print(item['code'].strip())

        # Print Context After
        print("\n--- Context After Code ---")
        if item['context_after']:
            print(item['context_after'])
        else:
            print("(No succeeding text context found)")
        
        print("\n==========================================\n")


if __name__ == "__main__":
    main()
