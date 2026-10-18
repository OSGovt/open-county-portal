"""Decide whether a commit needs a demo deploy.

The Deploy demo workflow runs this after CI passes on main. It compares the
commit with the last commit the workflow deployed and answers "no" when every
changed file is outside what the demo image is built from (see Dockerfile in
this folder): workflows, maintenance tools, reach measurements, the traffic
log, and the project documents that are not copied into the image. Everything
else, and anything it cannot verify, means "yes".

    python3 deploy/cloudflare/deploy_needed.py --repo OWNER/REPO --head SHA --event workflow_run

Prints the decision and the reason; also writes `deploy=true|false` to
$GITHUB_OUTPUT when that variable is set. Needs `gh` and `git` on PATH when
run for real; the path rules themselves are plain functions, tested in
tests/test_deploy_needed.py.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

# Files and folders the demo image never contains. A commit that touches only
# these has nothing to deploy. Folders end with "/". Keep this list in step
# with the COPY lines in deploy/cloudflare/Dockerfile: a path is listed here
# only if no COPY line reaches it.
OUTSIDE_IMAGE = (
    ".github/",
    "tools/",
    "reach/",
    "docs/traffic/traffic.csv",
    ".gitignore",
    "ACCESSIBILITY.md",
    "AUTOMATION.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "GOVERNANCE.md",
    "MAINTAINERS.md",
    "REACH.md",
    "SECURITY.md",
    "SUPPORT.md",
)


def outside_image(path: str) -> bool:
    """True when a changed file cannot alter the demo image or its Worker."""
    for rule in OUTSIDE_IMAGE:
        if rule.endswith("/"):
            if path.startswith(rule):
                return True
        elif path == rule:
            return True
    return False


def decide(changed: list[str]) -> tuple[bool, str]:
    """(deploy?, reason) for a list of changed paths since the last deploy."""
    if not changed:
        return False, "no files changed since the last deploy"
    inside = [p for p in changed if not outside_image(p)]
    if not inside:
        return False, f"only files outside the image changed: {', '.join(sorted(changed))}"
    return True, f"the image changes: {', '.join(sorted(inside)[:10])}"


def run(cmd: list[str]) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()


def last_deployed_sha(repo: str) -> str | None:
    """Head commit of the newest successful Deploy demo run on main, if any."""
    out = run(["gh", "api", f"repos/{repo}/actions/workflows/deploy-demo.yml/runs?status=success&branch=main&per_page=1"])
    runs = json.loads(out).get("workflow_runs") or []
    return runs[0].get("head_sha") if runs else None


def changed_since(base: str, head: str) -> list[str]:
    subprocess.run(["git", "fetch", "--no-tags", "--depth=1", "origin", base], check=True, capture_output=True)
    out = run(["git", "diff", "--name-only", base, head])
    return [line for line in out.splitlines() if line]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", required=True, help="OWNER/REPO")
    ap.add_argument("--head", required=True, help="commit being considered")
    ap.add_argument("--event", required=True, help="the workflow's github.event_name")
    args = ap.parse_args(argv)

    if args.event != "workflow_run":
        deploy, reason = True, f"started by {args.event}"
    else:
        try:
            base = last_deployed_sha(args.repo)
            if not base:
                deploy, reason = True, "no earlier successful deploy to compare with"
            elif base == args.head:
                deploy, reason = False, f"{args.head[:7]} is already deployed"
            else:
                deploy, reason = decide(changed_since(base, args.head))
                reason += f" (compared with {base[:7]})"
        except (subprocess.CalledProcessError, json.JSONDecodeError, OSError) as exc:
            deploy, reason = True, f"could not compare with the last deploy: {exc}"

    print(f"deploy={'true' if deploy else 'false'}: {reason}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            fh.write(f"deploy={'true' if deploy else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
