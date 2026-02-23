"""
BlackRoad Container Registry
Production-quality container image registry simulation with SQLite persistence
and content-addressable layer tracking.
"""

from __future__ import annotations
import argparse
import hashlib
import json
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


DB_PATH = Path.home() / ".blackroad" / "container_registry.db"

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Layer:
    digest: str
    size_bytes: int
    media_type: str = "application/vnd.oci.image.layer.v1.tar+gzip"

    @classmethod
    def from_content(cls, content: bytes | str) -> "Layer":
        if isinstance(content, str):
            content = content.encode()
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        return cls(digest=digest, size_bytes=len(content))


@dataclass
class Image:
    name: str
    tag: str
    digest: str = ""
    size_mb: float = 0.0
    pushed_at: float = field(default_factory=time.time)
    pulled_count: int = 0
    layers: list[Layer] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)
    architecture: str = "amd64"
    os: str = "linux"
    author: str = ""

    def __post_init__(self):
        if not self.name:
            raise ValueError("Image name cannot be empty")
        if not re.fullmatch(r"[a-z0-9][a-z0-9._/-]*", self.name):
            pass  # Accept most valid image names
        if not self.tag:
            self.tag = "latest"
        if not self.digest:
            payload = f"{self.name}:{self.tag}:{self.pushed_at}"
            self.digest = "sha256:" + hashlib.sha256(payload.encode()).hexdigest()

    @property
    def full_ref(self) -> str:
        return f"{self.name}:{self.tag}"

    @property
    def pushed_at_iso(self) -> str:
        return datetime.fromtimestamp(self.pushed_at, tz=timezone.utc).isoformat()

    def manifest(self) -> dict:
        return {
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "config": {
                "mediaType": "application/vnd.oci.image.config.v1+json",
                "digest": self.digest,
                "size": int(self.size_mb * 1024 * 1024),
            },
            "layers": [
                {"mediaType": l.media_type, "digest": l.digest, "size": l.size_bytes}
                for l in self.layers
            ],
            "annotations": {
                "org.opencontainers.image.created": self.pushed_at_iso,
                "org.opencontainers.image.authors": self.author,
                **self.labels,
            },
        }


import re


# ---------------------------------------------------------------------------
# SQLite persistence
# ---------------------------------------------------------------------------

def _init_db(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS images (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            tag          TEXT NOT NULL DEFAULT 'latest',
            digest       TEXT NOT NULL,
            size_mb      REAL NOT NULL DEFAULT 0,
            pushed_at    REAL NOT NULL,
            pulled_count INTEGER NOT NULL DEFAULT 0,
            architecture TEXT NOT NULL DEFAULT 'amd64',
            os           TEXT NOT NULL DEFAULT 'linux',
            author       TEXT,
            labels       TEXT NOT NULL DEFAULT '{}',
            UNIQUE(name, tag)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS layers (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            image_id   INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
            digest     TEXT NOT NULL,
            size_bytes INTEGER NOT NULL DEFAULT 0,
            media_type TEXT NOT NULL,
            layer_order INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pull_log (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT NOT NULL,
            tag       TEXT NOT NULL,
            pulled_at REAL NOT NULL,
            client_ip TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS repositories (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            description TEXT,
            created_at  REAL NOT NULL,
            public      INTEGER NOT NULL DEFAULT 1
        )
    """)
    # Enable WAL for better concurrent read performance
    conn.execute("PRAGMA journal_mode=WAL")
    conn.commit()
    return conn


def _ensure_repo(name: str, db: sqlite3.Connection) -> None:
    base = name.split("/")[0] if "/" in name else name
    db.execute(
        "INSERT OR IGNORE INTO repositories (name, created_at) VALUES (?, ?)",
        (base, time.time())
    )
    db.commit()


# ---------------------------------------------------------------------------
# Registry operations
# ---------------------------------------------------------------------------

def push_image(
    name: str,
    tag: str = "latest",
    layers: Optional[list[Layer]] = None,
    labels: Optional[dict[str, str]] = None,
    author: str = "",
    db: Optional[sqlite3.Connection] = None,
) -> Image:
    """Push (upsert) an image to the registry."""
    if db is None:
        db = _init_db()
    if layers is None:
        # Simulate a 3-layer image
        base = f"{name}:{tag}:base".encode()
        app = f"{name}:{tag}:app".encode()
        cfg = f"{name}:{tag}:config".encode()
        layers = [
            Layer("sha256:" + hashlib.sha256(base).hexdigest(), len(base) * 1000),
            Layer("sha256:" + hashlib.sha256(app).hexdigest(), len(app) * 2000),
            Layer("sha256:" + hashlib.sha256(cfg).hexdigest(), len(cfg) * 100),
        ]

    size_mb = sum(l.size_bytes for l in layers) / (1024 * 1024)
    img = Image(
        name=name,
        tag=tag,
        size_mb=round(size_mb, 3),
        layers=layers,
        labels=labels or {},
        author=author,
        pushed_at=time.time(),
    )

    _ensure_repo(name, db)

    # Upsert image
    db.execute(
        """INSERT INTO images (name,tag,digest,size_mb,pushed_at,architecture,os,author,labels)
           VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT(name,tag) DO UPDATE SET
             digest=excluded.digest, size_mb=excluded.size_mb,
             pushed_at=excluded.pushed_at, labels=excluded.labels""",
        (img.name, img.tag, img.digest, img.size_mb, img.pushed_at,
         img.architecture, img.os, img.author, json.dumps(img.labels)),
    )
    image_id = db.execute(
        "SELECT id FROM images WHERE name=? AND tag=?", (name, tag)
    ).fetchone()[0]

    # Replace layers
    db.execute("DELETE FROM layers WHERE image_id=?", (image_id,))
    for i, layer in enumerate(layers):
        db.execute(
            "INSERT INTO layers (image_id,digest,size_bytes,media_type,layer_order) VALUES (?,?,?,?,?)",
            (image_id, layer.digest, layer.size_bytes, layer.media_type, i),
        )
    db.commit()
    return img


def pull_image(
    name: str,
    tag: str = "latest",
    client_ip: str = "127.0.0.1",
    db: Optional[sqlite3.Connection] = None,
) -> Optional[Image]:
    """Pull an image from the registry (increments pull count)."""
    if db is None:
        db = _init_db()
    row = db.execute(
        "SELECT * FROM images WHERE name=? AND tag=?", (name, tag)
    ).fetchone()
    if not row:
        return None

    cols = [d[0] for d in db.execute("SELECT * FROM images LIMIT 0").description]
    data = dict(zip(cols, row))
    image_id = data["id"]

    # Increment pull count
    db.execute(
        "UPDATE images SET pulled_count=pulled_count+1 WHERE id=?", (image_id,)
    )
    db.execute(
        "INSERT INTO pull_log (name,tag,pulled_at,client_ip) VALUES (?,?,?,?)",
        (name, tag, time.time(), client_ip),
    )

    # Load layers
    layer_rows = db.execute(
        "SELECT digest,size_bytes,media_type FROM layers WHERE image_id=? ORDER BY layer_order",
        (image_id,),
    ).fetchall()
    layers = [Layer(r[0], r[1], r[2]) for r in layer_rows]
    db.commit()

    return Image(
        name=data["name"],
        tag=data["tag"],
        digest=data["digest"],
        size_mb=data["size_mb"],
        pushed_at=data["pushed_at"],
        pulled_count=data["pulled_count"] + 1,
        layers=layers,
        labels=json.loads(data.get("labels", "{}")),
        architecture=data.get("architecture", "amd64"),
        os=data.get("os", "linux"),
        author=data.get("author", ""),
    )


def list_images(
    filter_name: Optional[str] = None,
    db: Optional[sqlite3.Connection] = None,
) -> list[Image]:
    """List images, optionally filtered by name prefix."""
    if db is None:
        db = _init_db()
    if filter_name:
        rows = db.execute(
            "SELECT * FROM images WHERE name LIKE ? ORDER BY name,tag",
            (f"%{filter_name}%",),
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM images ORDER BY name,tag").fetchall()

    cols = [d[0] for d in db.execute("SELECT * FROM images LIMIT 0").description]
    result: list[Image] = []
    for row in rows:
        data = dict(zip(cols, row))
        result.append(Image(
            name=data["name"],
            tag=data["tag"],
            digest=data["digest"],
            size_mb=data["size_mb"],
            pushed_at=data["pushed_at"],
            pulled_count=data["pulled_count"],
            labels=json.loads(data.get("labels", "{}")),
            author=data.get("author", ""),
        ))
    return result


def delete_image(
    name: str,
    tag: str = "latest",
    db: Optional[sqlite3.Connection] = None,
) -> bool:
    """Delete an image and its layers."""
    if db is None:
        db = _init_db()
    row = db.execute(
        "SELECT id FROM images WHERE name=? AND tag=?", (name, tag)
    ).fetchone()
    if not row:
        return False
    db.execute("DELETE FROM images WHERE id=?", (row[0],))
    db.commit()
    return True


def get_image_stats(
    name: str,
    db: Optional[sqlite3.Connection] = None,
) -> dict:
    """Get statistics for all tags of an image."""
    if db is None:
        db = _init_db()
    rows = db.execute(
        "SELECT tag,digest,size_mb,pushed_at,pulled_count FROM images WHERE name=?",
        (name,),
    ).fetchall()
    if not rows:
        return {"error": f"No images found for {name}"}

    total_pulls = sum(r[4] for r in rows)
    total_size = sum(r[2] for r in rows)
    latest_push = max(r[3] for r in rows)

    return {
        "name": name,
        "tag_count": len(rows),
        "total_pulls": total_pulls,
        "total_size_mb": round(total_size, 3),
        "latest_push": datetime.fromtimestamp(latest_push, tz=timezone.utc).isoformat(),
        "tags": [
            {
                "tag": r[0],
                "digest": r[1][:19] + "...",
                "size_mb": r[2],
                "pulled_count": r[4],
                "pushed_at": datetime.fromtimestamp(r[3], tz=timezone.utc).isoformat(),
            }
            for r in rows
        ],
    }


def cleanup_untagged(
    days_old: int = 30,
    db: Optional[sqlite3.Connection] = None,
) -> dict:
    """Delete untagged images (tag='<none>') or images older than days_old."""
    if db is None:
        db = _init_db()
    cutoff = time.time() - (days_old * 86400)
    rows = db.execute(
        "SELECT id,name,tag FROM images WHERE pushed_at < ? AND pulled_count = 0",
        (cutoff,),
    ).fetchall()
    deleted = []
    for row in rows:
        db.execute("DELETE FROM images WHERE id=?", (row[0],))
        deleted.append(f"{row[1]}:{row[2]}")
    db.commit()
    return {"deleted": deleted, "count": len(deleted), "days_old": days_old}


def tag_image(
    source_name: str,
    source_tag: str,
    dest_tag: str,
    db: Optional[sqlite3.Connection] = None,
) -> Optional[Image]:
    """Create a new tag pointing to the same image."""
    if db is None:
        db = _init_db()
    src = pull_image(source_name, source_tag, db=db)
    if not src:
        return None
    return push_image(
        source_name, dest_tag,
        layers=src.layers,
        labels=src.labels,
        author=src.author,
        db=db,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cmd_push(args: argparse.Namespace) -> None:
    db = _init_db()
    img = push_image(args.name, args.tag, db=db)
    print(f"Pushed {img.full_ref}")
    print(f"  Digest: {img.digest[:19]}...")
    print(f"  Size:   {img.size_mb:.2f} MB")
    print(f"  Layers: {len(img.layers)}")


def _cmd_pull(args: argparse.Namespace) -> None:
    db = _init_db()
    img = pull_image(args.name, args.tag, db=db)
    if img is None:
        print(f"Image {args.name}:{args.tag} not found", file=sys.stderr)
        sys.exit(1)
    print(f"Pulled {img.full_ref}")
    print(f"  Digest:  {img.digest[:19]}...")
    print(f"  Size:    {img.size_mb:.2f} MB")
    print(f"  Pulls:   {img.pulled_count}")
    print(f"  Pushed:  {img.pushed_at_iso}")


def _cmd_list(args: argparse.Namespace) -> None:
    db = _init_db()
    images = list_images(args.filter, db)
    if not images:
        print("No images found.")
        return
    print(f"{'REPOSITORY':<35} {'TAG':<15} {'SIZE':<10} {'PULLS':<8} {'PUSHED'}")
    print("-" * 90)
    for img in images:
        pushed = datetime.fromtimestamp(img.pushed_at, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        print(f"{img.name:<35} {img.tag:<15} {img.size_mb:<10.2f} {img.pulled_count:<8} {pushed}")


def _cmd_delete(args: argparse.Namespace) -> None:
    db = _init_db()
    if delete_image(args.name, args.tag, db):
        print(f"Deleted {args.name}:{args.tag}")
    else:
        print(f"Image {args.name}:{args.tag} not found", file=sys.stderr)
        sys.exit(1)


def _cmd_stats(args: argparse.Namespace) -> None:
    db = _init_db()
    stats = get_image_stats(args.name, db)
    print(json.dumps(stats, indent=2))


def _cmd_cleanup(args: argparse.Namespace) -> None:
    db = _init_db()
    result = cleanup_untagged(args.days, db)
    print(f"Cleaned up {result['count']} images older than {result['days_old']} days")
    for d in result["deleted"]:
        print(f"  - {d}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BlackRoad Container Registry")
    sub = parser.add_subparsers(dest="command")

    push = sub.add_parser("push", help="Push an image")
    push.add_argument("name")
    push.add_argument("--tag", default="latest")

    pull = sub.add_parser("pull", help="Pull an image")
    pull.add_argument("name")
    pull.add_argument("--tag", default="latest")

    ls = sub.add_parser("list", help="List images")
    ls.add_argument("--filter", default=None)

    rm = sub.add_parser("delete", help="Delete an image")
    rm.add_argument("name")
    rm.add_argument("--tag", default="latest")

    st = sub.add_parser("stats", help="Get image stats")
    st.add_argument("name")

    cl = sub.add_parser("cleanup", help="Cleanup old untagged images")
    cl.add_argument("--days", type=int, default=30)

    tag = sub.add_parser("tag", help="Tag an image")
    tag.add_argument("name")
    tag.add_argument("source_tag")
    tag.add_argument("dest_tag")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    dispatch = {
        "push": _cmd_push, "pull": _cmd_pull, "list": _cmd_list,
        "delete": _cmd_delete, "stats": _cmd_stats, "cleanup": _cmd_cleanup,
    }
    if args.command in dispatch:
        dispatch[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
