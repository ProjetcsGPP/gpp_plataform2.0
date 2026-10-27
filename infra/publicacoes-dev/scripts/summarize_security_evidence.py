#!/usr/bin/env python3
"""Resume relatórios JSON do Trivy sem decidir ou suprimir achados."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def main() -> int:
    evidence_dir = Path(sys.argv[1])
    summary: dict[str, dict[str, int]] = {}
    for report_path in sorted(evidence_dir.glob("*.vuln.json")):
        report = json.loads(report_path.read_text(encoding="utf-8"))
        counts: Counter[str] = Counter()
        for result in report.get("Results") or ():
            for vulnerability in result.get("Vulnerabilities") or ():
                counts[vulnerability.get("Severity", "UNKNOWN")] += 1
        summary[report_path.name.removesuffix(".vuln.json")] = dict(
            sorted(counts.items())
        )
    json.dump(summary, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
