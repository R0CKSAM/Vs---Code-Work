from scripts.repair_placeholder_titles import derive_title_and_slug


def test_derives_title_only_from_specific_team_match_url():
    result = derive_title_and_slug(
        "https://www.fancode.com/cricket/tour/x/matches/tasmania-vs-new-south-wales-4249663/live-match-info"
    )
    assert result == ("Tasmania vs New South Wales", "tasmania-vs-new-south-wales")
    assert derive_title_and_slug("https://www.fancode.com/schedule") is None
    assert derive_title_and_slug("https://www.fancode.com/matches/final-4250055/live-match-info") is None
