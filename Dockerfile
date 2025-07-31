FROM python:3.12-slim

ARG PORT=8051

WORKDIR /app

RUN apt-get update && apt-get install -y git

# Install uv
RUN pip install --no-cache-dir uv

# Create the venv with uv (explicit path is clearer)
RUN uv venv /app/.venv

# Make that venv the default for all subsequent commands
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy the MCP server files
COPY . .

# Install deps into the venv with uv (no --system)
RUN df -h && df -i
RUN uv pip install --no-cache-dir -e .

# Any project-specific setup
RUN crawl4ai-setup

RUN playwright install chromium

EXPOSE ${PORT}
CMD ["python", "-u", "test_docker_io.py"]

