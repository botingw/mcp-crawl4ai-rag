# math_server.py
#from mcp.server.fastmcp import FastMCP
from contextlib import asynccontextmanager
import asyncio

# from mcp.server.fastmcp import FastMCP, Context
from fastmcp import FastMCP, Context
from sentence_transformers import CrossEncoder
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse, urldefrag
from xml.etree import ElementTree
from dotenv import load_dotenv
from supabase import Client
from pathlib import Path
import requests
import asyncio
import json
import os
import re
import concurrent.futures
import sys
# debug v2_2 remove all crawler
#from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode, MemoryAdaptiveDispatcher

# Load environment variables from the project root .env file
project_root = Path(__file__).resolve().parent.parent
dotenv_path = project_root / '.env'

# Force override of existing environment variables
load_dotenv(dotenv_path, override=True)

mcp = FastMCP(
    "Math",
    host=os.getenv("HOST", "0.0.0.0"),
    port=os.getenv("PORT", "8051"),
)

@asynccontextmanager
async def server_lifespan(server: FastMCP):
    """A no-op async context manager for demonstration."""
    # >>>>>>>> ADD THIS LINE FOR TESTING <<<<<<<<
    #
    print("LIFESPAN: Entering lifespan, sleeping for 10 seconds...", file=sys.stderr)
    import time
    time.sleep(10) # debug donker network race
    await asyncio.sleep(0.1) # Using a blocking sleep for this test is okay. debug AI assistant, FastMCP race
    print("LIFESPAN: Woke up from sleep.", file=sys.stderr)
    #
    # >>>>>>>>>>>>>>> END OF TEST CODE <<<<<<<<<<<<<<<

    # setup code could go here
    var = 5
    try:
        yield var
    finally:
        # teardown code could go here
        pass

@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b

@mcp.tool()
def multiply(a: int, b: int) -> int:
    """Multiply two numbers"""
    return a * b

if __name__ == "__main__":
    transport = os.getenv("TRANSPORT", "stdio")
    if transport == 'sse':
        mcp.run(transport="sse")
    elif transport == 'stdio':
        mcp.run(transport="stdio")
    elif transport == 'http':
        mcp.run(transport="http")
    else:
        print(f"Unknown transport: {transport}", file=sys.stderr)