import copy

import scoreboard_app as app


def run():
    assert "t18" in app.WEB_TEMPLATE_KEYS
    assert app.WEB_TEMPLATE_NAMES[app.WEB_TEMPLATE_KEYS.index("t18")] == "Scoreboard Astern"
    cfg = copy.deepcopy(app.DEFAULT_CONFIGS["t18"])
    image = app.RENDERERS["t18"](cfg)
    assert image.size == (1920, 1080)
    assert image.mode == "RGBA"
    alpha = image.getchannel("A")
    assert alpha.getextrema() == (0, 255)
    assert alpha.getbbox()
    image.save("scoreboard-astern.png")

    cfg.update(set_count=99, scores_a=["7"], scores_b=None,
               band_size_pct=999, country_a="India", country_b="Korea")
    clean = app.normalise_project_configs({"t18": cfg})["t18"]
    assert clean["set_count"] == 5
    assert clean["band_size_pct"] == 200
    assert clean["scores_a"] == ["7", "", "", "", ""]
    assert clean["scores_b"] == ["", "", "", "", ""]
    assert app.qualifier_country_code(clean["country_a"]) == "in"
    assert app.qualifier_country_code(clean["country_b"]) == "kr"
    print("Scoreboard Astern renderer tests passed")


if __name__ == "__main__":
    run()
