"""Refresh Master Dashboard UI without rebuilding the embedded data marts."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "src" / "dashboards" / "masterDashboard" / "template.html"
OUTPUT = ROOT / "output" / "master" / "veto_master_dashboard.html"


def main() -> None:
    existing = OUTPUT.read_text(encoding="utf-8")
    template = TEMPLATE.read_text(encoding="utf-8")

    chart_match = re.search(r"(<script>[\s\S]*?</script>)\s*</head>", existing)
    data_match = re.search(
        r"const DATA=(\{[\s\S]*?\});\s*\n\s*(?:const SECTIONS=|function unpackCompact)",
        existing,
    )
    if chart_match is None or data_match is None:
        raise RuntimeError("Could not recover Chart.js or the embedded dashboard data.")

    # Substitute data last so a raw value cannot be treated as a template token.
    refreshed = template.replace("$CHARTJS_TAG", chart_match.group(1))
    refreshed = refreshed.replace("$DATA_BLOB", data_match.group(1))
    if "$CHARTJS_TAG" in refreshed or "$DATA_BLOB" in refreshed:
        raise RuntimeError("Master template placeholders remain after refresh.")

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=OUTPUT.parent,
            prefix=f".{OUTPUT.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(refreshed)
            temp_path = Path(handle.name)
        temp_path.replace(OUTPUT)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()

    print(f"Master UI refreshed without data rebuild: {OUTPUT}")


if __name__ == "__main__":
    main()
