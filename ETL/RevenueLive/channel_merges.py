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
    def preview(sources, target):
        if type(sources) is int:
            sources = [sources]
        if (not isinstance(sources, list) or not sources
                or any(type(cid) is not int for cid in sources) or type(target) is not int):
            raise InvalidData('Choose source channels and one main channel.')
        sources = sorted(set(sources))
        if target in sources:
            raise InvalidData('The main channel cannot also be a source.')
        names = {row['id']: row['name'] for row in db().execute('SELECT * FROM channels')}
        archived = {row['channel_id'] for row in db().execute('SELECT channel_id FROM archived_channels')}
        if any(cid not in names or cid in archived for cid in [*sources, target]):
            raise InvalidData('All selected channels must be active.')
        links = [dict(row) for row in db().execute('SELECT source_id,target_id FROM channel_merges ORDER BY source_id')]
        if any(row['source_id'] in [*sources, target] or row['target_id'] in sources for row in links):
            raise InvalidData('Undo existing merges for these sources first. A destination cannot itself be merged.')
        existing = {row['source_id'] for row in links if row['target_id'] == target}
        members = set(sources) | {target} | existing
        marks = ','.join('?' for _ in members)
        rows = [dict(row) for row in db().execute(
            f'SELECT * FROM records WHERE channel_id IN ({marks}) ORDER BY day,channel_id', tuple(sorted(members)))]
        source_rows = [row for row in rows if row['channel_id'] in sources]
        destination_rows = [row for row in rows if row['channel_id'] not in sources]
        days, signatures = {}, {}
        for row in rows:
            days.setdefault(row['day'], set()).add(row['channel_id'])
            signature = (row['day'], *(row[m] for m in METRICS))
            signatures.setdefault(signature, set()).add(row['channel_id'])
        overlaps = sorted(day for day, ids in days.items() if len(ids) > 1 and ids.intersection(sources))
        exact = sorted({signature[0] for signature, ids in signatures.items()
                        if len(ids) > 1 and ids.intersection(sources)})
        token = hashlib.sha256(json.dumps(
            [sources, target, {cid: names[cid] for cid in sorted(members)}, links, rows],
            sort_keys=True).encode()).hexdigest()
        return dict(source=sources[0] if len(sources) == 1 else None, sources=sources, target=target,
                    source_name=names[sources[0]] if len(sources) == 1 else None,
                    source_channels=[dict(id=cid, name=names[cid],
                        records=sum(row['channel_id'] == cid for row in source_rows)) for cid in sources],
                    existing_channels=[dict(id=cid, name=names[cid]) for cid in sorted(existing)],
                    target_name=names[target], source_records=len(source_rows),
                    destination_records=len(destination_rows),
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
        return jsonify(preview(body.get('sources', body.get('source')), body.get('target')))

    @app.post('/api/admin/channel-merges')
    @require('admin')
    def merge():
        body = request.get_json(silent=True) or {}
        db().begin_write()
        plan = preview(body.get('sources', body.get('source')), body.get('target'))
        if body.get('token') != plan['token']:
            raise InvalidData('Data changed. Preview the merge again.')
        if plan['exact_match_dates']:
            raise InvalidData('Exact matching records need correction through upload review before merging. Nothing was changed.')
        if body.get('confirm_sum') is not True:
            raise InvalidData('Confirm that the entries are separate activities and should be added together.')
        for source in plan['sources']:
            db().execute('INSERT INTO channel_merges(source_id,target_id) VALUES (?,?)', (source, plan['target']))
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
