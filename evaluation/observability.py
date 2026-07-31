"""
Lightweight observability logger for MedFlow evaluation runs.

Every evaluation run (agent eval or LLM eval) is logged as a timestamped
JSON file to ``evaluation/runs/``. This enables post-hoc analysis of model
behaviour without depending on an external observability platform.

Why a custom logger instead of Opik?
  - Zero external dependencies — no API keys, no SDK installs.
  - Flat JSON files are trivial to version-control, grep, and diff.
  - Easy to ingest into any dashboard (Grafana, ELK, custom) later.

Usage:
    from evaluation.observability import EvalLogger

    logger = EvalLogger(tier="multi_tool")
    logger.log_run(case_id="MT-01", question="...", final_answer="...",
                   trace={...}, passed=True, failures=[])
    logger.close()
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

_RUNS_DIR = os.path.join(os.path.dirname(__file__), "runs")


class EvalLogger:
    """Log evaluation runs to timestamped JSON files in ``evaluation/runs/``."""

    def __init__(self, tier: str = "unknown") -> None:
        self._tier = tier
        self._rows: list[dict[str, Any]] = []
        os.makedirs(_RUNS_DIR, exist_ok=True)

    def log_run(
        self,
        case_id: str,
        question: str,
        final_answer: str,
        trace: dict,
        passed: bool,
        failures: list[str] | None = None,
        **extra: Any,
    ) -> None:
        """Append one evaluation run to the in-memory log."""
        self._rows.append({
            "case_id": case_id,
            "tier": self._tier,
            "question": question,
            "final_answer": final_answer,
            "passed": passed,
            "failures": failures or [],
            "trace": trace,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **extra,
        })

    def close(self) -> str:
        """
        Flush all logged runs to a timestamped JSON file.

        Returns the path of the written file.
        """
        if not self._rows:
            return ""

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{timestamp}_{self._tier}.json"
        filepath = os.path.join(_RUNS_DIR, filename)

        summary = {
            "tier": self._tier,
            "total": len(self._rows),
            "passed": sum(1 for r in self._rows if r["passed"]),
            "failed": sum(1 for r in self._rows if not r["passed"]),
            "timestamp": timestamp,
            "runs": self._rows,
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False, default=str)

        print(f"\n  [Observability] Logged {len(self._rows)} run(s) to {filepath}")
        self._rows.clear()
        return filepath

    def __enter__(self) -> EvalLogger:
        return self

    def __exit__(self, *args: Any) -> None:
        if self._rows:
            self.close()

