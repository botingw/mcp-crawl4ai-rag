

"""
Utility functions for the Crawl4AI MCP server.
"""
import os
import concurrent.futures
from typing import List, Dict, Any, Optional, Tuple
import json
from supabase import create_client, Client
from urllib.parse import urlparse
import openai
import re
import time
import random
from .config import INITIAL_DELAY, EXPONENTIAL_BASE, JITTER, MAX_RETRIES, MAX_WORKERS, MAX_TOKENS_PER_REQUEST

def retry_with_exponential_backoff(func):
    """Retry a function with exponential backoff for OpenAI API calls."""
    def wrapper(*args, **kwargs):
        num_retries = 0
        delay = INITIAL_DELAY
        while True:
            try:
                return func(*args, **kwargs)
            except openai.RateLimitError as e:
                num_retries += 1
                if num_retries > MAX_RETRIES:
                    raise Exception(f"Maximum number of retries ({MAX_RETRIES}) exceeded for function {func.__name__}.") from e
                
                delay *= EXPONENTIAL_BASE * (1 + JITTER * random.random())
                print(f"OpenAI rate limit exceeded. Retrying {func.__name__} in {delay:.2f} seconds...")
                time.sleep(delay)
            except openai.APIError as e:
                num_retries += 1
                if num_retries > MAX_RETRIES:
                    raise Exception(f"Maximum number of retries ({MAX_RETRIES}) exceeded for function {func.__name__}.") from e
                
                delay *= EXPONENTIAL_BASE * (1 + JITTER * random.random())
                print(f"OpenAI API error: {e}. Retrying {func.__name__} in {delay:.2f} seconds...")
                time.sleep(delay)

    return wrapper

# Load OpenAI API key for embeddings
openai.api_key = os.getenv("OPENAI_API_KEY")

def get_supabase_client() -> Client:
    """
    Get a Supabase client with the URL and key from environment variables.
    
    Returns:
        Supabase client instance
    """
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in environment variables")
    
    return create_client(url, key)

@retry_with_exponential_backoff
def create_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """
    Create embeddings for multiple texts in a single API call.
    
    Args:
        texts: List of texts to create embeddings for
        
    Returns:
        List of embeddings (each embedding is a list of floats)
    """
    if not texts:
        return []
    
    try:
        response = openai.embeddings.create(
            model="text-embedding-3-small",
            input=texts
        )
        return [item.embedding for item in response.data]
    except Exception as e:
        print(f"Failed to create batch embeddings: {e}")
        embeddings = []
        for text in texts:
            try:
                embeddings.append(create_embedding(text))
            except Exception as individual_error:
                print(f"Failed to create individual embedding: {individual_error}")
                embeddings.append([0.0] * 1536)
        return embeddings

def create_embedding(text: str) -> List[float]:
    """
    Create an embedding for a single text using OpenAI's API.
    
    Args:
        text: Text to create an embedding for
        
    Returns:
        List of floats representing the embedding
    """
    try:
        embeddings = create_embeddings_batch([text])
        return embeddings[0] if embeddings else [0.0] * 1536
    except Exception as e:
        print(f"Error creating embedding: {e}")
        return [0.0] * 1536

@retry_with_exponential_backoff
def generate_contextual_embedding(full_document: str, chunk: str) -> Tuple[str, bool]:
    """
    Generate contextual information for a chunk within a document to improve retrieval.
    
    Args:
        full_document: The complete document text
        chunk: The specific chunk of text to generate context for
        
    Returns:
        Tuple containing:
        - The contextual text that situates the chunk within the document
        - Boolean indicating if contextual embedding was performed
    """
    model_choice = os.getenv("MODEL_CHOICE")
    
    try:
        prompt = f"""<document> 
{full_document[:MAX_TOKENS_PER_REQUEST]} 
</document>
Here is the chunk we want to situate within the whole document 
<chunk> 
{chunk}
</chunk> 
Please give a short succinct context to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk. Answer only with the succinct context and nothing else."""

        response = openai.chat.completions.create(
            model=model_choice,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that provides concise contextual information."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=200
        )
        
        context = response.choices[0].message.content.strip()
        
        contextual_text = f"{context}\n---\n{chunk}"
        
        return contextual_text, True
    
    except Exception as e:
        print(f"Error generating contextual embedding: {e}. Using original chunk instead.")
        return chunk, False

def process_chunk_with_context(args):
    """
    Process a single chunk with contextual embedding.
    This function is designed to be used with concurrent.futures.
    
    Args:
        args: Tuple containing (url, content, full_document)
        
    Returns:
        Tuple containing:
        - The contextual text that situates the chunk within the document
        - Boolean indicating if contextual embedding was performed
    """
    url, content, full_document = args
    return generate_contextual_embedding(full_document, content)

def add_documents_to_supabase(
    client: Client, 
    urls: List[str], 
    chunk_numbers: List[int],
    contents: List[str], 
    metadatas: List[Dict[str, Any]],
    url_to_full_document: Dict[str, str],
    batch_size: int = 20
) -> None:
    """
    Add documents to the Supabase crawled_pages table in batches.
    Deletes existing records with the same URLs before inserting to prevent duplicates.
    
    Args:
        client: Supabase client
        urls: List of URLs
        chunk_numbers: List of chunk numbers
        contents: List of document contents
        metadatas: List of document metadata
        url_to_full_document: Dictionary mapping URLs to their full document content
        batch_size: Size of each batch for insertion
    """
    unique_urls = list(set(urls))
    
    try:
        if unique_urls:
            client.table("crawled_pages").delete().in_("url", unique_urls).execute()
    except Exception as e:
        print(f"Batch delete failed: {e}. Trying one-by-one deletion as fallback.")
        for url in unique_urls:
            try:
                client.table("crawled_pages").delete().eq("url", url).execute()
            except Exception as inner_e:
                print(f"Error deleting record for URL {url}: {inner_e}")
    
    use_contextual_embeddings = os.getenv("USE_CONTEXTUAL_EMBEDDINGS", "false") == "true"
    print(f"\n\nUse contextual embeddings: {use_contextual_embeddings}\n\n")
    
    for i in range(0, len(contents), batch_size):
        batch_end = min(i + batch_size, len(contents))
        
        batch_urls = urls[i:batch_end]
        batch_chunk_numbers = chunk_numbers[i:batch_end]
        batch_contents = contents[i:batch_end]
        batch_metadatas = metadatas[i:batch_end]
        
        if use_contextual_embeddings:
            process_args = []
            for j, content in enumerate(batch_contents):
                url = batch_urls[j]
                full_document = url_to_full_document.get(url, "")
                process_args.append((url, content, full_document))
            
            contextual_contents = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                future_to_idx = {executor.submit(process_chunk_with_context, arg): idx 
                                for idx, arg in enumerate(process_args)}
                
                for future in concurrent.futures.as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    try:
                        result, success = future.result()
                        contextual_contents.append(result)
                        if success:
                            batch_metadatas[idx]["contextual_embedding"] = True
                    except Exception as e:
                        print(f"Error processing chunk {idx}: {e}")
                        contextual_contents.append(batch_contents[idx])
            
            if len(contextual_contents) != len(batch_contents):
                print(f"Warning: Expected {len(batch_contents)} results but got {len(contextual_contents)}")
                contextual_contents = batch_contents
        else:
            contextual_contents = batch_contents
        
        batch_embeddings = create_embeddings_batch(contextual_contents)
        
        batch_data = []
        for j in range(len(contextual_contents)):
            chunk_size = len(contextual_contents[j])
            
            data = {
                "url": batch_urls[j],
                "chunk_number": batch_chunk_numbers[j],
                "content": contextual_contents[j],
                "metadata": {
                    "chunk_size": chunk_size,
                    **batch_metadatas[j]
                },
                "source_id": batch_metadatas[j]["source"],
                "embedding": batch_embeddings[j]
            }
            
            batch_data.append(data)
        
        max_retries = 3
        retry_delay = 1.0
        
        for retry in range(max_retries):
            try:
                client.table("crawled_pages").insert(batch_data).execute()
                break
            except Exception as e:
                if retry < max_retries - 1:
                    print(f"Error inserting batch into Supabase (attempt {retry + 1}/{max_retries}): {e}")
                    print(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    print(f"Failed to insert batch after {max_retries} attempts: {e}")
                    print("Attempting to insert records individually...")
                    successful_inserts = 0
                    for record in batch_data:
                        try:
                            client.table("crawled_pages").insert(record).execute()
                            successful_inserts += 1
                        except Exception as individual_error:
                            print(f"Failed to insert individual record for URL {record['url']}: {individual_error}")
                    
                    if successful_inserts > 0:
                        print(f"Successfully inserted {successful_inserts}/{len(batch_data)} records individually")

def search_documents(
    client: Client, 
    query: str, 
    match_count: int = 10, 
    filter_metadata: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Search for documents in Supabase using vector similarity.
    
    Args:
        client: Supabase client
        query: Query text
        match_count: Maximum number of results to return
        filter_metadata: Optional metadata filter
        
    Returns:
        List of matching documents
    """
    query_embedding = create_embedding(query)
    
    try:
        params = {
            'query_embedding': query_embedding,
            'match_count': match_count
        }
        
        if filter_metadata:
            params['filter'] = filter_metadata
        
        result = client.rpc('match_crawled_pages', params).execute()
        
        return result.data
    except Exception as e:
        print(f"Error searching documents: {e}")
        return []


def extract_code_blocks(markdown_content: str, min_length: int = 1000) -> List[Dict[str, Any]]:
    """
    Extract code blocks from markdown content along with context.
    
    Args:
        markdown_content: The markdown content to extract code blocks from
        min_length: Minimum length of code blocks to extract (default: 1000 characters)
        
    Returns:
        List of dictionaries containing code blocks and their context
    """
    code_blocks = []
    
    content = markdown_content.strip()
    start_offset = 0
    if content.startswith('```'):
        start_offset = 3
        print("Skipping initial triple backticks")
    
    backtick_positions = []
    pos = start_offset
    while True:
        pos = markdown_content.find('```', pos)
        if pos == -1:
            break
        backtick_positions.append(pos)
        pos += 3
    
    i = 0
    while i < len(backtick_positions) - 1:
        start_pos = backtick_positions[i]
        end_pos = backtick_positions[i + 1]
        
        code_section = markdown_content[start_pos+3:end_pos]
        
        lines = code_section.split('\n', 1)
        if len(lines) > 1:
            first_line = lines[0].strip()
            if first_line and not ' ' in first_line and len(first_line) < 20:
                language = first_line
                code_content = lines[1].strip() if len(lines) > 1 else ""
            else:
                language = ""
                code_content = code_section.strip()
        else:
            language = ""
            code_content = code_section.strip()
        
        if len(code_content) < min_length:
            i += 2
            continue
        
        context_start = max(0, start_pos - 1000)
        context_before = markdown_content[context_start:start_pos].strip()
        
        context_end = min(len(markdown_content), end_pos + 3 + 1000)
        context_after = markdown_content[end_pos + 3:context_end].strip()
        
        code_blocks.append({
            'code': code_content,
            'language': language,
            'context_before': context_before,
            'context_after': context_after,
            'full_context': f"{context_before}\n\n{code_content}\n\n{context_after}"
        })
        
        i += 2
    
    return code_blocks


@retry_with_exponential_backoff
def generate_code_example_summary(code: str, context_before: str, context_after: str) -> str:
    """
    Generate a summary for a code example using its surrounding context.
    
    Args:
        code: The code example
        context_before: Context before the code
        context_after: Context after the code
        
    Returns:
        A summary of what the code example demonstrates
    """
    model_choice = os.getenv("MODEL_CHOICE")
    
    prompt = f"""<context_before>
{context_before[-500:] if len(context_before) > 500 else context_before}
</context_before>

<code_example>
{code[:MAX_TOKENS_PER_REQUEST]}
</code_example>

<context_after>
{context_after[:500] if len(context_after) > 500 else context_after}
</context_after>

Based on the code example and its surrounding context, provide a concise summary (2-3 sentences) that describes what this code example demonstrates and its purpose. Focus on the practical application and key concepts illustrated.
"""
    
    try:
        response = openai.chat.completions.create(
            model=model_choice,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that provides concise code example summaries."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=100
        )
        
        return response.choices[0].message.content.strip()
    
    except Exception as e:
        print(f"Error generating code example summary: {e}")
        return "Code example for demonstration purposes."


def add_code_examples_to_supabase(
    client: Client,
    urls: List[str],
    chunk_numbers: List[int],
    code_examples: List[str],
    summaries: List[str],
    metadatas: List[Dict[str, Any]],
    batch_size: int = 20
):
    """
    Add code examples to the Supabase code_examples table in batches.
    
    Args:
        client: Supabase client
        urls: List of URLs
        chunk_numbers: List of chunk numbers
        code_examples: List of code example contents
        summaries: List of code example summaries
        metadatas: List of metadata dictionaries
        batch_size: Size of each batch for insertion
    """
    if not urls:
        return
        
    unique_urls = list(set(urls))
    for url in unique_urls:
        try:
            client.table('code_examples').delete().eq('url', url).execute()
        except Exception as e:
            print(f"Error deleting existing code examples for {url}: {e}")
    
    total_items = len(urls)
    for i in range(0, total_items, batch_size):
        batch_end = min(i + batch_size, total_items)
        batch_texts = []
        
        for j in range(i, batch_end):
            combined_text = f"{code_examples[j]}\n\nSummary: {summaries[j]}"
            batch_texts.append(combined_text)
        
        embeddings = create_embeddings_batch(batch_texts)
        
        valid_embeddings = []
        for embedding in embeddings:
            if embedding and not all(v == 0.0 for v in embedding):
                valid_embeddings.append(embedding)
            else:
                print(f"Warning: Zero or invalid embedding detected, creating new one...")
                single_embedding = create_embedding(batch_texts[len(valid_embeddings)])
                valid_embeddings.append(single_embedding)
        
        batch_data = []
        for j, embedding in enumerate(valid_embeddings):
            idx = i + j
            
            parsed_url = urlparse(urls[idx])
            source_id = parsed_url.netloc or parsed_url.path
            
            batch_data.append({
                'url': urls[idx],
                'chunk_number': chunk_numbers[idx],
                'content': code_examples[idx],
                'summary': summaries[idx],
                'metadata': metadatas[idx],
                'source_id': source_id,
                'embedding': embedding
            })
        
        max_retries = 3
        retry_delay = 1.0
        
        for retry in range(max_retries):
            try:
                client.table('code_examples').insert(batch_data).execute()
                break
            except Exception as e:
                if retry < max_retries - 1:
                    print(f"Error inserting batch into Supabase (attempt {retry + 1}/{max_retries}): {e}")
                    print(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    print(f"Failed to insert batch after {max_retries} attempts: {e}")
                    print("Attempting to insert records individually...")
                    successful_inserts = 0
                    for record in batch_data:
                        try:
                            client.table('code_examples').insert(record).execute()
                            successful_inserts += 1
                        except Exception as individual_error:
                            print(f"Failed to insert individual record for URL {record['url']}: {individual_error}")
                    
                    if successful_inserts > 0:
                        print(f"Successfully inserted {successful_inserts}/{len(batch_data)} records individually")

        print(f"Batch {i//batch_size + 1} processed. Pausing for 1 second...")
        time.sleep(1.0)


def update_source_info(client: Client, source_id: str, summary: str, word_count: int):
    """
    Update or insert source information in the sources table.
    
    Args:
        client: Supabase client
        source_id: The source ID (domain)
        summary: Summary of the source
        word_count: Total word count for the source
    """
    try:
        result = client.table('sources').update({
            'summary': summary,
            'total_word_count': word_count,
            'updated_at': 'now()'
        }).eq('source_id', source_id).execute()
        
        if not result.data:
            client.table('sources').insert({
                'source_id': source_id,
                'summary': summary,
                'total_word_count': word_count
            }).execute()
            print(f"Created new source: {source_id}")
        else:
            print(f"Updated source: {source_id}")
            
    except Exception as e:
        print(f"Error updating source {source_id}: {e}")


@retry_with_exponential_backoff
def extract_source_summary(source_id: str, content: str, max_length: int = 500) -> str:
    """
    Extract a summary for a source from its content using an LLM.
    
    This function uses the OpenAI API to generate a concise summary of the source content.
    
    Args:
        source_id: The source ID (domain)
        content: The content to extract a summary from
        max_length: Maximum length of the summary
        
    Returns:
        A summary string
    """
    default_summary = f"Content from {source_id}"
    
    if not content or len(content.strip()) == 0:
        return default_summary
    
    model_choice = os.getenv("MODEL_CHOICE")
    
    truncated_content = content[:MAX_TOKENS_PER_REQUEST]
    
    prompt = f"""<source_content>
{truncated_content}
</source_content>

The above content is from the documentation for '{source_id}'. Please provide a concise summary (3-5 sentences) that describes what this library/tool/framework is about. The summary should help understand what the library/tool/framework accomplishes and the purpose.
"""
    
    try:
        response = openai.chat.completions.create(
            model=model_choice,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that provides concise library/tool/framework summaries."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=150
        )
        
        summary = response.choices[0].message.content.strip()
        
        if len(summary) > max_length:
            summary = summary[:max_length] + "..."
            
        return summary
    
    except Exception as e:
        print(f"Error generating summary with LLM for {source_id}: {e}. Using default summary.")
        return default_summary


def search_code_examples(
    client: Client, 
    query: str, 
    match_count: int = 10, 
    filter_metadata: Optional[Dict[str, Any]] = None,
    source_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Search for code examples in Supabase using vector similarity.
    
    Args:
        client: Supabase client
        query: Query text
        match_count: Maximum number of results to return
        filter_metadata: Optional metadata filter
        source_id: Optional source ID to filter results
        
    Returns:
        List of matching code examples
    """
    enhanced_query = f"Code example for {query}\n\nSummary: Example code showing {query}"
    
    query_embedding = create_embedding(enhanced_query)
    
    try:
        params = {
            'query_embedding': query_embedding,
            'match_count': match_count
        }
        
        if filter_metadata:
            params['filter'] = filter_metadata
            
        if source_id:
            params['source_filter'] = source_id
        
        result = client.rpc('match_code_examples', params).execute()
        
        return result.data
    except Exception as e:
        print(f"Error searching code examples: {e}")
        return []
