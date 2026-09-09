from app.transform import path_matches


def test_path_matching_uses_complete_segment():
    assert path_matches("/live/upgovlive/segment.ts?x=1", "upgovlive")
    assert not path_matches("/live/not-upgovlive/segment.ts", "upgovlive")

