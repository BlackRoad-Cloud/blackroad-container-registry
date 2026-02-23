"""Tests for BlackRoad Container Registry."""
import time
import pytest
from container_registry import (
    Layer, Image, push_image, pull_image, list_images, delete_image,
    get_image_stats, cleanup_untagged, tag_image, _init_db,
)


def make_db(tmp_path):
    return _init_db(tmp_path / "test_registry.db")


class TestLayer:
    def test_from_content_bytes(self):
        layer = Layer.from_content(b"hello world")
        assert layer.digest.startswith("sha256:")
        assert layer.size_bytes == 11

    def test_from_content_str(self):
        layer = Layer.from_content("test content")
        assert layer.digest.startswith("sha256:")

    def test_unique_digests(self):
        l1 = Layer.from_content("content1")
        l2 = Layer.from_content("content2")
        assert l1.digest != l2.digest


class TestImage:
    def test_basic_image(self):
        img = Image(name="nginx", tag="latest")
        assert img.name == "nginx"
        assert img.tag == "latest"
        assert img.digest.startswith("sha256:")

    def test_full_ref(self):
        img = Image(name="nginx", tag="1.25")
        assert img.full_ref == "nginx:1.25"

    def test_default_tag(self):
        img = Image(name="nginx", tag="")
        assert img.tag == "latest"

    def test_manifest_structure(self):
        img = Image(name="nginx", tag="latest")
        m = img.manifest()
        assert m["schemaVersion"] == 2
        assert "config" in m
        assert "layers" in m

    def test_pushed_at_iso(self):
        img = Image(name="test", tag="v1", pushed_at=0)
        assert "1970" in img.pushed_at_iso


class TestPushImage:
    def test_basic_push(self, tmp_path):
        db = make_db(tmp_path)
        img = push_image("myapp", "v1.0", db=db)
        assert img.name == "myapp"
        assert img.tag == "v1.0"
        assert img.size_mb > 0
        assert len(img.layers) > 0

    def test_upsert_on_push(self, tmp_path):
        db = make_db(tmp_path)
        push_image("myapp", "latest", db=db)
        push_image("myapp", "latest", db=db)
        images = list_images(db=db)
        assert len(images) == 1

    def test_custom_layers(self, tmp_path):
        db = make_db(tmp_path)
        layers = [Layer.from_content("layer1"), Layer.from_content("layer2")]
        img = push_image("app", "v2", layers=layers, db=db)
        assert len(img.layers) == 2


class TestPullImage:
    def test_pull_existing(self, tmp_path):
        db = make_db(tmp_path)
        push_image("nginx", "stable", db=db)
        img = pull_image("nginx", "stable", db=db)
        assert img is not None
        assert img.name == "nginx"

    def test_pull_increments_count(self, tmp_path):
        db = make_db(tmp_path)
        push_image("nginx", "latest", db=db)
        pull_image("nginx", "latest", db=db)
        pull_image("nginx", "latest", db=db)
        img = pull_image("nginx", "latest", db=db)
        assert img.pulled_count == 3

    def test_pull_nonexistent_returns_none(self, tmp_path):
        db = make_db(tmp_path)
        result = pull_image("nonexistent", "latest", db=db)
        assert result is None


class TestListImages:
    def test_list_all(self, tmp_path):
        db = make_db(tmp_path)
        push_image("app1", "v1", db=db)
        push_image("app2", "v1", db=db)
        images = list_images(db=db)
        assert len(images) == 2

    def test_filter_by_name(self, tmp_path):
        db = make_db(tmp_path)
        push_image("nginx", "v1", db=db)
        push_image("redis", "v1", db=db)
        images = list_images("nginx", db=db)
        assert len(images) == 1
        assert images[0].name == "nginx"

    def test_empty_registry(self, tmp_path):
        db = make_db(tmp_path)
        assert list_images(db=db) == []


class TestDeleteImage:
    def test_delete_existing(self, tmp_path):
        db = make_db(tmp_path)
        push_image("app", "v1", db=db)
        result = delete_image("app", "v1", db=db)
        assert result is True
        assert list_images(db=db) == []

    def test_delete_nonexistent_returns_false(self, tmp_path):
        db = make_db(tmp_path)
        result = delete_image("ghost", "latest", db=db)
        assert result is False

    def test_delete_one_tag_keeps_others(self, tmp_path):
        db = make_db(tmp_path)
        push_image("app", "v1", db=db)
        push_image("app", "v2", db=db)
        delete_image("app", "v1", db=db)
        images = list_images(db=db)
        assert len(images) == 1
        assert images[0].tag == "v2"


class TestGetImageStats:
    def test_stats_for_existing(self, tmp_path):
        db = make_db(tmp_path)
        push_image("myapp", "v1", db=db)
        push_image("myapp", "v2", db=db)
        stats = get_image_stats("myapp", db=db)
        assert stats["tag_count"] == 2
        assert stats["name"] == "myapp"

    def test_stats_for_nonexistent(self, tmp_path):
        db = make_db(tmp_path)
        stats = get_image_stats("ghost", db=db)
        assert "error" in stats


class TestCleanupUntagged:
    def test_cleanup_old_images(self, tmp_path):
        db = make_db(tmp_path)
        # Insert an old image directly
        old_time = time.time() - (31 * 86400)
        db.execute(
            "INSERT INTO images (name,tag,digest,size_mb,pushed_at,pulled_count) VALUES (?,?,?,?,?,?)",
            ("old-app", "v0.1", "sha256:abc", 10.0, old_time, 0)
        )
        db.commit()
        result = cleanup_untagged(days_old=30, db=db)
        assert result["count"] == 1
        assert "old-app:v0.1" in result["deleted"]

    def test_recent_images_not_cleaned(self, tmp_path):
        db = make_db(tmp_path)
        push_image("fresh", "latest", db=db)
        result = cleanup_untagged(days_old=30, db=db)
        assert result["count"] == 0
