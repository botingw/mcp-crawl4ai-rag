import json
from collections import defaultdict

class StatsCollector:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(StatsCollector, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.reset()
        self._initialized = True

    def reset(self):
        """
        Resets all statistics to their initial state.
        """
        self.aggregated_stats = {
            "total_api_calls_initiated": 0,
            "total_successful_calls": 0,
            "total_failed_calls": 0,
            "total_tokens_from_raw_docs": 0,
            "total_prompt_tokens_sent": 0,
            "total_completion_tokens_received": 0,
            "total_billed_tokens": 0,
            "calls_by_type": defaultdict(lambda: {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
        }
        self.per_chunk_stats = defaultdict(lambda: defaultdict(lambda: {
            "raw_chunk_tokens": 0,
            "total_api_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "total_prompt_tokens_sent": 0,
            "total_completion_tokens_received": 0,
            "total_billed_tokens": 0,
            "call_details": []
        }))

    def log_raw_chunk(self, source_file: str, chunk_index: int, raw_chunk_tokens: int):
        """
        Logs the token count of a raw, unprocessed document chunk.
        """
        self.aggregated_stats["total_tokens_from_raw_docs"] += raw_chunk_tokens
        chunk_stats = self.per_chunk_stats[source_file][chunk_index]
        chunk_stats["raw_chunk_tokens"] = raw_chunk_tokens

    def log_api_call(self, source_file: str, chunk_index: int, call_type: str, prompt_tokens: int, completion_tokens: int, total_tokens: int, status: str, error_details: str = None):
        """
        Logs the details of a single API call, including input, output, and total tokens.
        """
        # Update aggregated stats
        self.aggregated_stats["total_api_calls_initiated"] += 1
        self.aggregated_stats["total_prompt_tokens_sent"] += prompt_tokens
        self.aggregated_stats["total_completion_tokens_received"] += completion_tokens
        self.aggregated_stats["total_billed_tokens"] += total_tokens

        # Update per-chunk stats
        chunk_stats = self.per_chunk_stats[source_file][chunk_index]
        chunk_stats["total_api_calls"] += 1
        chunk_stats["total_prompt_tokens_sent"] += prompt_tokens
        chunk_stats["total_completion_tokens_received"] += completion_tokens
        chunk_stats["total_billed_tokens"] += total_tokens

        call_detail = {
            "call_type": call_type,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "status": status,
        }
        if error_details:
            call_detail["error_details"] = error_details
        
        chunk_stats["call_details"].append(call_detail)

        if status == "Success":
            self.aggregated_stats["total_successful_calls"] += 1
            chunk_stats["successful_calls"] += 1
        else:
            self.aggregated_stats["total_failed_calls"] += 1
            chunk_stats["failed_calls"] += 1

        # Update aggregated stats by call type
        call_type_stats = self.aggregated_stats["calls_by_type"][call_type]
        call_type_stats["calls"] += 1
        call_type_stats["prompt_tokens"] += prompt_tokens
        call_type_stats["completion_tokens"] += completion_tokens
        call_type_stats["total_tokens"] += total_tokens

    def get_report(self) -> str:
        """
        Generates a comprehensive JSON report of all collected statistics.
        """
        report = {
            "aggregated_stats": dict(self.aggregated_stats),
            "per_chunk_stats": {k: dict(v) for k, v in self.per_chunk_stats.items()}
        }
        report["aggregated_stats"]["calls_by_type"] = {k: dict(v) for k, v in self.aggregated_stats["calls_by_type"].items()}
        return json.dumps(report, indent=4)

# Global singleton instance
stats_collector = StatsCollector()