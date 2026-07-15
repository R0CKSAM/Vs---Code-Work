"""Small Chrome DevTools Protocol check for self-contained dashboard HTML."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import urllib.request
from typing import Any

import websockets


class CdpClient:
    def __init__(self, websocket_url: str) -> None:
        self.websocket_url = websocket_url
        self.next_id = 1
        self.events: list[dict[str, Any]] = []

    async def __aenter__(self) -> "CdpClient":
        self.socket = await websockets.connect(self.websocket_url, max_size=None)
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.socket.close()

    async def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_id = self.next_id
        self.next_id += 1
        await self.socket.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
        while True:
            message = json.loads(await self.socket.recv())
            if message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError(f"CDP {method} failed: {message['error']}")
                return message.get("result", {})
            self.events.append(message)


def page_websocket(port: int, timeout: float = 10) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=1) as response:
                pages = json.load(response)
            page = next(item for item in pages if item.get("type") == "page")
            return str(page["webSocketDebuggerUrl"])
        except (OSError, StopIteration, KeyError):
            time.sleep(0.2)
    raise TimeoutError(f"Chrome DevTools page was not available on port {port}")


LAYOUT_EXPRESSION = r"""
(() => {
  const viewport = document.documentElement.clientWidth;
  const offenders = Array.from(document.querySelectorAll('body *')).filter((node) => {
    const style = getComputedStyle(node);
    if (style.display === 'none' || style.visibility === 'hidden' || style.position === 'fixed') return false;
    const rect = node.getBoundingClientRect();
    return rect.width > 0 && (rect.right > viewport + 1 || rect.left < -1);
  }).slice(0, 20).map((node) => ({
    tag: node.tagName,
    id: node.id || '',
    className: typeof node.className === 'string' ? node.className : '',
    left: Math.round(node.getBoundingClientRect().left),
    right: Math.round(node.getBoundingClientRect().right)
  }));
  return {
    readyState: document.readyState,
    viewport,
    bodyScrollWidth: document.body.scrollWidth,
    documentScrollWidth: document.documentElement.scrollWidth,
    overflowCount: offenders.length,
    overflowElements: offenders,
    title: document.title,
    kpiCards: document.querySelectorAll('.kpi-card').length,
    sourceButtons: document.querySelectorAll('#sourceButtons button').length,
    channelOptions: document.querySelectorAll('#channelOptions input').length,
    watchHours: document.getElementById('watchHours')?.textContent || '',
    usedRange: document.getElementById('usedRange')?.textContent || '',
    chartPresent: !!document.querySelector('#dailyChart'),
    chartRendered: !!(document.querySelector('#dailyChart')?.$chartjs)
  };
})()
"""


async def inspect(port: int) -> list[dict[str, Any]]:
    websocket_url = page_websocket(port)
    results: list[dict[str, Any]] = []
    async with CdpClient(websocket_url) as cdp:
        await cdp.call("Runtime.enable")
        await cdp.call("Page.enable")
        for width, height, name in ((1440, 1000, "desktop"), (390, 844, "mobile")):
            await cdp.call(
                "Emulation.setDeviceMetricsOverride",
                {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": width < 600},
            )
            cdp.events.clear()
            await cdp.call("Page.reload", {"ignoreCache": True})
            await asyncio.sleep(2)
            evaluated = await cdp.call(
                "Runtime.evaluate",
                {"expression": LAYOUT_EXPRESSION, "returnByValue": True, "awaitPromise": True},
            )
            value = evaluated.get("result", {}).get("value", {})
            exceptions = [event for event in cdp.events if event.get("method") == "Runtime.exceptionThrown"]
            value.update({"viewportName": name, "runtimeExceptions": len(exceptions)})
            results.append(value)
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(inspect(args.port)), indent=2))


if __name__ == "__main__":
    main()
