import asyncio
import json
import os
from pathlib import Path
import sys
import pytest

# Ensure the mcp library and project source are in the path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Define the command to start the server
SERVER_COMMAND = "/Users/wangbo-ting/git/langgraph-dev-navigator/mcp-crawl4ai-rag/start_mcp_server.sh"

@pytest.mark.asyncio
async def test_stdio_integration():
    """
    Tests the stdio integration with the MCP server, covering liveness, Supabase, and Neo4j tools.
    """
    print(f"--- Running Full stdio Integration Test ---")
    print(f"Starting MCP server with command: {SERVER_COMMAND}")

    # server_params = StdioServerParameters(
    #     command="uv",
    #     args=["run", "src/crawl4ai_mcp.py"],
    #     env={**os.environ, "TRANSPORT": "stdio"}
    # )
    server_params = StdioServerParameters(command=SERVER_COMMAND)

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                print("✓ MCP client connected successfully.")

                # 1. Test a tool that uses Supabase
                tool_name_supabase = "get_available_sources"
                parameters_supabase = {}
                print(f"Executing tool: {tool_name_supabase}")

                result_supabase = await session.execute_tool(tool=tool_name_supabase, arguments=parameters_supabase)
                print(f"Received response for {tool_name_supabase}: {result_supabase}")

                # Validate the Supabase response
                assert result_supabase is not None, "Did not receive a response from the server for Supabase test."
                response_json_supabase = json.loads(result_supabase)
                assert response_json_supabase.get("success") is True, "The 'success' field is not True for Supabase test."
                assert "sources" in response_json_supabase, "Response JSON does not contain 'sources' key for Supabase test."
                assert isinstance(response_json_supabase["sources"], list), "'sources' field is not a list for Supabase test."
                print("✓ Supabase tool test passed.")

                # 2. Test a tool that uses Neo4j
                if not os.getenv("NEO4J_URI"):
                    print("NEO4J_URI not set, skipping Neo4j tool test.")
                else:
                    tool_name_neo4j = "query_knowledge_graph"
                    parameters_neo4j = {"command": "repos"}
                    print(f"Executing tool: {tool_name_neo4j} with parameters: {parameters_neo4j}")

                    result_neo4j = await session.execute_tool(tool=tool_name_neo4j, arguments=parameters_neo4j)
                    print(f"Received response for {tool_name_neo4j}: {result_neo4j}")

                    # Validate the Neo4j response
                    assert result_neo4j is not None, "Did not receive a response from the server for Neo4j test."
                    response_json_neo4j = json.loads(result_neo4j)
                    assert response_json_neo4j.get("success") is True, "The 'success' field is not True for Neo4j test."
                    assert "data" in response_json_neo4j, "Response JSON does not contain 'data' key for Neo4j test."
                    assert "repositories" in response_json_neo4j["data"], "Response data does not contain 'repositories' key for Neo4j test."
                    assert isinstance(response_json_neo4j["data"]["repositories"], list), "'repositories' field is not a list for Neo4j test."
                    print("✓ Neo4j tool test passed.")

    except Exception as e:
        pytest.fail(f"An error occurred during the stdio integration test: {e}")