import importlib.util
import sys
from pathlib import Path
from test_davis_presets import batch
import pytest

sys.modules.setdefault('publish_davis_presets',batch)
spec=importlib.util.spec_from_file_location('h2h_batch',Path(batch.__file__).with_name('publish_india_korea_h2h.py'))
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_pairs_and_unknowns():
    library=[dict(id=f'{c}-{i}',template='t6',country=c,player=f'{c} {i}',
                  config=dict(age='28',total_wl='4/2',player_path='photo.png'))
             for c in ['INDIA','KOREA'] for i in range(5)]
    pairs=module.build_pairs(library)
    assert len(pairs)==len({x['player'] for x in pairs})==25
    for pair in pairs:
        cfg=pair['config']
        assert cfg['meeting']==''
        assert cfg['photo_a']==cfg['photo_b']=='photo.png'
        rows={r['label']:r for r in cfg['rows']}
        assert rows['Age']['value_a']=='28'
        assert rows['Davis Cup W-L']['value_b']=='4/2'
        assert rows['Head-to-Head']['value_a']==''
        assert rows['2026 W-L']['value_a']==''
    with pytest.raises(ValueError):
        module.build_pairs(library[:-1])
