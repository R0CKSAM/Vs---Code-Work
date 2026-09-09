// Run with: node tests/test_frequency_neighbours.js
const assert = require('node:assert/strict');
const source = require('node:fs').readFileSync(require('node:path').join(__dirname, '../app.py'), 'utf8');
const start = source.indexOf('let neighbourCache =');
const end = source.indexOf('let headendAvailCache =', start);
const createLookup = new Function('report', source.slice(start, end) + '\nreturn getNeighbourForChannelInWeek;');
const row = (channel, frequency, city = 'City A', mso = 'HITS') => ({
  channel_name: channel, market: 'Market', head_end: 'Headend', city, mso_type: mso,
  frequencies: { Previous: frequency, Current: frequency },
});
const report = { records: [
  row('AAJ TAK', 100), row('INDIA TV', 101), row(' india tv ', 101), row('NEWS 18 INDIA', 102),
  row('REPUBLIC BHARAT', 99, 'City B'), row('INDIA TV', 101, 'City B'),
  row('DTH CHANNEL', 100, 'City A', 'DTH'), row('INDIA TV', 101, 'City A', 'DTH'),
  row('INVALID', 'not a number'), row('MISSING', null), row('EMPTY', ''), row('NA', 100.5),
] };
const lookup = createLookup(report);
const get = (channel = 'INDIA TV', city = 'City A', mso = 'HITS', week = 'Current') =>
  lookup(channel, 'Market', 'Headend', week, city, mso);
assert.equal(get(), 'AAJ TAK', 'Duplicate channel rows cannot become their own neighbour');
assert.equal(get('INDIA TV', 'City B'), 'REPUBLIC BHARAT', 'Cities must have separate lineups and cache entries');
assert.equal(get('INDIA TV', 'City A', 'DTH'), 'DTH CHANNEL', 'MSO types must have separate lineups and cache entries');
assert.equal(get('AAJ TAK'), 'INDIA TV', 'First channel falls back to the following channel');
assert.equal(get(' india tv '), 'AAJ TAK', 'Channel comparison ignores case and surrounding spaces');
assert.equal(get('INDIA TV', 'Unknown city'), '', 'Never fall back to a different city');
assert.equal(get('MISSING'), '', 'Unavailable channels have no neighbour');
assert.equal(get('INDIA TV', 'City A', 'HITS', 'Unknown week'), '');
report.records[0].frequencies.Previous = null;
assert.equal(get('INDIA TV', 'City A', 'HITS', 'Previous'), 'NEWS 18 INDIA', 'Weeks have separate cache entries and skip duplicate rows in the forward direction');
report.records = [row('INDIA TV', 101), row(' india tv ', 101)];
assert.equal(get(), '', 'A lineup containing only the same channel has no neighbour; replacing data clears the cache');
console.log('Frequency neighbour regression checks passed.');

const placementStart = source.indexOf('function getChannelPlacementInWeek(');
const placementEnd = source.indexOf('function applyRepeatedChangeStyles(', placementStart);
const createSummary = new Function('report', 'formatChannelLabel',
  source.slice(start, end) + source.slice(placementStart, placementEnd)
  + '\nreturn { getChannelNeighboursInWeek, consolidateChannelReportRows };');
const channels = ['INDIA TV', 'AAJ TAK', 'NEWS 18 INDIA', 'REPUBLIC BHARAT'];
channels.forEach((channel) => {
  const data = { records: [
    row(channel, 711), row(` ${channel.toLowerCase()} `, 711),
    row('LOWER LCN', 709), row('HIGHER LCN', 713),
    row('SAME LCN', 711), row('DISTANT LOWER', 705), row('DISTANT HIGHER', 720),
    row('WRONG CITY', 712, 'City B'), row('WRONG MSO', 710, 'City A', 'DTH'),
  ] };
  const summary = createSummary(data, (value) => value.trim().toUpperCase());
  const getPair = (week = 'Current', frequency = 711) => summary.getChannelNeighboursInWeek(
    channel, 'Market', 'Headend', week, 'City A', 'HITS', frequency);
  assert.equal(getPair().above, 'LOWER LCN');
  assert.equal(getPair().below, 'HIGHER LCN', 'Missing 712 skips to 713');
  data.records = [...data.records, row('IMMEDIATE LOWER', 710), row('IMMEDIATE HIGHER', '712')];
  assert.equal(getPair().above, 'IMMEDIATE LOWER');
  assert.equal(getPair().below, 'IMMEDIATE HIGHER', 'Occupied 712 wins over 713');
  data.records.forEach((r) => { r.frequencies.Previous = null; });
  data.records.push({ ...row(channel, 711), frequencies: { Previous: 700, Current: 711 } });
  data.records.push({ ...row('PREVIOUS ABOVE', 699), frequencies: { Previous: 699 } });
  data.records.push({ ...row('PREVIOUS BELOW', 702), frequencies: { Previous: 702 } });
  const exported = summary.consolidateChannelReportRows([{
    channel_name: channel, market: 'Market', head_end: 'Headend', city: 'City A', mso_type: 'HITS',
    previousFrequency: 700, currentFrequency: 711, previousRank: 2, currentRank: 2,
  }], ['Previous', 'Current']);
  assert.equal(exported.length, 1);
  assert.equal(exported[0].changeText.includes('previously it was placed between PREVIOUS ABOVE & PREVIOUS BELOW'), true);
  assert.equal(exported[0].changeText.includes('between IMMEDIATE LOWER & IMMEDIATE HIGHER'), true,
    'Excel summary text must use both frequency neighbours for the corresponding week');
  assert.equal(getPair('Current', null).above, '', 'An unavailable target has no neighbours');
});
console.log('Excel summary neighbour checks passed for all four channels.');
