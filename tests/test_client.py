
import asyncio
import aiohttp
import json

async def main():
    """
    A simple MCP client to test the running server.
    """
    url = "http://localhost:8051"
    tool_call = {
        "tool_name": "get_available_sources",
        "parameters": {}
    }

    print(f"Connecting to MCP server at {url}")
    print(f"Executing tool: {tool_call['tool_name']}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{url}/v1/tool/execute",
                json=tool_call,
                headers={"Accept": "text/event-stream"}
            ) as response:
                if response.status == 200:
                    print("Successfully connected. Waiting for response...")
                    async for line in response.content:
                        line = line.decode('utf-8').strip()
                        if line.startswith('data:'):
                            data = line[5:].strip()
                            print(f"Received data: {data}")
                else:
                    print(f"Error: Server returned status {response.status}")
                    print(await response.text())

    except aiohttp.ClientConnectorError as e:
        print(f"Connection Error: {e}")
        print("Please ensure the Docker container is running and port 8051 is mapped.")

if __name__ == "__main__":
    asyncio.run(main())
