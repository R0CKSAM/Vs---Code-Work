import copy
import importlib.util
from pathlib import Path

from PIL import Image, ImageChops


ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("scoreboard_app_visual_test", ROOT / "scoreboard_app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


def test_all_templates_render_with_new_defaults():
    for key, renderer in app.RENDERERS.items():
        cfg = copy.deepcopy(app.DEFAULT_CONFIGS[key])
        image = renderer(cfg)
        assert image.size == (1920, 1080), key


def test_selected_text_role_box_changes_render():
    cfg = copy.deepcopy(app.DEFAULT_CONFIGS["t12"])
    cfg["text_styles"] = {
        "title": {
            "box_enabled": True,
            "box_color": [220, 10, 120],
            "box_opacity_pct": 85,
            "box_padding_pct": 30,
        }
    }
    plain = app.RENDERERS["t12"](copy.deepcopy(app.DEFAULT_CONFIGS["t12"]))
    boxed = app.RENDERERS["t12"](cfg)
    assert ImageChops.difference(plain.convert("RGB"), boxed.convert("RGB")).getbbox()


def test_image_adjustments_preserve_alpha_and_change_rgb():
    source = Image.new("RGBA", (2, 1))
    source.putdata([(40, 90, 160, 23), (210, 80, 30, 201)])
    adjusted = app.adjust_source_image(source, {
        "image_brightness_pct": 135,
        "image_vibrance_pct": 160,
        "image_contrast_pct": 125,
    })
    assert list(adjusted.getchannel("A").getdata()) == [23, 201]
    assert list(adjusted.convert("RGB").getdata()) != list(source.convert("RGB").getdata())


def test_visual_settings_are_normalised():
    saved = copy.deepcopy(app.DEFAULT_CONFIGS)
    saved["t12"]["image_brightness_pct"] = 999
    saved["t12"]["text_styles"] = {
        "title": {
            "box_enabled": 1,
            "box_color": [-5, 20, 999],
            "box_opacity_pct": 110,
            "box_padding_pct": -2,
        }
    }
    clean = app.normalise_project_configs(saved)["t12"]
    assert clean["image_brightness_pct"] == 200
    assert clean["text_styles"]["title"] == {
        "box_enabled": True,
        "box_color": [0, 20, 255],
        "box_opacity_pct": 100,
        "box_padding_pct": 0,
    }
