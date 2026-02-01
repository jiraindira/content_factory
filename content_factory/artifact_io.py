from __future__ import annotations

import json
from pathlib import Path

from content_factory.artifact_models import ContentArtifact


def write_content_artifact(*, repo_root: Path, artifact: ContentArtifact) -> Path:
    out_dir = repo_root / "content_factory" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{artifact.run_id}.json"
    out_path.write_text(json.dumps(artifact.to_dict(), indent=2, sort_keys=False), encoding="utf-8")
    return out_path
