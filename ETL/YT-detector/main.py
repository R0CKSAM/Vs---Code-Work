"""
main.py

CLI entry point: point it at a YouTube live URL, let it sample frames for
a while, and it prints a verdict on whether the stream looks like it's
looping pre-recorded content.

Usage:
    python main.py "https://www.youtube.com/watch?v=XXXXXXXX" --interval 20 --duration 30
"""

import argparse
import json

from frame_sampler import sample_stream
from loop_detector import LoopDetector


def main():
    parser = argparse.ArgumentParser(
        description="Detect whether a YouTube live stream is looping pre-recorded content."
    )
    parser.add_argument("url", help="YouTube live stream URL")
    parser.add_argument("--interval", type=int, default=20,
                         help="Seconds between samples (default: 20)")
    parser.add_argument("--duration", type=float, default=30,
                         help="How many minutes to sample for (default: 30)")
    parser.add_argument("--hash-size", type=int, default=16,
                         help="Perceptual hash resolution (default: 16)")
    parser.add_argument("--threshold", type=int, default=6,
                         help="Max Hamming distance to call two frames a match (default: 6)")
    args = parser.parse_args()

    detector = LoopDetector(hash_size=args.hash_size, match_threshold=args.threshold)

    print(f"Sampling {args.url}")
    print(f"every {args.interval}s for {args.duration} min (~{int(args.duration * 60 / args.interval)} samples)...\n")

    for elapsed, frame in sample_stream(args.url, args.interval, args.duration):
        match = detector.add_frame(frame, elapsed)
        tag = f"MATCH (Δ{match.period:.0f}s, dist={match.distance})" if match else "new"
        print(f"  t={elapsed:6.0f}s  {tag}")

    print("\nVerdict:")
    print(json.dumps(detector.verdict(), indent=2))


if __name__ == "__main__":
    main()
