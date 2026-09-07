from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "ETL" / "extras" / "apps" / "leaderBoardGen" / "scoreboard_app.py"
SPEC = importlib.util.spec_from_file_location("scoreboard_app", MODULE_PATH)
assert SPEC and SPEC.loader
scoreboard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scoreboard)


def test_text_style_inheritance_and_role_override() -> None:
    selected_font = next(
        (family for family in scoreboard.FONT_CHOICES if family != "Default"),
        "Default",
    )
    config = copy.deepcopy(scoreboard.DEF_T1)
    config["text_styles"] = {
        "all": {
            "color": [12, 34, 56],
            "size_pct": 125,
            "font_family": selected_font,
        },
        "title": {"color": [240, 20, 40], "size_pct": 150},
    }

    assert scoreboard.text_style_values(config, "stat_labels", (1, 2, 3)) == (
        (12, 34, 56),
        125,
    )
    assert scoreboard.text_style_values(config, "title", (1, 2, 3)) == (
        (240, 20, 40),
        150,
    )
    assert scoreboard.text_font_family(config, "title") == selected_font
    assert scoreboard.text_font_family(config, "stat_values") == selected_font


def test_text_case_preserves_typed_case_and_supports_explicit_transforms() -> None:
    config = copy.deepcopy(scoreboard.DEF_T1)
    assert scoreboard.apply_text_case(config, "stat_labels", "First Serve won") == "First Serve won"

    config["text_styles"] = {
        "all": {"case": "lowercase"},
        "stat_labels": {"case": "UPPERCASE"},
    }
    assert scoreboard.apply_text_case(config, "title", "Match Statistics") == "match statistics"
    assert scoreboard.apply_text_case(config, "stat_labels", "First Serve won") == "FIRST SERVE WON"


def test_project_normalization_rejects_bad_text_styles() -> None:
    configs = scoreboard.normalise_project_configs(
        {
            "t1": {
                "text_styles": {
                    "title": {
                        "color": ["bad", 2, 3],
                        "size_pct": 999,
                        "font_family": "Definitely Missing Font",
                    },
                    "unknown_role": {"color": [1, 2, 3], "size_pct": 80},
                }
            }
        }
    )

    assert configs["t1"]["text_styles"] == {"title": {"size_pct": 200}}


def test_single_player_layer_settings_are_normalized() -> None:
    config = scoreboard.normalise_project_configs(
        {
            "t1": {
                "player_x_pct": -50,
                "player_size_pct": 900,
                "logo_y_pct": "bad",
                "panel_width_pct": 99,
                "panel_opacity_pct": -3,
                "panel_color": [400, -20, 31],
                "panel_side": "middle",
            }
        }
    )["t1"]

    assert config["player_x_pct"] == 0
    assert config["player_size_pct"] == 300
    assert config["logo_y_pct"] == scoreboard.DEF_T1["logo_y_pct"]
    assert config["panel_width_pct"] == 80
    assert config["panel_opacity_pct"] == 0
    assert config["panel_color"] == [255, 0, 31]
    assert config["panel_side"] == scoreboard.DEF_T1["panel_side"]


def test_single_player_overlay_geometry_uses_independent_layer_scales(monkeypatch) -> None:
    monkeypatch.setattr(
        scoreboard,
        "load_photo",
        lambda _path: scoreboard.Image.new("RGBA", (100, 200), (255, 0, 0, 255)),
    )
    config = copy.deepcopy(scoreboard.DEF_T1)
    config.update(
        {
            "player_path": "player.png",
            "player_x_pct": 25,
            "player_y_pct": 60,
            "player_size_pct": 50,
            "logo_path": "logo.png",
            "logo_x_pct": 90,
            "logo_y_pct": 10,
            "logo_size_pct": 10,
        }
    )

    _, player_box = scoreboard.t1_overlay_geometry(config, "player", 1000, 500)
    _, logo_box = scoreboard.t1_overlay_geometry(config, "logo", 1000, 500)

    assert player_box == (188, 175, 125, 250)
    assert logo_box == (850, -50, 100, 200)


def test_single_player_renderer_composites_player_and_logo(monkeypatch) -> None:
    def fake_photo(path: str):
        colors = {
            "player.png": (240, 20, 30, 255),
            "logo.png": (20, 220, 60, 255),
        }
        return scoreboard.Image.new("RGBA", (100, 100), colors[path]) if path in colors else None

    monkeypatch.setattr(scoreboard, "load_photo", fake_photo)
    config = copy.deepcopy(scoreboard.DEF_T1)
    config.update(
        {
            "canvas_size": "16:9  (1024x576)",
            "title": "",
            "rows": [],
            "photo_path": "",
            "player_path": "player.png",
            "player_x_pct": 50,
            "player_y_pct": 50,
            "player_size_pct": 20,
            "player_in_front": True,
            "logo_path": "logo.png",
            "logo_x_pct": 90,
            "logo_y_pct": 10,
            "logo_size_pct": 5,
            "panel_opacity_pct": 0,
        }
    )

    image = scoreboard.render_t1(config)

    assert image.getpixel((512, 288)) == (240, 20, 30)
    assert image.getpixel((922, 58)) == (20, 220, 60)


def test_single_player_row_colors_override_group_colors() -> None:
    config = copy.deepcopy(scoreboard.DEF_T1)
    config.update(
        {
            "canvas_size": "16:9  (1024x576)",
            "title": "",
            "rows": [{
                "label": "Label", "value": "80", "max": "100",
                "label_color": [11, 202, 33],
                "value_color": [220, 41, 62],
                "bar_color": [34, 77, 211],
            }],
        }
    )

    colors = {color for _, color in scoreboard.render_t1(config).getcolors(1024 * 576)}

    assert (11, 202, 33) in colors
    assert (220, 41, 62) in colors
    assert (34, 77, 211) in colors


def test_single_player_group_bar_color_is_independent_from_value_color() -> None:
    config = copy.deepcopy(scoreboard.DEF_T1)
    config.update(
        {
            "canvas_size": "16:9  (1024x576)",
            "title": "",
            "bar_color": [24, 84, 220],
            "text_styles": {"stat_values": {"color": [235, 45, 91]}},
            "rows": [{"label": "Label", "value": "80", "max": "100"}],
        }
    )

    colors = {color for _, color in scoreboard.render_t1(config).getcolors(1024 * 576)}

    assert (24, 84, 220) in colors
    assert (235, 45, 91) in colors


def test_single_player_panel_effects_are_distinct() -> None:
    background = scoreboard.Image.new("RGB", (240, 160), (30, 80, 130))
    configs = []
    for style in ("solid", "gradient", "glass"):
        config = copy.deepcopy(scoreboard.DEF_T1)
        config.update({
            "panel_style": style,
            "panel_opacity_pct": 90,
            "panel_fade_pct": 0,
            "panel_color": [10, 20, 30],
            "panel_color_2": [100, 120, 140],
        })
        configs.append(scoreboard.apply_t1_panel_effect(background, config, 120, 120, "right"))

    samples = [image.getpixel((220, 20)) for image in configs]
    assert len(set(samples)) == 3
    assert configs[1].getpixel((220, 20)) != configs[1].getpixel((220, 140))


def test_single_player_glass_panel_has_no_white_edge_highlight() -> None:
    background = scoreboard.Image.new("RGB", (240, 160), (30, 80, 130))
    config = copy.deepcopy(scoreboard.DEF_T1)
    config.update({
        "panel_style": "glass",
        "panel_opacity_pct": 90,
        "panel_fade_pct": 0,
        "panel_blur_pct": 0,
        "panel_color": [10, 20, 30],
    })

    image = scoreboard.apply_t1_panel_effect(background, config, 120, 120, "right")

    assert image.getpixel((120, 80)) == image.getpixel((121, 80))


def test_style_preset_changes_appearance_without_replacing_content() -> None:
    source = copy.deepcopy(scoreboard.DEF_T1)
    source.update(
        {
            "panel_width_pct": 57,
            "row_gap_pct": 6,
            "accent_color": [12, 180, 220],
            "bar_color": [220, 80, 24],
            "background_color": [18, 36, 54],
            "text_styles": {"all": {"font_family": "Default", "size_pct": 115}},
        }
    )
    target = copy.deepcopy(scoreboard.DEF_T1)
    target["photo_path"] = "keep-background.png"
    target["rows"] = [{"label": "Keep", "value": "99", "max": "100"}]

    applied = scoreboard.apply_style_preset(
        target,
        "t1",
        scoreboard.build_style_preset(source, "t1"),
    )

    assert applied["photo_path"] == "keep-background.png"
    assert applied["rows"] == target["rows"]
    assert applied["panel_width_pct"] == 57
    assert applied["row_gap_pct"] == 6
    assert applied["accent_color"] == [12, 180, 220]
    assert applied["bar_color"] == [220, 80, 24]
    assert applied["background_color"] == [18, 36, 54]


def test_single_player_extreme_text_layout_still_renders() -> None:
    config = copy.deepcopy(scoreboard.DEF_T1)
    config["rows"] = [
        {"label": f"Long statistic label number {index}", "value": "100 percent", "max": "100"}
        for index in range(12)
    ]
    config["row_gap_pct"] = 15
    config["title_gap_pct"] = 20
    config["text_styles"] = {"all": {"size_pct": 200}}

    image = scoreboard.render_t1(config)

    assert image.size == scoreboard.T1_SIZES[config["canvas_size"]]


@pytest.mark.parametrize("template", scoreboard.TEMPLATE_KEYS)
def test_every_renderer_accepts_text_style_overrides(template: str) -> None:
    config = copy.deepcopy(scoreboard.DEFAULT_CONFIGS[template])
    role = next(role for role, _ in scoreboard.TEXT_STYLE_TARGETS[template] if role != "all")
    config["text_styles"] = {
        "all": {
            "color": [230, 210, 30],
            "size_pct": 110,
            "font_family": next(
                (family for family in scoreboard.FONT_CHOICES if family != "Default"),
                "Default",
            ),
        },
        role: {"color": [30, 180, 110], "size_pct": 125},
    }

    image = scoreboard.RENDERERS[template](config)
    expected_size = {
        "t1": scoreboard.T1_SIZES,
        "t2": scoreboard.T2_SIZES,
        "t3": scoreboard.T3_SIZES,
        "t4": scoreboard.T4_SIZES,
    }[template][config["canvas_size"]]
    assert image.size == expected_size
    assert any(low < high for low, high in image.getextrema())


@pytest.mark.parametrize("template", scoreboard.TEMPLATE_KEYS)
def test_every_renderer_honors_background_color(template: str) -> None:
    config=copy.deepcopy(scoreboard.DEFAULT_CONFIGS[template])
    config["background_color"]=[17,34,51]

    image=scoreboard.RENDERERS[template](config)

    assert image.getpixel((0,image.height-1)) == (17,34,51)


def test_head_to_head_photo_controls_are_normalized_and_saved_in_styles() -> None:
    config = scoreboard.normalise_project_configs({
        "t2": {
            "photo_width_pct": 99,
            "photo_fade_pct": -10,
            "photo_brightness_pct": 500,
        }
    })["t2"]

    assert config["photo_width_pct"] == 52
    assert config["photo_fade_pct"] == 0
    assert config["photo_brightness_pct"] == 120

    preset = scoreboard.build_style_preset(config, "t2")["settings"]
    assert preset["photo_width_pct"] == 52
    assert preset["photo_fade_pct"] == 0
    assert preset["photo_brightness_pct"] == 120


def test_head_to_head_names_adapt_to_light_background() -> None:
    config = copy.deepcopy(scoreboard.DEF_T2)
    config["background_color"] = [45, 236, 183]

    assert scoreboard.default_text_color(config, "t2", "player_1_names") == (10, 24, 38)
    assert scoreboard.default_text_color(config, "t2", "player_1_country") == (42, 65, 80)


def test_head_to_head_photo_keeps_outer_top_edge_opaque(monkeypatch) -> None:
    monkeypatch.setattr(
        scoreboard,
        "load_photo",
        lambda _path: scoreboard.Image.new("RGB", (300, 600), (240, 20, 30)),
    )
    config = copy.deepcopy(scoreboard.DEF_T2)
    config.update({"photo_a": "player.jpg", "rows": [], "show_playing_style": False})

    image = scoreboard.render_t2(config)
    red, green, blue = image.getpixel((0, 0))

    assert red > 180
    assert green < 40
    assert blue < 40


@pytest.mark.parametrize("template", ("t2", "t3", "t4"))
def test_comparison_templates_support_independent_group_bar_color(template: str) -> None:
    config=copy.deepcopy(scoreboard.DEFAULT_CONFIGS[template])
    config["bar_color"]=[21, 83, 219]

    image=scoreboard.RENDERERS[template](config)
    colors={color for _count,color in image.getcolors(image.width * image.height)}

    assert (21, 83, 219) in colors


@pytest.mark.parametrize("template", ("t2", "t3", "t4"))
def test_free_logo_can_be_positioned_anywhere(monkeypatch, template: str) -> None:
    original=scoreboard.load_photo
    monkeypatch.setattr(
        scoreboard,"load_photo",
        lambda path: scoreboard.Image.new("RGBA",(100,50),(12,230,74,255))
        if path == "logo.png" else original(path),
    )
    config=copy.deepcopy(scoreboard.DEFAULT_CONFIGS[template])
    config.update({"logo_path":"logo.png","logo_x_pct":20,"logo_y_pct":80,"logo_size_pct":10})

    image=scoreboard.RENDERERS[template](config)
    sample_x=int(image.width*.20)
    sample_y=int(image.height*.80)

    assert image.getpixel((sample_x,sample_y)) == (12,230,74)


def test_canvas_photo_boxes_cover_all_editable_player_slots() -> None:
    assert set(scoreboard.canvas_photo_boxes("t2",scoreboard.DEF_T2,1152,640)) == {"photo_a","photo_b"}
    assert set(scoreboard.canvas_photo_boxes("t3",scoreboard.DEF_T3,1080,1080)) == {"photo_a","photo_b"}
    assert set(scoreboard.canvas_photo_boxes("t4",scoreboard.DEF_T4,1080,1080)) == {
        "player_1","player_2","player_3",
    }
