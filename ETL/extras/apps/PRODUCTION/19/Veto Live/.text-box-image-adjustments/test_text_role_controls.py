import copy
import unittest

from PIL import ImageChops

import scoreboard_app as core


def color_box(image, predicate):
    points = []
    pixels = image.convert("RGB").load()
    for y in range(image.height):
        for x in range(image.width):
            if predicate(*pixels[x, y]):
                points.append((x, y))
    if not points:
        return None
    xs, ys = zip(*points)
    return min(xs), min(ys), max(xs), max(ys)


class TextRoleControlTests(unittest.TestCase):
    def quarter_config(self):
        cfg = copy.deepcopy(core.DEFAULT_CONFIGS["t12"])
        cfg.update(title="MOVE", subtitle="", country_a="", country_b="",
                   date_text="", venue="")
        return cfg

    def test_quarter_final_has_individual_text_roles(self):
        self.assertEqual(
            [role for role, _ in core.TEXT_STYLE_TARGETS["t12"]],
            ["all", "title", "subtitle", "country_a", "country_b",
             "versus", "date_text", "venue"],
        )

    def test_individual_title_position_size_color_and_style(self):
        base_cfg = self.quarter_config()
        base_cfg["text_styles"] = {
            "title": {"color": [255, 0, 255], "variant": "bold"}
        }
        moved_cfg = copy.deepcopy(base_cfg)
        moved_cfg["text_styles"]["title"].update(
            x_pct=10, y_pct=5, size_pct=130, variant="italic"
        )
        base = core.RENDERERS["t12"]({**base_cfg, "template": "t12"})
        moved = core.RENDERERS["t12"]({**moved_cfg, "template": "t12"})
        predicate = lambda r, g, b: r > 235 and b > 235 and g < 35
        base_box = color_box(base, predicate)
        moved_box = color_box(moved, predicate)
        self.assertIsNotNone(base_box)
        self.assertIsNotNone(moved_box)
        base_cx = (base_box[0] + base_box[2]) / 2
        base_cy = (base_box[1] + base_box[3]) / 2
        moved_cx = (moved_box[0] + moved_box[2]) / 2
        moved_cy = (moved_box[1] + moved_box[3]) / 2
        self.assertAlmostEqual(moved_cx - base_cx, 192, delta=5)
        self.assertAlmostEqual(moved_cy - base_cy, 54, delta=5)
        self.assertGreater(moved_box[2] - moved_box[0], base_box[2] - base_box[0])
        self.assertIsNotNone(ImageChops.difference(base, moved).getbbox())

    def test_normalization_keeps_new_style_fields(self):
        cfg = self.quarter_config()
        cfg["text_styles"] = {
            "venue": {"x_pct": -12.5, "y_pct": 7.5, "variant": "bold_italic"}
        }
        normalized = core.normalise_project_configs({"t12": cfg})["t12"]
        self.assertEqual(
            normalized["text_styles"]["venue"],
            {"variant": "bold_italic", "x_pct": -12.5, "y_pct": 7.5},
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
