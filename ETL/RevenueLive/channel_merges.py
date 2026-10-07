"""Reversible reporting identities; never move records or grant channel access."""
import hashlib
import json
from flask import g, jsonify, request

METRICS = ('views', 'impressions', 'ad', 'other', 'total')


def reporting_scope(connection, permitted):
    channels = {row['id']: dict(row) for row in permitted}
    groups = {}
    for row in connection.execute('SELECT source_id,target_id FROM channel_merges'):
        groups.setdefault(row['target_id'], set()).add(row['source_id'])
    mapping = {cid: cid for cid in channels}
    for target, sources in groups.items():
        # Partial-access users retain their original channels and original scope.
        if sources | {target} <= channels.keys():
            for source in sources:
                mapping[source] = target
    return channels, mapping


def aggregate(rows, channels, mapping):
    if all(source == target for source, target in mapping.items()):
        return rows
    result = {}
    for row in rows:
        target = mapping[row['channel_id']]
        key = (row['day'], target)
        if key not in result:
            result[key] = dict(day=row['day'], channel_id=target,
                               channel=channels[target]['name'], **dict.fromkeys(METRICS, 0))
        for metric in METRICS:
            result[key][metric] += row[metric]
    return sorted(result.values(), key=lambda row: (row['day'], row['channel'].lower()), reverse=True)


def install(app, db, require, log, InvalidData):
    def preview(source, target):
        if type(source) is not int or type(target) is not int or source == target:
            raise InvalidData('Choose two different channels.')
        active = {row['id']: row['name'] for row in db().execute(
            'SELECT * FROM channels WHERE id NOT IN (SELECT channel_id FROM archived_channels)')}
        if source not in active or target not in active:
            raise InvalidData('Both channels must be active.')
        links = [dict(row) for row in db().execute('SELECT source_id,target_id FROM channel_merges ORDER BY source_id')]
        if any(row['source_id'] in (source, target) or row['target_id'] == source for row in links):
            raise InvalidData('Undo existing merges for this source first. A destination cannot itself be merged.')
        members = {source, target} | {row['source_id'] for row in links if row['target_id'] == target}
        marks = ','.join('?' for _ in members)
        rows = [dict(row) for row in db().execute(
            f'SELECT * FROM records WHERE channel_id IN ({marks}) ORDER BY day,channel_id', tuple(sorted(members)))]
        source_rows = [row for row in rows if row['channel_id'] == source]
        destination_rows = [row for row in rows if row['channel_id'] != source]
        overlaps = sorted({row['day'] for row in source_rows} & {row['day'] for row in destination_rows})
        signatures = {(row['day'], *(row[m] for m in METRICS)) for row in destination_rows}
        exact = sorted({row['day'] for row in source_rows
                        if (row['day'], *(row[m] for m in METRICS)) in signatures})
        token = hashlib.sha256(json.dumps([source, target, active[source], active[target], links, rows], sort_keys=True).encode()).hexdigest()
        return dict(source=source, target=target, source_name=active[source], target_name=active[target],
                    source_records=len(source_rows), destination_records=len(destination_rows),
                    upload_count=len({row['upload_id'] for row in rows if row['upload_id']}),
                    overlap_dates=overlaps, exact_match_dates=exact, token=token,
                    rows=[{k: row[k] for k in ('day', 'channel_id', *METRICS)} for row in rows])

    @app.get('/api/admin/channel-merges')
    @require('admin')
    def listing():
        return jsonify(rows=[dict(row) for row in db().execute(
            'SELECT m.source_id,m.target_id,s.name AS source_name,t.name AS target_name '
            'FROM channel_merges m JOIN channels s ON s.id=m.source_id JOIN channels t ON t.id=m.target_id')])

    @app.post('/api/admin/channel-merges/preview')
    @require('admin')
    def review():
        body = request.get_json(silent=True) or {}
        return jsonify(preview(body.get('source'), body.get('target')))

    @app.post('/api/admin/channel-merges')
    @require('admin')
    def merge():
        body = request.get_json(silent=True) or {}
        db().begin_write()
        plan = preview(body.get('source'), body.get('target'))
        if body.get('token') != plan['token']:
            raise InvalidData('Data changed. Preview the merge again.')
        if plan['exact_match_dates']:
            raise InvalidData('Exact matching records need correction through upload review before merging. Nothing was changed.')
        if body.get('confirm_sum') is not True:
            raise InvalidData('Confirm that the entries are separate activities and should be added together.')
        db().execute('INSERT INTO channel_merges(source_id,target_id) VALUES (?,?)', (plan['source'], plan['target']))
        log('channel_merged', json.dumps({k: v for k, v in plan.items() if k != 'rows'}, sort_keys=True))
        db().commit()
        return jsonify(ok=True)

    @app.delete('/api/admin/channel-merges/<int:source>')
    @require('admin')
    def undo(source):
        db().begin_write()
        link = db().execute('SELECT * FROM channel_merges WHERE source_id=?', (source,)).fetchone()
        if not link:
            raise InvalidData('This channel is not merged.')
        db().execute('DELETE FROM channel_merges WHERE source_id=?', (source,))
        log('channel_merge_undone', json.dumps(dict(link), sort_keys=True))
        db().commit()
        return jsonify(ok=True)
