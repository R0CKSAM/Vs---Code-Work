"""Smoke-test Watch Hours cross-dimensional filters on the generated report."""

import csv
from pathlib import Path

from playwright.sync_api import sync_playwright


HTML = Path(__file__).resolve().parents[1] / 'output' / 'watch_hours' / 'veto_watch_hours.html'


def test_watch_hours_explorer():
    assert HTML.exists(), f'Generate dashboard first: {HTML}'
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 900}, accept_downloads=True)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(HTML.as_uri(), wait_until='domcontentloaded', timeout=180000)
        page.wait_for_function('exploreRows.length > 1 && document.querySelectorAll("#exploreChannel input").length > 1', timeout=180000)

        baseline = page.evaluate('''() => ({
            explorer: selectedExploreRows().reduce((total, row) => total + row.raw_ts_rows, 0),
            overall: viewDaily.reduce((total, row) => total + Number(row.raw_ts_rows || 0), 0)
        })''')
        assert baseline['explorer'] == baseline['overall']

        selection = page.evaluate('''() => {
            const facets = Object.keys(EXPLORE_FACETS);
            const first = exploreRows[0];
            return Object.fromEntries(facets.map(facet => {
                const one = String(exploreFacetValue(first, facet));
                const other = exploreRows.find(row => String(exploreFacetValue(row, facet)) !== one);
                return [facet, [one, String(exploreFacetValue(other, facet))]];
            }));
        }''')
        for facet, values in selection.items():
            for value in values:
                page.evaluate('''({facet, value}) => {
                    const root = document.getElementById(EXPLORE_FACETS[facet].id);
                    const input = [...root.querySelectorAll('input[type="checkbox"]')].find(node => node.value === value);
                    input.click();
                }''', {'facet': facet, 'value': value})
            assert page.evaluate('(facet) => exploreSelected[facet].size', facet) == 2

        totals = page.evaluate('''() => ({
            count: selectedExploreRows().length,
            raw: selectedExploreRows().reduce((total, row) => total + row.raw_watch_hours, 0),
            shown: document.querySelector('#exploreMetrics .mini span').textContent,
            chart: chartInstances.exploreChart.data.datasets[0].data.length,
            dates: viewDaily.length
        })''')
        assert totals['count'] > 0
        assert totals['shown'] == page.evaluate('(n) => fmtH(n)', totals['raw'])
        assert totals['chart'] == totals['dates']

        page.locator('#exploreChannel summary').click()
        page.locator('#exploreChannel .explore-search').fill('no such channel exists')
        assert page.evaluate('document.querySelectorAll("#exploreChannel .explore-option:not([hidden])").length') == 0
        page.locator('#exploreChannel .explore-search').fill('')

        page.locator('#exploreBreakdown').select_option('region')
        assert page.evaluate('document.querySelector("#exploreBreakdownTable th").textContent') == 'Region'
        page.locator('#exploreMeasure').select_option('status_200_watch_hours')
        assert page.evaluate('chartInstances.exploreChart.data.datasets[0].label') == 'Status 200 watch hours'

        with page.expect_download() as download_info:
            page.get_by_role('button', name='Download CSV').click()
        with open(download_info.value.path(), newline='', encoding='utf-8-sig') as stream:
            exported = list(csv.DictReader(stream))
        assert len(exported) == totals['count']
        assert abs(sum(float(row['raw_watch_hours']) for row in exported) - totals['raw']) < 0.001

        page.locator('#exploreDevice summary').click()
        page.locator('#exploreDevice [data-action="clear"]').click()
        assert page.evaluate('selectedExploreRows().length') == 0
        page.locator('#exploreDevice [data-action="all"]').click()
        assert page.evaluate('selectedExploreRows().length') > 0

        page.locator('#presetYesterday').click()
        assert page.evaluate('viewDaily.length') == 1
        assert page.evaluate('chartInstances.exploreChart.data.datasets[0].data.length') == 1
        page.locator('#sourceFast').click()
        assert page.evaluate('sourceFilter') == 'fast'

        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.locator('#exploreCountry summary').is_visible()
        assert page.evaluate('document.querySelector("#explore").getBoundingClientRect().width <= innerWidth')
        assert not errors, errors[:3]
        browser.close()


if __name__ == '__main__':
    test_watch_hours_explorer()
    print('Watch Hours explorer smoke test passed')
