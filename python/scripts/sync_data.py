"""Sync python/data/ with Cloudflare R2 for sharing among collaborators.

Usage:
    python scripts/sync_data.py upload          # push local data/ to R2
    python scripts/sync_data.py download        # pull R2 data/ to local
    python scripts/sync_data.py upload raw      # sync only raw/ subfolder
    python scripts/sync_data.py download cache  # sync only cache/ subfolder
    python scripts/sync_data.py watch           # auto-sync bidirectionally
    python scripts/sync_data.py watch --poll 60 # custom poll interval (seconds)

Environment variables (set in .env or export):
    R2_ACCOUNT_ID       - Cloudflare account ID
    R2_ACCESS_KEY_ID    - R2 API token access key
    R2_SECRET_ACCESS_KEY - R2 API token secret key
    R2_BUCKET_NAME      - Bucket name (default: orb-backtests-data)
"""

from __future__ import annotations

import os
import signal
import sys
import threading
import time
from pathlib import Path

import boto3

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SUBDIRS = ["raw", "cache", "results", "optimizations"]
# Standalone files in data/ to sync (not inside a subdir)
STANDALONE_FILES = ["experiments.db"]


def get_client():
    account_id = os.environ.get("R2_ACCOUNT_ID")
    access_key = os.environ.get("R2_ACCESS_KEY_ID")
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY")

    missing = []
    if not account_id:
        missing.append("R2_ACCOUNT_ID")
    if not access_key:
        missing.append("R2_ACCESS_KEY_ID")
    if not secret_key:
        missing.append("R2_SECRET_ACCESS_KEY")
    if missing:
        print(f"Error: missing environment variables: {', '.join(missing)}")
        print("Set them in .env or export them. See .env.example for reference.")
        sys.exit(1)

    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )


def get_bucket() -> str:
    return os.environ.get("R2_BUCKET_NAME", "orb-backtests-data")


def list_remote_objects(client, bucket: str, prefix: str = "") -> dict[str, int]:
    """Return {key: size} for all objects under prefix."""
    objects = {}
    kwargs = {"Bucket": bucket, "Prefix": prefix}
    while True:
        resp = client.list_objects_v2(**kwargs)
        for obj in resp.get("Contents", []):
            objects[obj["Key"]] = obj["Size"]
        if not resp.get("IsTruncated"):
            break
        kwargs["ContinuationToken"] = resp["NextContinuationToken"]
    return objects


def upload(subdirs: list[str] | None = None):
    client = get_client()
    bucket = get_bucket()
    targets = subdirs or SUBDIRS
    uploaded = 0
    skipped = 0

    remote_objects = {}
    for subdir in targets:
        remote_objects.update(list_remote_objects(client, bucket, prefix=f"{subdir}/"))

    for subdir in targets:
        local_dir = DATA_DIR / subdir
        if not local_dir.exists():
            print(f"  skip {subdir}/ (not found locally)")
            continue
        for filepath in sorted(local_dir.rglob("*")):
            if filepath.is_dir():
                continue
            key = filepath.relative_to(DATA_DIR).as_posix()
            local_size = filepath.stat().st_size

            if key in remote_objects and remote_objects[key] == local_size:
                skipped += 1
                continue

            print(f"  uploading {key} ({local_size:,} bytes)")
            client.upload_file(str(filepath), bucket, key)
            uploaded += 1

    # Sync standalone files (only during full sync, not subfolder-specific)
    if subdirs is None:
        for fname in STANDALONE_FILES:
            filepath = DATA_DIR / fname
            if not filepath.exists():
                continue
            key = fname
            local_size = filepath.stat().st_size
            remote_objects.update(list_remote_objects(client, bucket, prefix=key))
            if key in remote_objects and remote_objects[key] == local_size:
                skipped += 1
                continue
            print(f"  uploading {key} ({local_size:,} bytes)")
            client.upload_file(str(filepath), bucket, key)
            uploaded += 1

    print(f"\nDone: {uploaded} uploaded, {skipped} unchanged")


def download(subdirs: list[str] | None = None):
    client = get_client()
    bucket = get_bucket()
    targets = subdirs or SUBDIRS
    downloaded = 0
    skipped = 0

    for subdir in targets:
        remote_objects = list_remote_objects(client, bucket, prefix=f"{subdir}/")
        for key, remote_size in sorted(remote_objects.items()):
            local_path = DATA_DIR / key
            if local_path.exists() and local_path.stat().st_size == remote_size:
                skipped += 1
                continue

            local_path.parent.mkdir(parents=True, exist_ok=True)
            print(f"  downloading {key} ({remote_size:,} bytes)")
            client.download_file(bucket, key, str(local_path))
            downloaded += 1

    # Sync standalone files (only during full sync)
    if subdirs is None:
        for fname in STANDALONE_FILES:
            remote_objects = list_remote_objects(client, bucket, prefix=fname)
            for key, remote_size in remote_objects.items():
                if key != fname:
                    continue
                local_path = DATA_DIR / key
                if local_path.exists() and local_path.stat().st_size == remote_size:
                    skipped += 1
                    continue
                local_path.parent.mkdir(parents=True, exist_ok=True)
                print(f"  downloading {key} ({remote_size:,} bytes)")
                client.download_file(bucket, key, str(local_path))
                downloaded += 1

    print(f"\nDone: {downloaded} downloaded, {skipped} unchanged")


def upload_file(client, bucket: str, filepath: Path):
    """Upload a single file to R2."""
    key = filepath.relative_to(DATA_DIR).as_posix()
    size = filepath.stat().st_size
    print(f"  [upload] {key} ({size:,} bytes)")
    client.upload_file(str(filepath), bucket, key)


def watch(poll_interval: int = 30):
    """Bidirectional sync: watch local changes + poll R2 for remote changes."""
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    client = get_client()
    bucket = get_bucket()

    # Track files we just downloaded to avoid re-uploading them
    recently_synced: set[str] = set()
    sync_lock = threading.Lock()

    class UploadHandler(FileSystemEventHandler):
        def _handle(self, event):
            if event.is_directory:
                return
            filepath = Path(event.src_path)
            # Only sync files inside known subdirs
            try:
                key = filepath.relative_to(DATA_DIR).as_posix()
            except ValueError:
                return
            if not any(key.startswith(f"{s}/") for s in SUBDIRS) and key not in STANDALONE_FILES:
                return
            with sync_lock:
                if key in recently_synced:
                    recently_synced.discard(key)
                    return
            if filepath.exists():
                upload_file(client, bucket, filepath)

        def on_created(self, event):
            self._handle(event)

        def on_modified(self, event):
            self._handle(event)

    # Start local file watcher
    observer = Observer()
    observer.schedule(UploadHandler(), str(DATA_DIR), recursive=True)
    observer.start()
    print(f"Watching {DATA_DIR} for local changes")
    print(f"Polling R2 every {poll_interval}s for remote changes")
    print("Press Ctrl+C to stop\n")

    # Initial full sync
    print("Running initial sync...")
    upload()
    download()
    print()

    # Poll R2 for remote changes
    stop_event = threading.Event()

    def handle_signal(sig, frame):
        print("\nStopping watcher...")
        stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    while not stop_event.is_set():
        stop_event.wait(poll_interval)
        if stop_event.is_set():
            break
        for subdir in SUBDIRS:
            remote_objects = list_remote_objects(client, bucket, prefix=f"{subdir}/")
            for key, remote_size in remote_objects.items():
                local_path = DATA_DIR / key
                if local_path.exists() and local_path.stat().st_size == remote_size:
                    continue
                local_path.parent.mkdir(parents=True, exist_ok=True)
                print(f"  [download] {key} ({remote_size:,} bytes)")
                client.download_file(bucket, key, str(local_path))
                with sync_lock:
                    recently_synced.add(key)

    observer.stop()
    observer.join()
    print("Watcher stopped.")


def load_env():
    """Load .env file if present."""
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def main():
    commands = ("upload", "download", "watch")
    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        print("Usage: python scripts/sync_data.py <upload|download|watch> [options]")
        print(f"Subfolders (for upload/download): {', '.join(SUBDIRS)}")
        print("Watch options: --poll <seconds> (default: 30)")
        sys.exit(1)

    command = sys.argv[1]

    load_env()

    if command == "watch":
        poll_interval = 30
        if "--poll" in sys.argv:
            idx = sys.argv.index("--poll")
            if idx + 1 < len(sys.argv):
                poll_interval = int(sys.argv[idx + 1])
        watch(poll_interval)
        return

    subdirs = None
    if len(sys.argv) > 2:
        subdirs = [s for s in sys.argv[2:] if s in SUBDIRS]
        invalid = [s for s in sys.argv[2:] if s not in SUBDIRS]
        if invalid:
            print(f"Warning: ignoring unknown subfolders: {', '.join(invalid)}")
            print(f"Valid subfolders: {', '.join(SUBDIRS)}")

    print(f"{'Uploading to' if command == 'upload' else 'Downloading from'} R2...")
    if command == "upload":
        upload(subdirs)
    else:
        download(subdirs)


if __name__ == "__main__":
    main()
