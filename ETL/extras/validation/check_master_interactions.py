"""Exercise master-dashboard filters through a running Chrome CDP page."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
from pathlib import Path
from typing import Any


HELPER_PATH = Path(__file__).resolve().with_name("check_static_dashboard.py")
SPEC = importlib.util.spec_from_file_location("static_dashboard_check", HELPER_PATH)
assert SPEC is not None and SPEC.loader is not None
HELPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPER)


SNAPSHOT = r"""
(() => ({
  source: state.source,
  mode: state.mode,
  from: state.from,
  to: state.to,
  watchHours: document.getElementById('watchHours').textContent,
  ipUsers: document.getElementById('ipUsers').textContent,
  deviceUsers: document.getElementById('deviceUsers').textContent,
  sessionUsers: document.getElementById('sessionUsers').textContent,
  averageWatch: document.getElementById('averageWatch').textContent,
  usedRange: document.getElementById('usedRange').textContent,
  channelSummary: document.getElementById('channelSummary').textContent,
  channelOptions: document.querySelectorAll('#channelOptions input').length,
  deviceRows: document.querySelectorAll('#deviceLeaderboard .rank-row').length,
  osRows: document.querySelectorAll('#osLeaderboard .rank-row').length,
  stateRows: document.querySelectorAll('#stateLeaderboard .rank-row').length,
  countryRows: document.querySelectorAll('#countryLeaderboard .rank-row').length,
  topDevice: document.querySelector('#deviceLeaderboard .rank-name span')?.textContent || '',
  topState: document.querySelector('#stateLeaderboard .rank-name span')?.textContent || '',
  uaCoverage: document.getElementById('uaCoverage').textContent,
  bodyScrollWidth: document.body.scrollWidth,
  viewport: document.documentElement.clientWidth
}))()
"""


async def evaluate(cdp: Any, expression: str) -> Any:
    result = await cdp.call(
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": True},
    )
    return result.get("result", {}).get("value")


async def check(port: int) -> dict[str, Any]:
    snapshots: dict[str, Any] = {}
    async with HELPER.CdpClient(HELPER.page_websocket(port)) as cdp:
        await cdp.call("Runtime.enable")
        await asyncio.sleep(2)
        snapshots["default"] = await evaluate(cdp, SNAPSHOT)
        await evaluate(cdp, "setSource('fast')")
        snapshots["fast"] = await evaluate(cdp, SNAPSHOT)
        await evaluate(cdp, "setSource('stream')")
        snapshots["stream"] = await evaluate(cdp, SNAPSHOT)
        await evaluate(cdp, "setQuickRange('7')")
        snapshots["stream_7d"] = await evaluate(cdp, SNAPSHOT)
        await evaluate(
            cdp,
            "state.channels=new Set(['India TV']);renderChannelOptions();renderAll()",
        )
        snapshots["stream_7d_india_tv"] = await evaluate(cdp, SNAPSHOT)
        await evaluate(cdp, "setSource('fast')")
        snapshots["fast_7d_india_tv"] = await evaluate(cdp, SNAPSHOT)
        snapshots["runtimeExceptions"] = len(
            [event for event in cdp.events if event.get("method") == "Runtime.exceptionThrown"]
        )
    return snapshots


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(check(args.port)), indent=2))


if __name__ == "__main__":
    main()
