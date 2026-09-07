from __future__ import annotations

import configparser
import datetime as dt
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass(frozen=True)
class RcloneS3Remote:
    section: str
    bucket: str
    key_prefix: str
    endpoint: str
    region: str
    access_key_id: str
    secret_access_key: str


def _rclone_config_path() -> Path:
    configured = os.getenv("RCLONE_CONFIG")
    if configured:
        return Path(configured).expanduser()
    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / "rclone" / "rclone.conf"
    return Path.home() / ".config" / "rclone" / "rclone.conf"


def load_rclone_s3_remote(remote: str) -> RcloneS3Remote:
    section, separator, location = remote.partition(":")
    if not separator or not section or not location:
        raise ValueError(f"Invalid rclone remote: {remote}")
    bucket, slash, key_prefix = location.partition("/")
    if not bucket:
        raise ValueError(f"S3 bucket is missing from: {remote}")

    parser = configparser.RawConfigParser()
    config_path = _rclone_config_path()
    if not parser.read(config_path, encoding="utf-8") or not parser.has_section(section):
        raise ValueError(f"rclone section [{section}] was not found in {config_path}")
    values = parser[section]
    if values.get("type", "").casefold() != "s3":
        raise ValueError(f"rclone section [{section}] is not an S3 remote")
    endpoint = values.get("endpoint", "").strip()
    if not endpoint:
        raise ValueError(f"rclone section [{section}] has no S3 endpoint")
    if "://" not in endpoint:
        endpoint = "https://" + endpoint
    return RcloneS3Remote(
        section=section,
        bucket=bucket,
        key_prefix=key_prefix.rstrip("/") if slash else "",
        endpoint=endpoint,
        region=values.get("region", "").strip(),
        access_key_id=values.get("access_key_id", "").strip(),
        secret_access_key=values.get("secret_access_key", "").strip(),
    )


def list_recent_relative_key_sets(
    remote: str,
    hours: int,
    workers: int = 10,
    now: dt.datetime | None = None,
    local_root: Path | None = None,
) -> tuple[list[str], list[str]]:
    """List missing and all recent objects with one parallel S3 traversal."""
    import boto3
    from botocore.config import Config

    target = load_rclone_s3_remote(remote)
    client = boto3.client(
        "s3",
        endpoint_url=target.endpoint,
        region_name=target.region or None,
        aws_access_key_id=target.access_key_id or None,
        aws_secret_access_key=target.secret_access_key or None,
        config=Config(
            connect_timeout=10,
            read_timeout=30,
            retries={"max_attempts": 3, "mode": "standard"},
            max_pool_connections=max(10, workers),
        ),
    )
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    cutoff = current.astimezone(dt.timezone.utc) - dt.timedelta(hours=hours)
    base = f"{target.key_prefix}/" if target.key_prefix else ""

    def list_shard(digit: str) -> tuple[list[str], list[str]]:
        missing: list[str] = []
        recent: list[str] = []
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(
            Bucket=target.bucket,
            Prefix=f"{base}ak-{digit}",
        ):
            for item in page.get("Contents", ()):
                key = item.get("Key", "")
                modified = item.get("LastModified")
                if modified is None or modified < cutoff or not key.casefold().endswith(".gz"):
                    continue
                relative = key[len(base):] if key.startswith(base) else PurePosixPath(key).name
                if not relative or "/" in relative:
                    continue
                recent.append(relative)
                if local_root is not None:
                    try:
                        if (local_root / relative).stat().st_size == int(item.get("Size", -1)):
                            continue
                    except OSError:
                        pass
                missing.append(relative)
        return missing, recent

    with ThreadPoolExecutor(max_workers=max(1, min(10, workers))) as pool:
        groups = list(pool.map(list_shard, "0123456789"))
    missing = sorted({key for group, _recent in groups for key in group})
    recent = sorted({key for _missing, group in groups for key in group})
    return missing, recent


def list_recent_relative_keys(
    remote: str,
    hours: int,
    workers: int = 10,
    now: dt.datetime | None = None,
    local_root: Path | None = None,
) -> list[str]:
    """Compatibility wrapper returning only objects missing from local storage."""
    missing, _recent = list_recent_relative_key_sets(
        remote, hours, workers=workers, now=now, local_root=local_root
    )
    return missing
