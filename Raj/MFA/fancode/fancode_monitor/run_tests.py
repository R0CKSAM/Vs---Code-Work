"""
run_tests.py – Convenience test runner for FanCode Monitor.

Usage
-----
  python run_tests.py                   # All tests (headless)
  python run_tests.py --e2e             # E2E tests only
  python run_tests.py --unit            # Unit tests only
  python run_tests.py --headed          # E2E tests in headed (visible) browser
  python run_tests.py --base-url URL    # Override target URL
  python run_tests.py --timeout MS      # Override browser timeout (ms)
  python run_tests.py --verbose         # Extra verbosity (-vv)
  python run_tests.py --ci              # CI mode: add --tb=long, no colors

Unknown arguments are forwarded directly to pytest.
"""

from __future__ import annotations

import argparse
import subprocess
import sys


def build_pytest_args(args: argparse.Namespace, extra: list[str]) -> list[str]:
    """Translate run_tests.py options into a pytest argument list."""
    cmd: list[str] = [sys.executable, "-m", "pytest"]

    # ── Test scope ────────────────────────────────────────────────────
    if args.e2e:
        cmd.append("tests/e2e")
    elif args.unit:
        cmd.append("tests/unit")
    else:
        cmd.append("tests")

    # ── Browser mode ─────────────────────────────────────────────────
    if args.headed:
        cmd.append("--headed")

    # ── URL / timeout overrides ───────────────────────────────────────
    if args.base_url:
        cmd.extend(["--base-url", args.base_url])
    if args.timeout:
        cmd.extend(["--browser-timeout", str(args.timeout)])

    # ── Verbosity ────────────────────────────────────────────────────
    if args.verbose:
        cmd.append("-vv")

    # ── CI mode ──────────────────────────────────────────────────────
    if args.ci:
        cmd.extend(["--tb=long", "--no-header"])

    # ── Pass-through any unknown pytest arguments ─────────────────────
    cmd.extend(extra)

    return cmd


def main() -> int:
    parser = argparse.ArgumentParser(
        description="FanCode Monitor – test runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--e2e", action="store_true", help="Run E2E tests only.")
    scope.add_argument("--unit", action="store_true", help="Run unit tests only.")

    parser.add_argument(
        "--headed", action="store_true",
        help="Run Playwright tests in headed (visible) browser mode.",
    )
    parser.add_argument(
        "--base-url", metavar="URL",
        help="Override the base URL (default: https://www.fancode.com).",
    )
    parser.add_argument(
        "--timeout", metavar="MS", type=int,
        help="Browser navigation timeout in milliseconds.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable extra verbose pytest output (-vv).",
    )
    parser.add_argument(
        "--ci", action="store_true",
        help="CI mode: long tracebacks, no ANSI colours.",
    )

    args, extra = parser.parse_known_args()
    cmd = build_pytest_args(args, extra)

    print("▶  Running:", " ".join(cmd))
    print("─" * 70)

    result = subprocess.run(cmd, cwd=str(__file__).replace("run_tests.py", ""))
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
