import importlib.util
import json
import sys
from pathlib import Path

from test_davis_player_import import importer

sys.modules.setdefault('import_davis_players', importer)
spec = importlib.util.spec_from_file_location('davis_presets', importer.ROOT / 'publish_davis_presets.py')
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)


def test_labels_and_existing_identity():
    assert batch.display_country('South Korea') == 'KOREA'
    assert batch.display_country('India') == 'INDIA'
    assert batch.identity(dict(template='t6', player='A Player', country='Korea')) == batch.identity(
        dict(template='t6', player='a player', country='South Korea'))


def test_batch_country_presets_no_sample_results(tmp_path):
    source = tmp_path / 'source.csv'
    source.write_text('COUNTRY,NAME,AGE,TOTAL W/L,DEBUT YEAR,FAVOURATE HAND\n')
    photo = tmp_path / 'photo.json'
    photo.write_text(json.dumps({'players': []}))
    report = {'players': [dict(role='player', profile_id='one', name='Player', country='India',
                              config=dict(importer.core.DEF_T6)),
                          dict(role='captain', name='Captain')]}
    items = batch.build_items(report, [photo], source)
    assert len(items) == 15
    players = [x for x in items if x['template'] == 't6']
    assert players[0]['country'] == 'INDIA' and players[0]['player'] == 'Player'
    qualifiers = [x for x in items if x['template'] == 't7']
    assert len(qualifiers) == 14
    assert all(x['config']['country_b'] == '' and x['config']['score'] == '' for x in qualifiers)
    assert all(row == {'value_a': '', 'value_b': ''} for x in qualifiers for row in x['config']['rows'])
