from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from content_factory.package_writer import write_content_package_v1


def test_writes_content_package_v1_layout(tmp_path: Path) -> None:
    repo_root = tmp_path
    md = """---\ntitle: My Test Title\ndescription: x\npublishedAt: 2099-01-01\ncategories: [tech]\nproducts: []\npicks: []\n---\n\n## Intro\n\nHello\n"""

    out = write_content_package_v1(
        repo_root=repo_root,
        brand_id="the_product_wheel",
        run_id="run_123",
        publish_date=date(2099, 1, 1),
        post_markdown=md,
    )

    assert out.package_dir.exists()
    assert out.manifest_path.exists()
    assert out.post_path.exists()

    manifest = json.loads(out.manifest_path.read_text(encoding="utf-8"))
    assert manifest["version"] == "1"
    assert manifest["brand_id"] == "the_product_wheel"
    assert manifest["run_id"] == "run_123"
    assert manifest["publish_date"] == "2099-01-01"
    assert manifest["slug"] == "my-test-title"
    assert manifest["outputs"] == [{"kind": "blog_post", "path": "post.md"}]

    post_md = out.post_path.read_text(encoding="utf-8")
    assert "title: My Test Title" in post_md
