# BlackRoad Container Registry

> SQLite-backed container image registry with content-addressable layer storage and OCI-compatible manifests.

## Features

- `Image` dataclass with OCI-compatible manifest generation
- `Layer` with SHA-256 content-addressable digests
- `push_image()`, `pull_image()`, `list_images()`, `delete_image()`
- `get_image_stats()` — pulls, sizes, tags per repository
- `cleanup_untagged()` — remove stale images older than N days
- `tag_image()` — create tag aliases
- Pull count tracking with client IP audit log
- SQLite with WAL mode for concurrent reads
- CLI: `push`, `pull`, `list`, `delete`, `stats`, `cleanup`, `tag`

## Usage

```bash
# Push an image
python src/container_registry.py push myapp --tag v1.2.3

# Pull an image
python src/container_registry.py pull myapp --tag v1.2.3

# List all images
python src/container_registry.py list
python src/container_registry.py list --filter myapp

# Get stats for a repository
python src/container_registry.py stats myapp

# Clean up old images
python src/container_registry.py cleanup --days 30
```

## Tests

```bash
pytest tests/ -v --cov=src
```
