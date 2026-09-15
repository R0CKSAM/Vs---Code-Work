import copy
import importlib.util
import json
import sys
from pathlib import Path

from test_scoreboard_app import scoreboard
from test_davis_presets import batch
import pytest

sys.modules.setdefault('publish_davis_presets', batch)
spec=importlib.util.spec_from_file_location('qualifier_import',Path(batch.__file__).with_name('fill_qualifier_results.py'))
importer=importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)


def source():
    return json.loads(Path(importer.__file__).with_name('davis_2026_round1_results.json').read_text())


def test_all_country_results_reconcile_and_render():
    data=source()
    importer.validate_results(data)
    for country in importer.COUNTRIES:
        config=importer.config_for_country(data,country)
        assert len(config['rows'])==5
        assert scoreboard.render_t7(config).size==(1920,1080)
    usa=importer.config_for_country(data,'United States')
    assert usa['score']=='4-0'
    assert usa['country_b']=='HUNGARY'
    assert usa['rows'][0]=={'value_a':'W','value_b':'L'}
    assert importer.config_for_country(data,'India')['rows'][0]=={'value_a':'L','value_b':'W'}
    assert importer.config_for_country(data,'United States',set_scores=True)['rows'][0]=={'value_a':'7   6','value_b':'6   3'}
    assert usa['rows'][4]=={'value_a':'NOT PLAYED','value_b':'NOT PLAYED'}
    assert importer.config_for_country(data,'Spain')['score']=='BYE'
    assert importer.config_for_country(data,'Korea')['score']=='3-2'


def test_invalid_totals_and_completed_matches_rejected():
    data=source()
    data['ties'][0]['score']=[3,1]
    with pytest.raises(ValueError,match='reconcile'):
        importer.validate_results(data)
    data=source()
    data['ties'][0]['matches'][0]=[[6,6,6],[4,4,4]]
    with pytest.raises(ValueError,match='Extra set'):
        importer.validate_results(data)


def test_existing_content_is_protected():
    config=copy.deepcopy(scoreboard.DEF_T7)
    config.update(country_b='',score='',rows=[{'value_a':'','value_b':''}]*5)
    assert not importer.has_results(config)
    config['rows']=[{'value_a':'Operator draft','value_b':''}]
    assert importer.has_results(config)
