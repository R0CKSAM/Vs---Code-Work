"""
loop_detector.py

Core algorithm for the "is this YouTube stream really live" prototype.

Idea: a genuine live broadcast should look visually different every time
you sample it. A stream that's actually looping a pre-recorded file will
show near-identical frames recurring at a fixed interval. We sample frames
over time, perceptually hash each one, and look for two things:

  1. Repeated near-duplicate frames (via Hamming distance between hashes)
  2. Whether those repeats share a *consistent period* -- one coincidental
     similar frame (e.g. two wide shots of a news desk) isn't evidence of
     looping, but the same match recurring every ~N seconds is.
"""

from dataclasses import dataclass
from typing import Optional

import imagehash
from PIL import Image


@dataclass
class FrameRecord:
    timestamp: float  # seconds since sampling started
    hash: imagehash.ImageHash


@dataclass
class LoopMatch:
    frame_time: float
    matched_time: float
    period: float  # frame_time - matched_time
    distance: int  # Hamming distance between the two hashes


class LoopDetector:
    """
    Feed it frames with timestamps via add_frame(). It tracks near-duplicate
    matches against everything seen so far and flags consistent periodic
    repetition as evidence of a loop.
    """

    def __init__(self, hash_size: int = 16, match_threshold: int = 6,
                 period_tolerance: float = 5.0):
        """
        hash_size:        perceptual hash resolution (bigger = more precise, slower)
        match_threshold:  max Hamming distance to count two frames as "the same shot"
        period_tolerance: seconds of slack when checking whether repeated
                           matches share a consistent period
        """
        self.hash_size = hash_size
        self.match_threshold = match_threshold
        self.period_tolerance = period_tolerance
        self.frames: list[FrameRecord] = []
        self.matches: list[LoopMatch] = []

    def add_frame(self, image: Image.Image, timestamp: float) -> Optional[LoopMatch]:
        """Hash a new frame, compare it against history, record it."""
        h = imagehash.phash(image, hash_size=self.hash_size)

        best_match, best_distance = None, None
        for prev in self.frames:
            distance = h - prev.hash  # Hamming distance
            if distance <= self.match_threshold:
                if best_distance is None or distance < best_distance:
                    best_match, best_distance = prev, distance

        self.frames.append(FrameRecord(timestamp=timestamp, hash=h))

        if best_match is not None:
            match = LoopMatch(
                frame_time=timestamp,
                matched_time=best_match.timestamp,
                period=timestamp - best_match.timestamp,
                distance=best_distance,
            )
            self.matches.append(match)
            return match
        return None

    def novelty_ratio(self) -> float:
        """Fraction of sampled frames that were NOT near-duplicates of an earlier one."""
        if not self.frames:
            return 1.0
        return 1 - (len(self.matches) / len(self.frames))

    def dominant_period(self, tolerance: Optional[float] = None) -> Optional[tuple]:
        """
        Look for a period value that keeps recurring across matches (i.e. a
        cluster of matches all roughly `period` seconds apart). Returns
        (period_seconds, occurrence_count) for the largest such cluster, or
        None if there's no clear repeating cycle.
        """
        if len(self.matches) < 3:
            return None

        tolerance = self.period_tolerance if tolerance is None else tolerance
        periods = sorted(m.period for m in self.matches)

        best_cluster: list[float] = []
        for p in periods:
            cluster = [q for q in periods if abs(q - p) <= tolerance]
            if len(cluster) > len(best_cluster):
                best_cluster = cluster

        if len(best_cluster) < 3:
            return None
        return (sum(best_cluster) / len(best_cluster), len(best_cluster))

    def verdict(self) -> dict:
        """
        Summarize findings into a simple verdict. This is a prototype
        heuristic, not a certainty -- see README for limitations.
        """
        novelty = self.novelty_ratio()
        period_info = self.dominant_period()

        is_looping, reason = False, "insufficient repetition detected -- behaves like fresh content"

        if period_info is not None:
            period, count = period_info
            is_looping = True
            reason = f"{count} frame-matches recur at a consistent ~{period:.0f}s interval"
        elif novelty < 0.5 and len(self.frames) >= 10:
            is_looping = True
            reason = f"only {novelty:.0%} of sampled frames were visually novel"

        return {
            "probable_loop": is_looping,
            "novelty_ratio": round(novelty, 3),
            "frames_sampled": len(self.frames),
            "matches_found": len(self.matches),
            "dominant_period_seconds": round(period_info[0], 1) if period_info else None,
            "reason": reason,
        }
