# Copyright (c) 2025 Boting Wang
# Copyright (c) 2025 Cole Medin
#
# SPDX-License-Identifier: MIT

# Exponential backoff configuration
INITIAL_DELAY = 30
EXPONENTIAL_BASE = 4
JITTER = True
MAX_RETRIES = 10

# Concurrency and Rate Limiting Configuration
MAX_WORKERS = 10  # Max concurrent threads/processes for API calls
MAX_TOKENS_PER_REQUEST = 4000  # Max tokens to send in a single API request prompt
TPM_LIMIT = 200000  # OpenAI Tokens-Per-Minute limit
