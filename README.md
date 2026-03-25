<!-- BlackRoad SEO Enhanced -->

# ulackroad container registry

> Part of **[BlackRoad OS](https://blackroad.io)** — Sovereign Computing for Everyone

[![BlackRoad OS](https://img.shields.io/badge/BlackRoad-OS-ff1d6c?style=for-the-badge)](https://blackroad.io)
[![BlackRoad-Cloud](https://img.shields.io/badge/Org-BlackRoad-Cloud-2979ff?style=for-the-badge)](https://github.com/BlackRoad-Cloud)

**ulackroad container registry** is part of the **BlackRoad OS** ecosystem — a sovereign, distributed operating system built on edge computing, local AI, and mesh networking by **BlackRoad OS, Inc.**

### BlackRoad Ecosystem
| Org | Focus |
|---|---|
| [BlackRoad OS](https://github.com/BlackRoad-OS) | Core platform |
| [BlackRoad OS, Inc.](https://github.com/BlackRoad-OS-Inc) | Corporate |
| [BlackRoad AI](https://github.com/BlackRoad-AI) | AI/ML |
| [BlackRoad Hardware](https://github.com/BlackRoad-Hardware) | Edge hardware |
| [BlackRoad Security](https://github.com/BlackRoad-Security) | Cybersecurity |
| [BlackRoad Quantum](https://github.com/BlackRoad-Quantum) | Quantum computing |
| [BlackRoad Agents](https://github.com/BlackRoad-Agents) | AI agents |
| [BlackRoad Network](https://github.com/BlackRoad-Network) | Mesh networking |

**Website**: [blackroad.io](https://blackroad.io) | **Chat**: [chat.blackroad.io](https://chat.blackroad.io) | **Search**: [search.blackroad.io](https://search.blackroad.io)

---


> BlackRoad Cloud Infrastructure: blackroad-container-registry

Part of the [BlackRoad OS](https://blackroad.io) ecosystem — [BlackRoad-Cloud](https://github.com/BlackRoad-Cloud)

---

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
