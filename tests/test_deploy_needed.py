"""The demo deploys only when a commit changes what the image is built from."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("deploy_needed", ROOT / "deploy" / "cloudflare" / "deploy_needed.py")
deploy_needed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy_needed)


def test_bookkeeping_commits_do_not_deploy():
    deploy, reason = deploy_needed.decide(["docs/traffic/traffic.csv"])
    assert deploy is False and "outside the image" in reason
    deploy, _ = deploy_needed.decide(["reach/github.csv", "reach/latest.md", ".github/workflows/ci.yml", "AUTOMATION.md"])
    assert deploy is False
    assert deploy_needed.decide([]) == (False, "no files changed since the last deploy")


def test_anything_in_the_image_deploys():
    for path in ["portal/web.py", "docs/admin/backups.md", "docs/traffic/README.md", "README.md", "CHANGELOG.md",
                 "VERSION", "requirements.txt", "deploy/cloudflare/worker.js", "deploy/install.sh", "tests/conftest.py",
                 "conformance/run.py", "Dockerfile", ".dockerignore", "something/new.txt"]:
        deploy, reason = deploy_needed.decide([path, "docs/traffic/traffic.csv"])
        assert deploy is True, path
        assert path in reason


def test_prefix_rules_do_not_match_lookalikes():
    assert deploy_needed.outside_image("tools/traffic_log.py")
    assert not deploy_needed.outside_image("toolsmith/x.py")
    assert not deploy_needed.outside_image("docs/tools/x.md")


def test_outside_list_matches_the_dockerfile():
    """Every path listed as outside the image really is outside every COPY line."""
    dockerfile = (ROOT / "deploy" / "cloudflare" / "Dockerfile").read_text(encoding="utf-8")
    copied: set[str] = set()
    for line in dockerfile.splitlines():
        if line.startswith("COPY "):
            copied.update(line.split()[1:-1])
    for rule in deploy_needed.OUTSIDE_IMAGE:
        top = rule.rstrip("/")
        assert not any(src == top or src.startswith(top + "/") for src in copied), rule
        # A folder copied whole (COPY docs ./docs) reaches files inside it.
        if "/" in top:
            assert top.split("/")[0] not in copied or rule == "docs/traffic/traffic.csv", rule
    # The traffic log lives inside the copied docs/ folder; it rides along into
    # the image but nothing reads it there, which is why it is the one exception.
    assert "docs" in copied and not re.search(r"traffic\.csv", "\n".join(
        p.read_text(encoding="utf-8", errors="ignore") for p in (ROOT / "portal").rglob("*.py")))
