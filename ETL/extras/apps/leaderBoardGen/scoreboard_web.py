"""Browser host for scoreboard_app.py using only the Python standard library."""

from __future__ import annotations

import base64
import copy
import csv
import io
import importlib.util
import ipaddress
import hashlib
import hmac
import secrets
import unicodedata
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse


MAX_REQUEST_BYTES = 35 * 1024 * 1024
SESSION_TIMEOUT_SECONDS = 30


class ProjectConflict(ValueError):
    pass
IMAGE_MIME_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/avif": ".avif",
}


class ScoreboardWebRuntime:
    def __init__(self, core, upload_dir: Path | None = None):
        self.core = core
        self.app_dir = Path(core.__file__).resolve().parent
        self.web_file = self.app_dir / "scoreboard_web.html"
        self.upload_dir = self._select_upload_dir(upload_dir)
        self.project_dir = self.upload_dir.parent / "projects"
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.live_output = None
        self.live_preset = None
        self.live_output_name = None
        self.live_owner_id = None
        self._capability_lock = threading.Lock()
        self._capabilities = None
        self._capability_time = 0
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.project_unlocks = {}
        self.project_attempts = {}
        self.library_dir = self.upload_dir.parent / 'templates'
        self.library_dir.mkdir(parents=True, exist_ok=True)
        self.library_changed = threading.Condition(self.lock)
        self.library_revision = uuid.uuid4().hex
        self.library_warnings = []
        self.on_air = None
        self.program_revision = uuid.uuid4().hex
        self.program_name = ''
        self.program_frame = None
        self.media_playback = None
        spec = importlib.util.spec_from_file_location('scoreboard_media', self.app_dir / 'scoreboard_media.py')
        self.media = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.media)
        self.credentials_path = self.upload_dir.parent / 'editor_credentials.json'
        if not self.credentials_path.exists():
            self._write_credentials('veto', 'veto@spark')

    def _write_credentials(self, username, password):
        username = str(username).strip()
        if not username or len(username) > 80:
            raise ValueError('Enter an editor ID of 1 to 80 characters.')
        record = dict(username=username, password=self._password_record(password))
        temporary = self.credentials_path.with_name('.credentials-' + uuid.uuid4().hex + '.tmp')
        try:
            with temporary.open('w', encoding='utf-8') as stream:
                json.dump(record, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.credentials_path)
        finally:
            temporary.unlink(missing_ok=True)

    def _check_credentials(self, payload, remote_address):
        now = time.monotonic()
        attempts = [t for t in self.project_attempts.get(remote_address, []) if now - t < 60]
        if len(attempts) >= 5:
            raise ValueError('Too many attempts. Wait one minute before retrying.')
        record = json.loads(self.credentials_path.read_text(encoding='utf-8'))
        password = payload.get('password', '')
        if not isinstance(password, str) or len(password) > 128:
            password = ''
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(),
            bytes.fromhex(record['password']['salt']), 310000).hex()
        if (str(payload.get('username', '')) != record['username']
                or not hmac.compare_digest(digest, record['password']['digest'])):
            self.project_attempts[remote_address] = attempts + [now]
            raise ValueError('Incorrect editor ID or password.')
        self.project_attempts.pop(remote_address, None)

    def manage_project(self, payload, remote_address):
        if not self._is_local_request(remote_address):
            raise PermissionError('Project administration is available on the hosted PC only.')
        with self.lock:
            self._check_credentials(payload, remote_address)
            if payload.get('action') == 'credentials':
                self._write_credentials(payload.get('new_username'), payload.get('new_password'))
                self.project_unlocks.clear()
                return {'ok': True}
            document = self.open_project(payload.get('id'))
            if payload.get('revision') != document['revision']:
                raise ProjectConflict('Project changed. Refresh the project list.')
            path = self._project_path(document['id'])
            if payload.get('action') == 'delete':
                # Retain a recoverable copy; uploaded assets may be used by other projects.
                archive = self.project_dir / 'deleted'
                archive.mkdir(exist_ok=True)
                os.replace(path, archive / (document['id'] + '-' + uuid.uuid4().hex + '.json'))
                self.project_unlocks = {k:v for k,v in self.project_unlocks.items() if v['id'] != document['id']}
                return {'ok': True}
            if payload.get('action') != 'rename':
                raise ValueError('Unknown project action.')
            return self.save_project({**document, 'name':payload.get('name'),
                'client_id':payload.get('client_id')}, remote_address, _authorized=True)

    def _select_upload_dir(self, requested: Path | None) -> Path:
        candidates = []
        if requested is not None:
            candidates.append(Path(requested))
        configured = os.environ.get("SCOREBOARD_WEB_UPLOAD_DIR", "").strip()
        if configured:
            candidates.append(Path(configured))
        candidates.append(self.app_dir / "data" / "uploads")
        if len(self.app_dir.parents) > 2:
            candidates.append(
                self.app_dir.parents[2] / "output" / "scoreboard_web" / "uploads"
            )
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            candidates.append(Path(local_app_data) / "Veto" / "ScoreboardMaker" / "uploads")
        candidates.append(Path(tempfile.gettempdir()) / "VetoScoreboardMaker" / "uploads")

        failures = []
        for candidate in candidates:
            try:
                candidate = candidate.expanduser().resolve()
                candidate.mkdir(parents=True, exist_ok=True)
                probe = candidate / f".write-check-{uuid.uuid4().hex}"
                probe.write_bytes(b"ok")
                probe.unlink()
                return candidate
            except OSError as exc:
                failures.append(f"{candidate}: {exc}")
        raise RuntimeError(
            "No writable scoreboard upload folder was found. " + " | ".join(failures)
        )

    def list_templates(self):
        """Expose legacy presets read-only alongside the create-only flat library."""
        entries = []
        with self.lock:
            warnings = []
            for path in self.project_dir.glob('*.json'):
                try:
                    document = self.open_project(path.stem)
                    project_entries = []
                    for template, presets in document['presets'].items():
                        for preset in presets:
                            config = preset['config']
                            player = str(preset.get('player') or config.get('player_name') or preset.get('name') or document['name'])
                            country = str(preset.get('country') or config.get('country') or config.get('country_a') or '')
                            project_entries.append(dict(id='legacy-' + path.stem + '-' + preset['id'],
                                template=template, player=player, country=country, config=config))
                    entries.extend(project_entries)
                except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError):
                    warnings.append('Unreadable project: ' + path.name)
            for path in self.library_dir.glob('*.json'):
                try:
                    item = json.loads(path.read_text(encoding='utf-8'))
                    if item['id'] != path.stem or not re.fullmatch(r'[a-f0-9]{32}',item['id']):
                        raise ValueError('Invalid template ID')
                    if not isinstance(item['player'],str) or not isinstance(item['country'],str):
                        raise ValueError('Invalid template metadata')
                    item['config'] = self.normalized_config(item['template'], item['config'])
                    entries.append(item)
                except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError):
                    warnings.append('Unreadable template: ' + path.name)
            self.library_warnings = warnings
        for item in entries:
            item['edit_revision'] = self._template_revision(item)
        return sorted(entries, key=lambda item:(item['template'], self._name_key(item['country']), self._name_key(item['player'])))

    @staticmethod
    def _template_revision(item):
        content = {key:item[key] for key in ('id','template','player','country','config')}
        return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def update_template(self, payload, remote_address):
        """Update one preset, with credentials and optimistic conflict protection."""
        with self.lock:
            self._check_credentials(payload, remote_address)
            item = next((entry for entry in self.list_templates() if entry['id'] == payload.get('id')), None)
            if item is None:
                raise ProjectConflict('Saved template no longer exists.')
            if payload.get('edit_revision') != item['edit_revision']:
                raise ProjectConflict('Another operator changed this template. Your preview is retained; reopen the saved version before updating.')
            config = self.normalized_config(item['template'], payload.get('config', {}))
            if item['template'] == 't8' and not config.get('media_path'):
                raise ValueError('Upload an image or video first.')
            def portable(value):
                if isinstance(value, dict):
                    return {key:portable(child) for key,child in value.items()}
                if isinstance(value, list):
                    return [portable(child) for child in value]
                if isinstance(value, str) and value.startswith(str(self.upload_dir) + os.sep):
                    return Path(value).name
                return value
            if item['id'].startswith('legacy-'):
                _, project_id, preset_id = item['id'].split('-')
                path = self._project_path(project_id)
                document = json.loads(path.read_text(encoding='utf-8'))
                presets = self._project_presets(document)
                preset = next(p for p in presets[item['template']] if p['id'] == preset_id)
                preset['config'] = portable(config)
                document['presets'] = portable(presets)
                document['revision'] = int(document.get('revision', 0)) + 1
            else:
                path = self.library_dir / (item['id'] + '.json')
                document = json.loads(path.read_text(encoding='utf-8'))
                document['config'] = portable(config)
            document['updated_at'] = datetime.now(timezone.utc).isoformat()
            # Preserve the previous version before the atomic replacement.
            history = path.parent / 'history'
            history.mkdir(exist_ok=True)
            backup = history / (path.stem + '-' + uuid.uuid4().hex + '.json')
            with backup.open('xb') as stream:
                stream.write(path.read_bytes())
                stream.flush()
                os.fsync(stream.fileno())
            temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
            try:
                with temporary.open('w', encoding='utf-8') as stream:
                    json.dump(document, stream, ensure_ascii=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
            self.library_revision = uuid.uuid4().hex
            self.library_changed.notify_all()
            updated = next(entry for entry in self.list_templates() if entry['id'] == item['id'])
            return {'saved':True, 'item':updated}

    def library_snapshot(self):
        with self.lock:
            entries = self.list_templates()
            return {'templates':entries, 'revision':self.library_revision,
                    'warnings':list(self.library_warnings)}

    def wait_for_library(self, revision, timeout=20):
        # Waiting releases the runtime lock: SDI controls remain independent.
        with self.library_changed:
            self.library_changed.wait_for(lambda:self.library_revision != revision, timeout=timeout)
            return {'revision':self.library_revision}

    def save_template(self, payload, remote_address):
        template = payload.get('template')
        config = self.normalized_config(template, payload.get('config', {}))
        player, country = (str(payload.get(field, '')).strip() for field in ('player','country'))
        if template == 't8':
            country = ''
            if not config.get('media_path'):
                raise ValueError('Upload an image or video first.')
        if not player or (not country and template != 't8') or max(len(player),len(country)) > 100:
            raise ValueError('Enter player name and country (at most 100 characters each).')
        with self.lock:
            entries = self.list_templates()
            if self.library_warnings:
                raise ValueError('Library needs host attention before saving: ' + '; '.join(self.library_warnings))
            for item in entries:
                if (item['template'] == template and self._name_key(item['country']) == self._name_key(country)
                        and self._name_key(item['player']) == self._name_key(player)):
                    return {'saved':False, 'existing':item}
            def portable(value):
                if isinstance(value, dict):
                    return {k:portable(v) for k,v in value.items()}
                if isinstance(value, list):
                    return [portable(v) for v in value]
                if isinstance(value, str) and value.startswith(str(self.upload_dir) + os.sep):
                    return Path(value).name
                return value
            item = dict(id=uuid.uuid4().hex, template=template, player=player, country=country,
                config=portable(config), updated_at=datetime.now(timezone.utc).isoformat())
            path = self.library_dir / (item['id'] + '.json')
            temporary = path.with_suffix('.tmp')
            try:
                with temporary.open('w',encoding='utf-8') as stream:
                    json.dump(item,stream,ensure_ascii=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary,path)
            finally:
                temporary.unlink(missing_ok=True)
            self.library_revision = uuid.uuid4().hex
            self.library_changed.notify_all()
            public_item = {**item, 'config':config}
            public_item['edit_revision'] = self._template_revision(public_item)
            return {'saved':True,'item':public_item}

    def storage_status(self) -> Dict[str, Any]:
        return {
            "path": str(self.upload_dir),
            "projects": str(self.project_dir),
            "writable": self.upload_dir.is_dir() and os.access(self.upload_dir, os.W_OK),
        }

    def _project_path(self, project_id):
        if not isinstance(project_id, str) or not re.fullmatch(r"[a-f0-9]{32}", project_id):
            raise ValueError("Invalid project ID.")
        return self.project_dir / (project_id + ".json")

    @staticmethod
    def _project_metadata(document):
        result = {key: document[key] for key in (
            "id", "name", "revision", "updated_at", "updated_by", "active_template"
        )}
        result['protected'] = True
        return result

    def list_projects(self):
        projects = []
        with self.lock:
            for path in self.project_dir.glob("*.json"):
                try:
                    projects.append(self._project_metadata(json.loads(path.read_text(encoding="utf-8"))))
                except (OSError, ValueError, KeyError):
                    continue
        return sorted(projects, key=lambda item: item["updated_at"], reverse=True)

    def open_project(self, project_id):
        with self.lock:
            path = self._project_path(project_id)
            if not path.is_file():
                raise ValueError("Project no longer exists.")
            document = json.loads(path.read_text(encoding="utf-8"))
        document["templates"] = {
            key: self.normalized_config(key, value)
            for key, value in document["templates"].items()
        }
        document.pop('_edit_password', None)
        document['protected'] = True
        document['presets'] = self._project_presets(document)
        return document

    def _project_presets(self, document):
        """Expose legacy template snapshots as presets without changing disk files."""
        if 'presets' in document:
            return {
                key: [{**item, 'config': self.normalized_config(key, item['config'])}
                      for item in document.get('presets', {}).get(key, [])]
                for key in self.core.WEB_TEMPLATE_KEYS
            }
        return {
            key: [dict(id=uuid.uuid5(uuid.NAMESPACE_URL, document['id'] + key).hex,
                       name='Original', country=str(cfg.get('country', '')),
                       player=str(cfg.get('player_name', '')),
                       config=self.normalized_config(key, cfg))]
            for key, cfg in document['templates'].items()
        }

    def lock_project(self, payload):
        with self.lock:
            token = payload.get('edit_token', '')
            grant = self.project_unlocks.get(token)
            if grant and grant['client'] == payload.get('client_id'):
                self.project_unlocks.pop(token, None)
        return {'locked': True}

    def save_preset(self, payload, remote_address):
        template = payload.get('template')
        config = self.normalized_config(template, payload.get('config', {}))
        fields = {key: str(payload.get(key, '')).strip() for key in ('name','country','player')}
        if not fields['name'] or any(len(value) > 100 for value in fields.values()):
            raise ValueError('Enter a preset name; each preset field must be at most 100 characters.')
        if template == 't6' and (not config['player_name'].strip() or not config['country'].strip()):
            raise ValueError('Enter the player name and country.')
        if template == 't6':
            fields['player'], fields['country'] = config['player_name'], config['country']
        with self.lock:
            document = self.open_project(payload.get('project_id'))
            if payload.get('revision') != document['revision']:
                raise ProjectConflict('Another operator saved this project. Reopen it before saving your preset.')
            presets = document['presets']
            entries = presets.setdefault(template, [])
            preset_id = payload.get('preset_id') or uuid.uuid4().hex
            if not isinstance(preset_id, str) or not re.fullmatch(r'[a-f0-9]{32}', preset_id):
                raise ValueError('Invalid preset ID.')
            previous = next((item for item in entries if item['id'] == preset_id), None)
            if payload.get('preset_id') and previous is None:
                raise ProjectConflict('Preset no longer exists. Refresh the project.')
            identity = tuple(self._name_key(fields[key]) for key in ('name','country','player'))
            if any(item['id'] != preset_id and tuple(self._name_key(item.get(key, ''))
                   for key in ('name','country','player')) == identity for item in entries):
                raise ProjectConflict('This template already has that preset. Select it to update, or choose a different name.')
            item = dict(id=preset_id, **fields, config=config,
                        updated_at=datetime.now(timezone.utc).isoformat())
            if previous:
                entries[entries.index(previous)] = item
            else:
                entries.append(item)
            document['templates'][template] = config
            token = payload.get('edit_token', '')
            grant = copy.deepcopy(self.project_unlocks.get(token))
            metadata = self.save_project(dict(
                id=document['id'], name=document['name'], revision=payload.get('revision'),
                templates=document['templates'], active_template=template,
                client_id=payload.get('client_id'), edit_token=token,
                new_password=payload.get('new_password'),
            ), remote_address, presets=presets, _authorized=previous is None)
            # Keep the saving editor's grant; other editors must refresh stale revisions.
            if grant and grant['expires'] > time.monotonic():
                grant['revision'] = metadata['revision']
                self.project_unlocks[token] = grant
            return {'project': self.open_project(document['id']), 'preset_id': preset_id}

    @staticmethod
    def _name_key(name):
        return ' '.join(unicodedata.normalize('NFKC', name).split()).casefold()

    @staticmethod
    def _password_record(password):
        if not isinstance(password, str) or not 6 <= len(password) <= 128:
            raise ValueError('Use an edit password of 6 to 128 characters.')
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 310000)
        return {'salt': salt, 'digest': digest.hex()}

    def unlock_project(self, payload, remote_address):
        client = self._clean_client_id(payload.get('client_id'))
        if not client:
            raise ValueError('Register an operator session first.')
        project_id = payload.get('id')
        with self.lock:
            document = json.loads(self._project_path(project_id).read_text(encoding='utf-8'))
            self._check_credentials(payload, remote_address)
            now = time.monotonic()
            self.project_unlocks = {key: value for key, value in self.project_unlocks.items() if value['expires'] > now}
            token = secrets.token_urlsafe(32)
            self.project_unlocks[token] = dict(id=project_id, client=client,
                revision=document['revision'], expires=now + 1800)
            return {'edit_token': token, 'revision': document['revision']}

    def save_project(self, payload, remote_address, *, presets=None, _authorized=False):
        name = str(payload.get("name", "")).strip()
        if not name or len(name) > 100:
            raise ValueError("Enter a project name of 1 to 100 characters.")
        incoming = payload.get("templates")
        if not isinstance(incoming, dict):
            raise ValueError("Project templates are missing.")
        templates = {key: self.normalized_config(key, incoming.get(key, {}))
                     for key in self.core.WEB_TEMPLATE_KEYS}
        # Store generated image filenames so the entire data folder is movable.
        def portable(value):
            if isinstance(value, dict):
                return {key: portable(item) for key, item in value.items()}
            if isinstance(value, list):
                return [portable(item) for item in value]
            if isinstance(value, str) and value.startswith(str(self.upload_dir) + os.sep):
                return Path(value).name
            return value
        active = payload.get("active_template", "t1")
        if active not in templates:
            raise ValueError("Unknown active template.")
        session = self.touch_session(payload.get("client_id"), remote_address)
        with self.lock:
            project_id = payload.get("id") or uuid.uuid4().hex
            path = self._project_path(project_id)
            previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
            if payload.get("id") and (previous is None or payload.get("revision") != previous["revision"]):
                raise ProjectConflict("Another operator saved this project. Reopen it or save a copy to keep your changes.")
            if previous and not _authorized:
                grant = self.project_unlocks.get(payload.get('edit_token'), {})
                if (grant.get('id') != project_id or grant.get('client') != payload.get('client_id')
                    or grant.get('revision') != previous['revision'] or grant.get('expires', 0) <= time.monotonic()):
                    raise ProjectConflict('Project is locked. Unlock with its edit password before saving.')
            if any(item['id'] != project_id and self._name_key(item['name']) == self._name_key(name)
                   for item in self.list_projects()):
                raise ProjectConflict('A project with this name already exists. Open it or choose a different name.')
            if previous and name != previous['name'] and not self._is_local_request(remote_address):
                raise PermissionError('Only the hosted PC can rename a project.')
            password_record = None
            if presets is None:
                presets = self._project_presets(previous) if previous else {key: [] for key in templates}
                if not previous and isinstance(payload.get('presets'), dict):
                    for key in templates:
                        entries = payload['presets'].get(key, [])
                        if not isinstance(entries, list):
                            raise ValueError('Invalid preset list.')
                        identities = set()
                        for entry in entries:
                            if not isinstance(entry, dict):
                                raise ValueError('Invalid preset.')
                            fields = {field: str(entry.get(field, '')).strip()
                                      for field in ('name', 'country', 'player')}
                            identity = tuple(self._name_key(fields[field]) for field in fields)
                            if not fields['name'] or any(len(value) > 100 for value in fields.values()):
                                raise ValueError('Invalid preset name or metadata.')
                            if identity in identities:
                                raise ProjectConflict('Duplicate preset in imported project.')
                            identities.add(identity)
                            presets[key].append(dict(id=uuid.uuid4().hex, **fields,
                                config=self.normalized_config(key, entry.get('config', {}))))
                elif not previous:
                    presets[active] = [dict(id=uuid.uuid4().hex, name='Original',
                        player=str(templates[active].get('player_name', '')),
                        country=str(templates[active].get('country', '')), config=templates[active])]
            document = dict(version=4, id=project_id, name=name,
                            revision=(previous["revision"] + 1 if previous else 1),
                            updated_at=datetime.now(timezone.utc).isoformat(),
                            updated_by=session["name"] if session else "Operator",
                            active_template=active, templates=portable(templates), presets=portable(presets))
            if password_record:
                document['_edit_password'] = password_record
            temporary = path.with_name("." + uuid.uuid4().hex + ".tmp")
            try:
                with temporary.open("w", encoding="utf-8") as stream:
                    json.dump(document, stream, ensure_ascii=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
            self.project_unlocks = {key: value for key, value in self.project_unlocks.items()
                                    if value['id'] != project_id and value['expires'] > time.monotonic()}
        return self._project_metadata(document)

    @staticmethod
    def _clean_client_id(value: Any) -> str:
        client_id = str(value or "").strip()
        return client_id if re.fullmatch(r"[A-Za-z0-9-]{8,80}", client_id) else ""

    @staticmethod
    def _clean_display_name(value: Any, client_id: str) -> str:
        name = re.sub(r"\s+", " ", str(value or "")).strip()[:40]
        return name or f"Operator {client_id[:4].upper()}"

    @staticmethod
    def _is_local_request(remote_address: str) -> bool:
        try:
            return ipaddress.ip_address(remote_address).is_loopback
        except ValueError:
            return False

    def _purge_sessions_locked(self) -> None:
        cutoff = time.monotonic() - SESSION_TIMEOUT_SECONDS
        stale = [
            client_id for client_id, session in self.sessions.items()
            if session["last_seen"] < cutoff and client_id != self.live_owner_id
        ]
        for client_id in stale:
            self.sessions.pop(client_id, None)

    def register_session(
        self, client_id: Any, display_name: Any, remote_address: str,
    ) -> Dict[str, Any]:
        client_id = self._clean_client_id(client_id) or uuid.uuid4().hex
        now = time.monotonic()
        with self.lock:
            existing = self.sessions.get(client_id, {})
            session = {
                "id": client_id,
                "name": self._clean_display_name(display_name, client_id),
                "address": remote_address,
                "priority": int(existing.get("priority", 50)),
                "last_seen": now,
            }
            self.sessions[client_id] = session
            self._purge_sessions_locked()
            return self._public_session(session)

    def touch_session(self, client_id: Any, remote_address: str) -> Dict[str, Any] | None:
        client_id = self._clean_client_id(client_id)
        if not client_id:
            return None
        with self.lock:
            session = self.sessions.get(client_id)
            if session is None:
                session = {
                    "id": client_id,
                    "name": self._clean_display_name("", client_id),
                    "address": remote_address,
                    "priority": 50,
                    "last_seen": time.monotonic(),
                }
                self.sessions[client_id] = session
            else:
                session["address"] = remote_address
                session["last_seen"] = time.monotonic()
            self._purge_sessions_locked()
            return self._public_session(session)

    def _public_session(self, session: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": session["id"],
            "name": session["name"],
            "address": session["address"],
            "priority": session["priority"],
            "live_owner": session["id"] == self.live_owner_id,
            "age_seconds": max(0, int(time.monotonic() - session["last_seen"])),
        }

    def session_status(self, client_id: Any, remote_address: str) -> Dict[str, Any]:
        requester = self.touch_session(client_id, remote_address)
        with self.lock:
            sessions = sorted(
                (self._public_session(session) for session in self.sessions.values()),
                key=lambda item: (-item["priority"], item["name"].casefold()),
            )
        return {
            "requester": requester,
            "can_manage": self._is_local_request(remote_address),
            "session_timeout_seconds": SESSION_TIMEOUT_SECONDS,
            "sessions": sessions,
        }

    def set_session_priority(
        self, target_id: Any, priority: Any, remote_address: str,
    ) -> Dict[str, Any]:
        if not self._is_local_request(remote_address):
            raise PermissionError("Priorities can only be changed from this computer.")
        target_id = self._clean_client_id(target_id)
        try:
            priority = max(0, min(100, int(priority)))
        except (TypeError, ValueError) as exc:
            raise ValueError("Priority must be from 0 to 100.") from exc
        with self.lock:
            session = self.sessions.get(target_id)
            if session is None:
                raise ValueError("That user is no longer online.")
            session["priority"] = priority
            return self._public_session(session)

    def output_capabilities(self):
        # Isolate driver discovery from the renderer and bound hangs in vendor code.
        with self._capability_lock:
            if self._capabilities is not None and time.monotonic()-self._capability_time < 30:
                return copy.deepcopy(self._capabilities)
            try:
                # The bundle's Python startup shim adds these again in the child.
                # Inheriting them can deadlock plugin discovery on Windows.
                probe_env={key:value for key,value in os.environ.items()
                           if not key.startswith(('GST_','GI_','PYGI_')) and key!='PYTHONPATH'}
                result=subprocess.run([sys.executable,str(self.app_dir/'scoreboard_output_probe.py')],
                    capture_output=True,text=True,timeout=12,env=probe_env,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                if result.returncode:
                    raise ValueError('Driver probe exited unsuccessfully.')
                data=json.loads(result.stdout)
                if not isinstance(data.get('devices'),list):
                    raise ValueError('Invalid driver response.')
            except (OSError,ValueError,subprocess.TimeoutExpired) as error:
                data=dict(devices=[],error='Cannot verify output hardware: '+str(error),switcher_detected=False)
            self._capabilities=data
            self._capability_time=time.monotonic()
            return copy.deepcopy(data)

    def bootstrap(self) -> Dict[str, Any]:
        return {
            "shared_projects": False,
            "template_library": True,
            "project_edit_locks": True,
            "template_presets": True,
            "template_names": dict(zip(
                self.core.WEB_TEMPLATE_KEYS, self.core.WEB_TEMPLATE_NAMES
            )),
            "defaults": copy.deepcopy(self.core.DEFAULT_CONFIGS),
            "text_targets": {
                key: [{"key": role, "label": label} for role, label in targets]
                for key, targets in self.core.TEXT_STYLE_TARGETS.items()
            },
            "fonts": list(self.core.FONT_CHOICES),
            "text_cases": list(self.core.TEXT_CASE_CHOICES),
            "video_presets": list(self.core.VIDEO_EXPORT_PRESETS),
            "mp4_presets": list(self.core.MP4_EXPORT_PRESETS),
            "decklink_outputs": self.core.DECKLINK_OUTPUTS,
            "canvas_sizes": {
                "t1": list(self.core.T1_SIZES),
                "t2": list(self.core.T2_SIZES),
                "t3": list(self.core.T3_SIZES),
                "t4": list(self.core.T4_SIZES),
                "t5": list(self.core.T5_SIZES),
                "t6": list(self.core.T6_SIZES),
                "t7": list(self.core.T7_SIZES),
                "t8": list(self.core.T8_SIZES),
                "t9": list(self.core.T9_SIZES),
                **{key:list(self.core.BROADCAST_SIZES) for key in ('t10','t11','t12')},
            },
            "qualifier_countries": sorted(set(json.loads((self.app_dir / 'country_flags.json').read_text(encoding='utf-8-sig')).values()) | set(self.core.QUALIFIER_ALPHA3.values())),
            "custom_text_boxes": True,
            "program_monitor": True,
        }

    def normalized_config(self, template: str, value: Any) -> Dict[str, Any]:
        if template not in self.core.WEB_TEMPLATE_KEYS:
            raise ValueError("Unknown scoreboard template.")
        config = self.core.normalise_project_configs({template: value})[template]
        # Browser clients choose a supported canvas, never an internal multiplier.
        config.pop('_render_scale', None)
        self._validate_image_paths(template, config)
        return config

    def _validate_image_paths(self, template: str, config: Dict[str, Any]) -> None:
        keys = {
            "t1": ("photo_path", "player_path", "logo_path"),
            "t2": ("photo_a", "photo_b", "logo_path"),
            "t3": ("photo_a", "photo_b", "logo_path"),
            "t4": ("logo_path",),
            "t5": ("background_path", "player_path"),
            "t6": ("player_path",),
            "t7": (),
            "t8": ('media_path','poster_path'),
            "t9": ('photo_a','photo_b'),
            "t10": ('photo_a','photo_b','background_path','logo_path'),
            "t11": ('background_path',),
            "t12": ('background_path','logo_path'),
        }[template]
        for key in keys:
            config[key] = self._safe_uploaded_path(config.get(key, ""))
        if template == 't8' and config['media_path']:
            metadata_path = Path(config['media_path']).with_suffix('.media.json')
            if not metadata_path.is_file():
                raise ValueError('Custom media must be uploaded through Custom Upload.')
            metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
            config['media_kind'] = metadata['kind']
            config['poster_path'] = self._safe_uploaded_path(metadata.get('poster',''))
        if template == "t4":
            for player in config.get("players", []):
                player["photo"] = self._safe_uploaded_path(player.get("photo", ""))

    def _safe_uploaded_path(self, value: Any) -> str:
        if not value:
            return ""
        try:
            path = Path(str(value)).resolve()
            path.relative_to(self.upload_dir.resolve())
            if path.is_file():
                return str(path)
        except (OSError, ValueError):
            pass

        # A transferred project may retain the old PC's absolute upload path.
        # Only reconnect its generated filename inside this server's upload root.
        try:
            migrated = (self.upload_dir / Path(str(value)).name).resolve()
            migrated.relative_to(self.upload_dir.resolve())
            return str(migrated) if migrated.is_file() else ""
        except (OSError, ValueError):
            return ""

    def render(
        self, template: str, value: Any, update_live: bool = True, client_id: str = "",
    ):
        config = self.normalized_config(template, value)
        image = self.core.RENDERERS[template](config)
        with self.lock:
            if (
                update_live and self.live_output is not None
                and self._clean_client_id(client_id) == self.live_owner_id
            ):
                self.live_output.update(image)
        return image, config

    def upload(self, payload: Dict[str, Any]) -> Dict[str, str]:
        name = Path(str(payload.get("name", "image"))).name
        data_url = str(payload.get("data", ""))
        match = re.fullmatch(r"data:([^;,]+);base64,(.+)", data_url, re.DOTALL)
        if not match or match.group(1).lower() not in IMAGE_MIME_EXTENSIONS:
            raise ValueError("Upload a supported PNG, JPG, GIF, WebP, BMP, or AVIF image.")
        try:
            data = base64.b64decode(match.group(2), validate=True)
        except ValueError as exc:
            raise ValueError("The uploaded image is not valid base64 data.") from exc
        if not data or len(data) > 25 * 1024 * 1024:
            raise ValueError("Images must be between 1 byte and 25 MB.")
        try:
            with self.core.Image.open(io.BytesIO(data)) as image:
                image.verify()
        except Exception as exc:
            raise ValueError("The uploaded file is not a readable image.") from exc
        extension = IMAGE_MIME_EXTENSIONS[match.group(1).lower()]
        target = self.upload_dir / f"{uuid.uuid4().hex}{extension}"
        try:
            # The UUID target is not exposed until this write completes, so a
            # second temporary file and Windows rename are unnecessary here.
            target.write_bytes(data)
        except OSError as exc:
            raise RuntimeError(
                f"Scoreboard upload storage is not writable: {self.upload_dir}"
            ) from exc
        return {"path": str(target.resolve()), "name": name}

    def upload_media(self, stream, length, name):
        suffix = Path(name).suffix.lower()
        if suffix not in self.media.VIDEO_EXTENSIONS | self.media.IMAGE_EXTENSIONS:
            raise ValueError('Unsupported media format. Use an image, MP4, MOV, MKV, WebM, AVI, MPEG or TS.')
        if not 0 < length <= self.media.MAX_MEDIA_BYTES:
            raise ValueError('Media files must be between 1 byte and 512 MB.')
        target = self.upload_dir / (uuid.uuid4().hex + suffix)
        poster = target.with_suffix('.poster.png')
        metadata = target.with_suffix('.media.json')
        try:
            with target.open('xb') as output:
                remaining = length
                while remaining:
                    chunk = stream.read(min(1024*1024,remaining))
                    if not chunk:
                        raise ValueError('Upload interrupted. Please try again.')
                    output.write(chunk)
                    remaining -= len(chunk)
                output.flush()
                os.fsync(output.fileno())
            kind = 'video' if suffix in self.media.VIDEO_EXTENSIONS else 'image'
            if kind == 'image':
                with self.core.Image.open(target) as image:
                    image.verify()
            else:
                ffmpeg = self.core.locate_ffmpeg()
                if not ffmpeg:
                    raise ValueError('FFmpeg is required for video uploads.')
                result = subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-nostdin',
                    '-protocol_whitelist','file,pipe','-i',str(target),'-map','0:v:0','-an',
                    '-vf','scale=960:540:force_original_aspect_ratio=decrease','-frames:v','1',str(poster)],
                    capture_output=True,timeout=45,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                if result.returncode or not poster.is_file():
                    raise ValueError('The file has no decodable video stream or is damaged.')
            metadata.write_text(json.dumps({'kind':kind,'poster':poster.name if kind=='video' else ''}),encoding='utf-8')
            return {'media_path':str(target),'media_kind':kind,'poster_path':str(poster) if kind=='video' else ''}
        except Exception:
            for path in (target,poster,metadata):
                path.unlink(missing_ok=True)
            raise

    def _stop_media(self):
        if self.media_playback is not None:
            self.media_playback.stop()
            self.media_playback = None

    def start_live(
        self, template: str, config: Any, preset: str, output_name: str,
        client_id: Any, remote_address: str, standby: bool = False,
    ):
        if preset not in self.core.VIDEO_EXPORT_PRESETS:
            raise ValueError("Unknown video format.")
        capabilities=self.output_capabilities()
        device=next((d for d in capabilities['devices'] if d['name']==output_name),None)
        if device is None:
            raise ValueError(capabilities.get('error') or 'Selected DeckLink output is not detected. Refresh output devices.')
        if preset not in device['modes']:
            raise ValueError('Selected video format is not supported by this output card.')
        requester = self.touch_session(client_id, remote_address)
        if requester is None:
            raise PermissionError("Register an operator name before starting live output.")
        if requester["priority"] <= 0:
            raise PermissionError("This user has view-only live priority.")
        with self.lock:
            owner = self.sessions.get(self.live_owner_id) if self.live_owner_id else None
            if owner and owner["id"] != requester["id"]:
                if requester["priority"] <= owner["priority"]:
                    raise PermissionError(
                        f"Live output is controlled by {owner['name']} "
                        f"(priority {owner['priority']})."
                    )
            image, _ = self.render(
                template, config, update_live=False, client_id=requester["id"],
            )
            if (
                self.live_output is not None
                and self.live_preset == preset
                and self.live_output_name == output_name
            ):
                if not standby:
                    self._stop_media()
                    self.live_output.update(image)
                    self.program_frame = image.copy()
                    self.program_name = dict(zip(self.core.WEB_TEMPLATE_KEYS,self.core.WEB_TEMPLATE_NAMES))[template]
                    self.on_air = self.program_revision = uuid.uuid4().hex
                self.live_owner_id = requester["id"]
                return self.live_status(requester["id"], remote_address)
            previous = self.live_output
            if previous is not None:
                self._stop_media()
                previous.stop()
                self.live_output = None
                self.live_preset = None
                self.live_output_name = None
                self.live_owner_id = None
            output = self.core.DeckLinkLiveOutput(
                preset, device['number']
            )
            self.program_frame = self.core.Image.new('RGB', image.size, 'black') if standby else image.copy()
            output.start(self.program_frame)
            self.program_revision = uuid.uuid4().hex
            self.on_air = None if standby else self.program_revision
            self.program_name = '' if standby else dict(zip(self.core.WEB_TEMPLATE_KEYS,self.core.WEB_TEMPLATE_NAMES))[template]
            self.live_output = output
            self.live_preset = preset
            self.live_output_name = output_name
            self.live_owner_id = requester["id"]
        return self.live_status(requester["id"], remote_address)

    def show_live(self, template, config, client_id, remote_address, expected_revision=None, name=''):
        with self.lock:
            requester = self.touch_session(client_id, remote_address)
            if not requester or requester['priority'] <= 0 or requester['id'] != self.live_owner_id:
                raise PermissionError('Only the live operator can show a template on this stream.')
            if self.live_output is None:
                raise ValueError('Start the live stream first.')
            self._check_program_revision(expected_revision)
            image, config = self.render(template, config, update_live=False)
            if template == 't8' and not config.get('media_path'):
                raise ValueError('Upload media before showing it live.')
            playback = None
            if template == 't8' and config.get('media_kind') == 'video':
                playback = self.media.VideoPlayback(self.core,self.live_output,config['media_path'],
                    self.live_preset,bool(config.get('loop',True)),config=config)
            self._stop_media()
            self.live_output.update(image)
            self.program_frame = image.copy()
            self.media_playback = playback
            if playback:
                playback.start()
            self.on_air = uuid.uuid4().hex
            self.program_revision = self.on_air
            self.program_name = str(name).strip()[:100] or dict(zip(self.core.WEB_TEMPLATE_KEYS,self.core.WEB_TEMPLATE_NAMES))[template]
            return self.live_status(client_id, remote_address)

    def _check_program_revision(self, expected):
        if expected is not None and expected != self.program_revision:
            raise ProjectConflict('On Air changed. Check the output monitor and try again.')

    def clear_live(self, client_id, remote_address, expected_revision=None):
        with self.lock:
            requester = self.touch_session(client_id,remote_address)
            if not requester or requester['priority'] <= 0 or requester['id'] != self.live_owner_id:
                raise PermissionError('Only the live operator can clear On Air.')
            if self.live_output is None:
                raise ValueError('Output is stopped.')
            self._check_program_revision(expected_revision)
            self._stop_media()
            mode = self.core.VIDEO_EXPORT_PRESETS[self.live_preset]
            image = self.core.Image.new('RGB',(mode['width'],mode['height']),'black')
            self.live_output.update(image)
            self.program_frame = image
            self.on_air = None
            self.program_name = ''
            self.program_revision = uuid.uuid4().hex
            return self.live_status(client_id,remote_address)

    def program_preview(self):
        with self.lock:
            revision = self.program_revision
            image = None
            if self.live_output is not None:
                snapshot = getattr(self.live_output,'snapshot_frame',None)
                image = snapshot() if snapshot else self.program_frame
            image = image.copy() if image is not None else self.core.Image.new('RGB',(640,360),'black')
        image.thumbnail((640,360),self.core.Image.Resampling.BILINEAR)
        data = io.BytesIO()
        image.save(data,'JPEG',quality=80)
        return data.getvalue(),revision

    def stop_live(
        self, client_id: Any = "", remote_address: str = "", force: bool = False, expected_revision=None,
    ):
        client_id = self._clean_client_id(client_id)
        with self.lock:
            if not force:
                self._check_program_revision(expected_revision)
            if (
                self.live_output is not None and not force
                and client_id != self.live_owner_id
                and not self._is_local_request(remote_address)
            ):
                owner = self.sessions.get(self.live_owner_id, {})
                raise PermissionError(
                    f"Only {owner.get('name', 'the live operator')} can stop live output."
                )
            self._stop_media()
            output, self.live_output = self.live_output, None
            self.live_preset = None
            self.live_output_name = None
            self.live_owner_id = None
            self.on_air = None
            self.program_frame = None
            self.program_name = ''
            self.program_revision = uuid.uuid4().hex
        if output is not None:
            output.stop()
        return self.live_status(client_id, remote_address)

    def live_status(self, client_id: Any = "", remote_address: str = ""):
        client_id = self._clean_client_id(client_id)
        with self.lock:
            error = self.live_output.poll_error() if self.live_output is not None else None
        if error:
            self.stop_live(force=True)
            return {"active": False, "error": error}
        with self.lock:
            owner = self.sessions.get(self.live_owner_id)
            return {
                "active": self.live_output is not None,
                "program_revision": self.program_revision,
                "program_name": self.program_name,
                "on_air": self.on_air if self.live_output is not None else None,
                "media_error": self.media_playback.error if self.media_playback else None,
                "media_finished": self.media_playback.finished if self.media_playback else False,
                "preset": self.live_preset,
                "output": self.live_output_name,
                "owner_id": self.live_owner_id,
                "owner_name": owner["name"] if owner else None,
                "owned_by_requester": bool(client_id and client_id == self.live_owner_id),
            }

    def export_mp4(self, template: str, value: Any, preset: str, duration: int) -> bytes:
        ffmpeg = self.core.locate_ffmpeg()
        if not ffmpeg:
            raise RuntimeError("FFmpeg is not installed or FFMPEG_PATH is not configured.")
        duration = max(1, min(300, int(duration)))
        image, config = self.render(template, value, update_live=False)
        with tempfile.TemporaryDirectory(prefix="scoreboard_web_mp4_") as directory:
            source = Path(directory) / "frame.png"
            output = Path(directory) / "scoreboard.mp4"
            image.save(source, "PNG")
            command = self.core.build_mp4_command(ffmpeg, source, output, preset, duration)
            if template == 't8' and config.get('media_kind') == 'video':
                # Replace the still-image input, retaining the broadcast encoding settings.
                index = command.index('-loop')
                command[index:index+6] = ['-stream_loop','-1','-protocol_whitelist','file,pipe',
                    '-i',config['media_path']]
                command[-1:-1] = ['-map','0:v:0','-map','1:a:0']
                if config.get('text_boxes'):
                    mode = self.core.MP4_EXPORT_PRESETS[preset]
                    overlay_path = Path(directory)/'overlay.png'
                    self.core.render_custom_text_overlay(config,(mode['width'],mode['height'])).save(overlay_path)
                    input_index = command.index('-t')
                    command[input_index:input_index] = ['-loop','1','-i',str(overlay_path)]
                    filter_index = command.index('-vf')
                    base_filter = command[filter_index+1]
                    command[filter_index:filter_index+2] = ['-filter_complex',
                        f'[0:v]{base_filter}[base];[base][2:v]overlay=0:0:format=auto,format=yuv420p[out]']
                    command[command.index('-map')+1] = '[out]'
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode:
                detail = (result.stderr or result.stdout or "FFmpeg failed").strip()
                raise RuntimeError(detail[-1800:])
            return output.read_bytes()


def make_handler(runtime: ScoreboardWebRuntime):
    class Handler(BaseHTTPRequestHandler):
        server_version = "VetoScoreboard/1.0"

        def log_message(self, message, *args):
            sys.stderr.write("scoreboard-web: " + message % args + "\n")

        def _send(self, status: int, data: bytes, content_type: str, filename: str = "", headers=None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "frame-ancestors 'self'")
            for key,value in (headers or {}).items():
                self.send_header(key,value)
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                # Rapid preview changes cancel older browser requests by design.
                pass

        def _json(self, status: int, value: Any):
            self._send(status, json.dumps(value).encode("utf-8"), "application/json; charset=utf-8")

        def _body(self) -> Dict[str, Any]:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise ValueError("Invalid Content-Length.") from exc
            if length <= 0 or length > MAX_REQUEST_BYTES:
                raise ValueError("Request body is empty or too large.")
            value = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError("JSON request must be an object.")
            return value

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            query = parse_qs(parsed.query)
            client_id = query.get("client_id", [""])[0]
            remote_address = self.client_address[0]
            try:
                if path == '/api/media':
                    name = query.get('name',[''])[0]
                    if not re.fullmatch(r'[0-9a-f]{32}\.[a-z0-9]+',name):
                        self._json(404, {'error':'Media not found'})
                        return
                    source = runtime.upload_dir / name
                    if not source.is_file() or not source.with_suffix('.media.json').is_file():
                        self._json(404, {'error':'Media not found'})
                        return
                    size = source.stat().st_size
                    start,end = 0,size-1
                    range_header = self.headers.get('Range')
                    if range_header:
                        match = re.fullmatch(r'bytes=(\d+)-(\d*)',range_header)
                        if not match or int(match[1]) >= size:
                            self.send_response(416)
                            self.send_header('Content-Range',f'bytes */{size}')
                            self.send_header('Content-Length','0')
                            self.end_headers()
                            return
                        start = int(match[1])
                        end = min(size-1,int(match[2])) if match[2] else size-1
                        if end < start:
                            self._json(400, {'error':'Invalid media range'})
                            return
                    import mimetypes
                    self.send_response(206 if range_header else 200)
                    self.send_header('Content-Type',mimetypes.guess_type(name)[0] or 'application/octet-stream')
                    self.send_header('Content-Length',str(end-start+1))
                    self.send_header('Accept-Ranges','bytes')
                    self.send_header('X-Content-Type-Options','nosniff')
                    if range_header:
                        self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
                    self.end_headers()
                    with source.open('rb') as stream:
                        stream.seek(start)
                        remaining = end-start+1
                        try:
                            while remaining:
                                data = stream.read(min(1024*1024,remaining))
                                if not data: break
                                self.wfile.write(data)
                                remaining -= len(data)
                        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):
                            pass
                elif path in {"/", "/scoreboard"}:
                    self._send(200, runtime.web_file.read_bytes(), "text/html; charset=utf-8")
                elif path == "/api/bootstrap":
                    self._json(200, runtime.bootstrap())
                elif path == '/api/output/capabilities':
                    self._json(200, runtime.output_capabilities())
                elif path == "/api/projects":
                    self._json(200, {"projects": runtime.list_projects()})
                elif path == '/api/templates':
                    self._json(200, runtime.library_snapshot())
                elif path == '/api/templates/changes':
                    self._json(200, runtime.wait_for_library(query.get('revision',[''])[0]))
                elif path == "/api/projects/open":
                    self._json(200, runtime.open_project(query.get("id", [""])[0]))
                elif path == "/api/live/status":
                    self._json(200, runtime.live_status(client_id, remote_address))
                elif path == '/api/live/preview':
                    data,revision = runtime.program_preview()
                    self._send(200,data,'image/jpeg',headers={'X-Program-Revision':revision})
                elif path == "/api/sessions":
                    self._json(200, runtime.session_status(client_id, remote_address))
                elif path == "/healthz":
                    self._json(200, {
                        "ok": True,
                        "service": "scoreboard-web",
                        "upload_storage": runtime.storage_status(),
                    })
                else:
                    self._json(404, {"error": "Not found"})
            except Exception as exc:
                self._json(500, {"error": str(exc)})

        def do_POST(self):
            path = urlparse(self.path).path.rstrip("/")
            try:
                if path == '/api/media/upload':
                    self.close_connection = True
                    self.connection.settimeout(120)
                    from urllib.parse import unquote
                    length = int(self.headers.get('Content-Length','0'))
                    self._json(200, runtime.upload_media(self.rfile,length,
                        unquote(self.headers.get('X-Filename',''))))
                    return
                if path.startswith('/api/projects/') or path == '/api/presets/save':
                    self._json(410, {'error':'Project editing has been retired. Use the template library.'})
                    return
                payload = self._body()
                client_id = payload.get("client_id", "")
                remote_address = self.client_address[0]
                if path == '/api/templates/save':
                    self._json(200, runtime.save_template(payload, remote_address))
                elif path == '/api/templates/update':
                    self._json(200, runtime.update_template(payload, remote_address))
                elif path == "/api/projects/save":
                    self._json(200, runtime.save_project(payload, remote_address))
                elif path == '/api/projects/unlock':
                    self._json(200, runtime.unlock_project(payload, remote_address))
                elif path == '/api/projects/lock':
                    self._json(200, runtime.lock_project(payload))
                elif path == '/api/presets/save':
                    self._json(200, runtime.save_preset(payload, remote_address))
                elif path == "/api/session/register":
                    self._json(200, runtime.register_session(
                        client_id, payload.get("display_name", ""), remote_address,
                    ))
                elif path == "/api/session/heartbeat":
                    self._json(200, runtime.touch_session(client_id, remote_address))
                elif path == "/api/session/priority":
                    self._json(200, runtime.set_session_priority(
                        payload.get("target_id", ""), payload.get("priority"), remote_address,
                    ))
                elif path == '/api/render/overlay':
                    config = runtime.normalized_config('t8',payload.get('config'))
                    size = runtime.core.T8_SIZES[config['canvas_size']]
                    image = runtime.core.render_custom_text_overlay(config,size)
                    buffer = io.BytesIO()
                    image.save(buffer,'PNG')
                    self._send(200,buffer.getvalue(),'image/png')
                elif path == "/api/render":
                    runtime.touch_session(client_id, remote_address)
                    image, _ = runtime.render(
                        payload.get("template", ""), payload.get("config"),
                        client_id=client_id,
                        update_live=False,
                    )
                    buffer = io.BytesIO()
                    image.save(buffer, "PNG")
                    self._send(200, buffer.getvalue(), "image/png")
                elif path == "/api/upload":
                    runtime.touch_session(client_id, remote_address)
                    self._json(200, runtime.upload(payload))
                elif path == "/api/export/png":
                    runtime.touch_session(client_id, remote_address)
                    template = payload.get("template", "")
                    image, _ = runtime.render(template, payload.get("config"))
                    buffer = io.BytesIO()
                    image.save(buffer, "PNG")
                    self._send(200, buffer.getvalue(), "image/png", f"scoreboard_{template}.png")
                elif path == "/api/export/mp4":
                    runtime.touch_session(client_id, remote_address)
                    template = payload.get("template", "")
                    data = runtime.export_mp4(
                        template, payload.get("config"), payload.get("preset", "HD 1080i50"),
                        payload.get("duration", 10),
                    )
                    self._send(200, data, "video/mp4", f"scoreboard_{template}.mp4")
                elif path == "/api/live/start":
                    self._json(200, runtime.start_live(
                        payload.get("template", ""), payload.get("config"),
                        payload.get("preset", ""), payload.get("output", ""),
                        client_id, remote_address,
                        standby=True,
                    ))
                elif path == '/api/live/show':
                    self._json(200, runtime.show_live(payload.get('template'), payload.get('config'), client_id, remote_address,
                        payload.get('expected_revision'),payload.get('name','')))
                elif path == '/api/live/clear':
                    self._json(200,runtime.clear_live(client_id,remote_address,payload.get('expected_revision')))
                elif path == "/api/live/stop":
                    self._json(200, runtime.stop_live(client_id, remote_address,expected_revision=payload.get('expected_revision')))
                else:
                    self._json(404, {"error": "Not found"})
            except ProjectConflict as exc:
                self._json(409, {"error": str(exc)})
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(400, {"error": str(exc)})
            except PermissionError as exc:
                self._json(403, {"error": str(exc)})
            except Exception as exc:
                self._json(500, {"error": str(exc)})

    return Handler


def run_server(core, host: str = "0.0.0.0", port: int = 8080):
    runtime = ScoreboardWebRuntime(core)
    server = ThreadingHTTPServer((host, port), make_handler(runtime))
    print(f"Scoreboard web editor: http://127.0.0.1:{port}/scoreboard")
    if host not in {"127.0.0.1", "localhost"}:
        print(f"LAN binding enabled on {host}:{port}")
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        runtime.stop_live(force=True)
        server.server_close()
