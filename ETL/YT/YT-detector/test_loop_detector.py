"""
test_loop_detector.py

Validates the core detection algorithm using synthetic frames, so the
logic can be verified without a live YouTube stream on hand. Run with:

    python test_loop_detector.py
"""

from PIL import Image, ImageDraw

from loop_detector import LoopDetector


def make_frame(label: str, size=(64, 64)) -> Image.Image:
    """Deterministic synthetic 'frame': same label always renders identically."""
    img = Image.new("RGB", size, color="black")
    draw = ImageDraw.Draw(img)
    draw.text((5, 25), label, fill="white")
    return img


def test_detects_looping_content():
    """A short cycle repeated many times should be flagged as a probable loop."""
    detector = LoopDetector(match_threshold=6, period_tolerance=3)
    cycle = ["A", "B", "C"]
    t = 0
    for _ in range(6):  # 6 repetitions of the 3-frame cycle
        for label in cycle:
            detector.add_frame(make_frame(label), timestamp=t)
            t += 10  # 10s between samples -> cycle period = 30s

    verdict = detector.verdict()
    assert verdict["probable_loop"] is True, verdict
    assert verdict["dominant_period_seconds"] == 30.0, verdict
    print("PASS: looping content correctly flagged ->", verdict["reason"])


def test_does_not_flag_fresh_content():
    """Frames that are all distinct from each other should not be flagged."""
    detector = LoopDetector(match_threshold=6, period_tolerance=3)
    t = 0
    for i in range(20):
        detector.add_frame(make_frame(f"frame-{i}"), timestamp=t)  # every label unique
        t += 10

    verdict = detector.verdict()
    assert verdict["probable_loop"] is False, verdict
    print("PASS: fresh content correctly left unflagged ->", verdict["reason"])


def test_single_coincidental_match_is_not_enough():
    """One repeated shot (e.g. two similar news-desk wide angles) shouldn't
    alone trigger a loop verdict -- periodicity needs multiple occurrences."""
    detector = LoopDetector(match_threshold=6, period_tolerance=3)
    t = 0
    for i in range(15):
        label = "wide-shot" if i in (2, 9) else f"frame-{i}"  # matches once, non-periodically
        detector.add_frame(make_frame(label), timestamp=t)
        t += 10

    verdict = detector.verdict()
    assert verdict["probable_loop"] is False, verdict
    print("PASS: single coincidental match correctly ignored ->", verdict["reason"])


if __name__ == "__main__":
    test_detects_looping_content()
    test_does_not_flag_fresh_content()
    test_single_coincidental_match_is_not_enough()
    print("\nAll tests passed.")
