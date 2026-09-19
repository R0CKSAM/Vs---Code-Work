import sys
import time

sys.path.insert(0, r"D:\Veto OTT")

import scoreboard_app as core


def check_mode(label, *, single_port, color):
    output = core.DeckLinkLiveOutput(
        "HD 1080i50", device_number=0, external_key=False, single_port=single_port
    )
    try:
        output.start(core.Image.new("RGB", (1920, 1080), color))
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            error = output.poll_error()
            if error:
                raise RuntimeError(error)
            time.sleep(0.1)
        print(f"{label}: PASS")
    finally:
        output.stop()


print(f"MODULE={core.__file__}")
check_mode("Normal", single_port=False, color=(16, 16, 16))
check_mode("Chroma Pink", single_port=True, color=(255, 0, 255))
