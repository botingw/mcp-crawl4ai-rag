

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
import tiktoken
from .stats_collector import stats_collector
from .config import INITIAL_DELAY, EXPONENTIAL_BASE, JITTER, MAX_RETRIES, MAX_WORKERS, MAX_TOKENS_PER_REQUEST, TPM_LIMIT
import threading

def num_tokens_from_string(string: str, model_name: str) -> int:
    """
    Returns the number of tokens in a text string.
    """
    ENCODING_MAP = {
        "gpt-4": "cl100k_base",
        "gpt-3.5-turbo": "cl100k_base",
        "text-embedding-ada-002": "cl100k_base",
    }
    try:
        encoding_name = ENCODING_MAP.get(model_name) or tiktoken.encoding_for_model(model_name).name
    except KeyError:
        encoding_name = "cl100k_base"
    encoding = tiktoken.get_encoding(encoding_name)
    return len(encoding.encode(string))

class TokenBucketRateLimiter:
    """
    A thread-safe token bucket rate limiter for proactive throttling.
    """
    def __init__(self, capacity, refill_time_seconds):
        """
        Initializes the token bucket.
        
        :param capacity: The total number of tokens the bucket can hold (e.g., your TPM limit).
        :param refill_time_seconds: The time in seconds for the bucket to refill completely (e.g., 60).
        """
        self.capacity = float(capacity)
        self._tokens = float(capacity)
        self.refill_rate = capacity / refill_time_seconds
        self.last_refill_time = time.monotonic()
        self.lock = threading.Lock()

    def _refill(self):
        """Refills the bucket with tokens based on elapsed time. This is an internal method."""
        now = time.monotonic()
        time_passed = now - self.last_refill_time
        new_tokens = time_passed * self.refill_rate
        self._tokens = min(self.capacity, self._tokens + new_tokens)
        self.last_refill_time = now

    def acquire(self, tokens_needed):
        """
        Acquires a specified number of tokens, waiting if necessary.
        This is the main method to call before an API request.
        """
        if tokens_needed > self.capacity:
            raise ValueError("Requested tokens exceed the bucket's total capacity.")
        with self.lock:
            self._refill()
            if tokens_needed > self._tokens:
                required_additional_tokens = tokens_needed - self._tokens
                wait_time = required_additional_tokens / self.refill_rate
                print(f"[THROTTLER]: Not enough tokens. Need {tokens_needed:.0f}, have {self._tokens:.0f}. Proactively waiting for {wait_time:.2f} seconds.")
                time.sleep(wait_time)
                self._refill()
            self._tokens -= tokens_needed

rate_limiter = TokenBucketRateLimiter(TPM_LIMIT, 60)

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
def generate_contextual_embedding(full_document: str, chunk: str, source_file: str, chunk_index: int) -> Tuple[str, bool]:
    """
    Generate contextual information for a chunk within a document to improve retrieval.
    
    Args:
        full_document: The complete document text
        chunk: The specific chunk of text to generate context for
        source_file: The source file of the chunk
        chunk_index: The index of the chunk
        
    Returns:
        Tuple containing:
        - The contextual text that situates the chunk within the document
        - Boolean indicating if contextual embedding was performed
    """
    model_choice = os.getenv("MODEL_CHOICE")
    
    prompt = f"""<document> 
{full_document[:MAX_TOKENS_PER_REQUEST]} 
</document>
Here is the chunk we want to situate within the whole document 
<chunk> 
{chunk}
</chunk> 
Please give a short succinct context to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk. Answer only with the succinct context and nothing else."""

    prompt_tokens = num_tokens_from_string(prompt, model_choice)
    raw_chunk_tokens=num_tokens_from_string(chunk, model_choice)
    # stats_collector.log_raw_chunk(source_file, chunk_index, raw_chunk_tokens)

    try:
        rate_limiter.acquire(prompt_tokens + 200) # Estimate 200 output tokens

        response = openai.chat.completions.create(
            model=model_choice,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that provides concise contextual information."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=200
        )
        
        completion_tokens = response.usage.completion_tokens
        total_tokens = response.usage.total_tokens
        
        stats_collector.log_chunk_api_call(
            source_file=source_file,
            chunk_index=chunk_index,
            raw_chunk_tokens=raw_chunk_tokens,
            call_type="contextual_embedding",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            status="Success"
        )
        
        context = response.choices[0].message.content.strip()
        contextual_text = f"{context}\n---\n{chunk}"
        
        return contextual_text, True
    
    except Exception as e:
        stats_collector.log_chunk_api_call(
            source_file=source_file,
            chunk_index=chunk_index,
            raw_chunk_tokens=raw_chunk_tokens,
            call_type="contextual_embedding",
            prompt_tokens=prompt_tokens,
            completion_tokens=0,
            total_tokens=prompt_tokens,
            status="Fail",
            error_details=str(e)
        )
        print(f"Error generating contextual embedding: {e}. Using original chunk instead.")
        return chunk, False

def process_chunk_with_context(args):
    """
    Process a single chunk with contextual embedding.
    This function is designed to be used with concurrent.futures.
    
    Args:
        args: Tuple containing (url, content, full_document, chunk_index)
        
    Returns:
        Tuple containing:
        - The contextual text that situates the chunk within the document
        - Boolean indicating if contextual embedding was performed
    """
    url, content, full_document, chunk_index = args
    return generate_contextual_embedding(full_document, content, url, chunk_index)

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
    # Get unique URLs to delete existing records
    unique_urls = list(set(urls))
    
    # Delete existing records for these URLs in a single operation
    try:
        if unique_urls:
            # Use the .in_() filter to delete all records with matching URLs
            client.table("crawled_pages").delete().in_("url", unique_urls).execute()
    except Exception as e:
        print(f"Batch delete failed: {e}. Trying one-by-one deletion as fallback.")
        # Fallback: delete records one by one
        for url in unique_urls:
            try:
                client.table("crawled_pages").delete().eq("url", url).execute()
            except Exception as inner_e:
                print(f"Error deleting record for URL {url}: {inner_e}")
                # Continue with the next URL even if one fails
    
    # Check if MODEL_CHOICE is set for contextual embeddings
    use_contextual_embeddings = os.getenv("USE_CONTEXTUAL_EMBEDDINGS", "false") == "true"
    print(f"\n\nUse contextual embeddings: {use_contextual_embeddings}\n\n")
    
    # Process in batches to avoid memory issues
    for i in range(0, len(contents), batch_size):
        batch_end = min(i + batch_size, len(contents))
        
        # Get batch slices
        batch_urls = urls[i:batch_end]
        batch_chunk_numbers = chunk_numbers[i:batch_end]
        batch_contents = contents[i:batch_end]
        batch_metadatas = metadatas[i:batch_end]
        
        # Apply contextual embedding to each chunk if MODEL_CHOICE is set
        if use_contextual_embeddings:
            # Prepare arguments for parallel processing
            process_args = []
            for j, content in enumerate(batch_contents):
                url = batch_urls[j]
                chunk_index = batch_chunk_numbers[j]
                full_document = url_to_full_document.get(url, "")
                process_args.append((url, content, full_document, chunk_index))
            
            # Process in parallel using ThreadPoolExecutor
            contextual_contents = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                # Submit all tasks and collect results
                future_to_idx = {executor.submit(process_chunk_with_context, arg): idx 
                                for idx, arg in enumerate(process_args)}
                
                # Process results as they complete
                for future in concurrent.futures.as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    try:
                        result, success = future.result()
                        contextual_contents.append(result)
                        if success:
                            batch_metadatas[idx]["contextual_embedding"] = True
                    except Exception as e:
                        print(f"Error processing chunk {idx}: {e}")
                        # Use original content as fallback
                        contextual_contents.append(batch_contents[idx])
            
            # Sort results back into original order if needed
            if len(contextual_contents) != len(batch_contents):
                print(f"Warning: Expected {len(batch_contents)} results but got {len(contextual_contents)}")
                # Use original contents as fallback
                contextual_contents = batch_contents
        else:
            # If not using contextual embeddings, use original contents
            contextual_contents = batch_contents
        
        # Create embeddings for the entire batch at once
        batch_embeddings = create_embeddings_batch(contextual_contents)
        
        batch_data = []
        for j in range(len(contextual_contents)):
            # Extract metadata fields
            chunk_size = len(contextual_contents[j])
            
            # Prepare data for insertion
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
        
        # Insert batch into Supabase with retry logic
        max_retries = 3
        retry_delay = 1.0
        
        for retry in range(max_retries):
            try:
                client.table("crawled_pages").insert(batch_data).execute()
                # Success - break out of retry loop
                break
            except Exception as e:
                if retry < max_retries - 1:
                    print(f"Error inserting batch into Supabase (attempt {retry + 1}/{max_retries}): {e}")
                    print(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    # Final attempt failed
                    print(f"Failed to insert batch after {max_retries} attempts: {e}")
                    # Optionally, try inserting records one by one as a last resort
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
    # Create embedding for the query
    query_embedding = create_embedding(query)
    
    # Execute the search using the match_crawled_pages function
    try:
        # Only include filter parameter if filter_metadata is provided and not empty
        params = {
            'query_embedding': query_embedding,
            'match_count': match_count
        }
        
        # Only add the filter if it's actually provided and not empty
        if filter_metadata:
            params['filter'] = filter_metadata
        
        result = client.rpc('match_crawled_pages', params).execute()
        
        return result.data
    except Exception as e:
        print(f"Error searching documents: {e}")
        return []


from markdown_it import MarkdownIt

def extract_code_blocks(markdown_content: str, min_code_words: int = 20) -> List[Dict[str, Any]]:
    """
    Parses a markdown document and extracts code blocks along with their
    full preceding and succeeding text blocks for RAG enrichment.

    Args:
        markdown_content: The markdown string to parse.

    Returns:
        A list of dictionaries, where each dict contains a code block
        and its full textual context.
    """
    md = MarkdownIt()
    tokens = md.parse(markdown_content)

    # Step 1: Create a simplified, sequential representation of the document
    structured_blocks = []
    current_text = ""
    for token in tokens:
        if token.type == 'fence':
            # If there's pending text, save it before the code block
            if current_text.strip():
                structured_blocks.append({'type': 'text', 'content': current_text.strip()})
                current_text = ""
            
            # Add the code block
            language = (token.info or "").split()[0] if token.info else None
            structured_blocks.append({
                'type': 'code', 
                'content': token.content, 
                'language': language
            })
        elif token.content:
            # Accumulate text from various other tokens
            current_text += token.content
    
    # Add any final text block at the end
    if current_text.strip():
        structured_blocks.append({'type': 'text', 'content': current_text.strip()})

    # Step 2: Iterate through the structured blocks to find context for each code block
    enriched_code_blocks = []
    for i, block in enumerate(structured_blocks):
        if block['type'] == 'code':
            # filter code blocks with the words
            code_words = len(block['content'].split(' '))
            if code_words < min_code_words:
                continue
            context_before = ""
            # Look at the previous block if it exists and is text
            if i > 0 and structured_blocks[i-1]['type'] == 'text':
                context_before = structured_blocks[i-1]['content']

            context_after = ""
            # Look at the next block if it exists and is text
            if i < len(structured_blocks) - 1 and structured_blocks[i+1]['type'] == 'text':
                context_after = structured_blocks[i+1]['content']
            
            enriched_code_blocks.append({
                'code': block['content'],
                'language': block['language'],
                'context_before': context_before,
                'context_after': context_after
            })
            
    return enriched_code_blocks



@retry_with_exponential_backoff
def generate_code_example_summary(code: str, context_before: str, context_after: str, source_file: str, chunk_index: int) -> str:
    """
    Generate a summary for a code example using its surrounding context.
    
    Args:
        code: The code example
        context_before: Context before the code
        context_after: Context after the code
        source_file: The source file of the code example
        chunk_index: The index of the chunk containing the code example
        
    Returns:
        A summary of what the code example demonstrates
    """
    model_choice = os.getenv("MODEL_CHOICE")
    
    # Create the prompt
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
    
    prompt_tokens = num_tokens_from_string(prompt, model_choice)
    # stats_collector.log_raw_chunk(source_file, chunk_index, num_tokens_from_string(code, model_choice))

    try:
        rate_limiter.acquire(prompt_tokens + 100) # Estimate 100 output tokens

        response = openai.chat.completions.create(
            model=model_choice,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that provides concise code example summaries."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=100
        )
        
        completion_tokens = response.usage.completion_tokens
        total_tokens = response.usage.total_tokens

        stats_collector.log_code_block_api_call(
            source_file=source_file,
            code_block_index=chunk_index,
            raw_code_tokens=num_tokens_from_string(code, model_choice),
            call_type="code_example_summary",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            status="Success"
        )
        
        return response.choices[0].message.content.strip()
    
    except Exception as e:
        stats_collector.log_code_block_api_call(
            source_file=source_file,
            code_block_index=chunk_index,
            raw_code_tokens=num_tokens_from_string(code, model_choice),
            call_type="code_example_summary",
            prompt_tokens=prompt_tokens,
            completion_tokens=0,
            total_tokens=prompt_tokens,
            status="Fail",
            error_details=str(e)
        )
        print(f"Error generating code example summary: {e}")
        return "Code example for demonstration purposes."


def process_code_example(args):
    """
    Process a single code example to generate its summary.
    This function is designed to be used with concurrent.futures.
    
    Args:
        args: Tuple containing (code, context_before, context_after)
        
    Returns:
        The generated summary
    """
    code, context_before, context_after, source_file, chunk_index = args
    return generate_code_example_summary(code, context_before, context_after, source_file, chunk_index)


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
        
    # Delete existing records for these URLs
    unique_urls = list(set(urls))
    for url in unique_urls:
        try:
            client.table('code_examples').delete().eq('url', url).execute()
        except Exception as e:
            print(f"Error deleting existing code examples for {url}: {e}")
    
    # Process in batches
    total_items = len(urls)
    for i in range(0, total_items, batch_size):
        batch_end = min(i + batch_size, total_items)
        batch_texts = []
        
        # Create combined texts for embedding (code + summary)
        for j in range(i, batch_end):
            combined_text = f"{code_examples[j]}\n\nSummary: {summaries[j]}"
            batch_texts.append(combined_text)
        
        # Create embeddings for the batch
        embeddings = create_embeddings_batch(batch_texts)
        
        # Check if embeddings are valid (not all zeros)
        valid_embeddings = []
        for embedding in embeddings:
            if embedding and not all(v == 0.0 for v in embedding):
                valid_embeddings.append(embedding)
            else:
                print(f"Warning: Zero or invalid embedding detected, creating new one...")
                # Try to create a single embedding as fallback
                single_embedding = create_embedding(batch_texts[len(valid_embeddings)])
                valid_embeddings.append(single_embedding)
        
        # Prepare batch data
        batch_data = []
        for j, embedding in enumerate(valid_embeddings):
            idx = i + j
            
            # Extract source_id from URL
            parsed_url = urlparse(urls[idx])
            # source_id = parsed_url.netloc or parsed_url.path # this is not robust, should always get source_id from metadata?
            source_id = metadatas[idx]["source"]
            
            batch_data.append({
                'url': urls[idx],
                'chunk_number': chunk_numbers[idx],
                'content': code_examples[idx],
                'summary': summaries[idx],
                'metadata': metadatas[idx],
                'source_id': source_id,
                'embedding': embedding
            })
        
        # Insert batch into Supabase with retry logic
        max_retries = 3
        retry_delay = 1.0
        
        for retry in range(max_retries):
            try:
                client.table('code_examples').insert(batch_data).execute()
                # Success - break out of retry loop
                break
            except Exception as e:
                if retry < max_retries - 1:
                    print(f"Error inserting batch into Supabase (attempt {retry + 1}/{max_retries}): {e}")
                    print(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    # Final attempt failed
                    print(f"Failed to insert batch after {max_retries} attempts: {e}")
                    # Optionally, try inserting records one by one as a last resort
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
        # Try to update existing source
        result = client.table('sources').update({
            'summary': summary,
            'total_word_count': word_count,
            'updated_at': 'now()'
        }).eq('source_id', source_id).execute()
        
        # If no rows were updated, insert new source
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
    # Default summary if we can't extract anything meaningful
    default_summary = f"Content from {source_id}"
    
    if not content or len(content.strip()) == 0:
        return default_summary
    
    # Get the model choice from environment variables
    model_choice = os.getenv("MODEL_CHOICE")
    
    # Limit content length to avoid token limits
    truncated_content = content[:MAX_TOKENS_PER_REQUEST]
    
    # Create the prompt for generating the summary
    prompt = f"""<source_content>
{truncated_content}
</source_content>

The above content is from the documentation for '{source_id}'. Please provide a concise summary (3-5 sentences) that describes what this library/tool/framework is about. The summary should help understand what the library/tool/framework accomplishes and the purpose.
"""
    
    prompt_tokens = num_tokens_from_string(prompt, model_choice)
    raw_doc_tokens = num_tokens_from_string(content, model_choice)

    try:
        # Call the OpenAI API to generate the summary
        response = openai.chat.completions.create(
            model=model_choice,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that provides concise library/tool/framework summaries."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=150
        )
        
        completion_tokens = response.usage.completion_tokens
        total_tokens = response.usage.total_tokens

        stats_collector.log_source_api_call(
            source_id=source_id,
            raw_doc_tokens=raw_doc_tokens,
            call_type="source_summary",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            status="Success"
        )

        # Extract the generated summary
        summary = response.choices[0].message.content.strip()
        
        # Ensure the summary is not too long
        if len(summary) > max_length:
            summary = summary[:max_length] + "..."
            
        return summary
    
    except Exception as e:
        stats_collector.log_source_api_call(
            source_id=source_id,
            raw_doc_tokens=raw_doc_tokens,
            call_type="source_summary",
            prompt_tokens=prompt_tokens,
            completion_tokens=0,
            total_tokens=prompt_tokens,
            status="Fail",
            error_details=str(e)
        )
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
    # Create a more descriptive query for better embedding match
    # Since code examples are embedded with their summaries, we should make the query more descriptive
    enhanced_query = f"Code example for {query}\n\nSummary: Example code showing {query}"
    
    # Create embedding for the enhanced query
    query_embedding = create_embedding(enhanced_query)
    
    # Execute the search using the match_code_examples function
    try:
        # Only include filter parameter if filter_metadata is provided and not empty
        params = {
            'query_embedding': query_embedding,
            'match_count': match_count
        }
        
        # Only add the filter if it's actually provided and not empty
        if filter_metadata:
            params['filter'] = filter_metadata
            
        # Add source filter if provided
        if source_id:
            params['source_filter'] = source_id
        
        result = client.rpc('match_code_examples', params).execute()
        
        return result.data
    except Exception as e:
        print(f"Error searching code examples: {e}")
        return []
