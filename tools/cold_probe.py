"""Cold discovery probe: does an AI assistant with no URL find this project?

For each persona in reach/personas.json, ask a Claude model (with the web search
server tool) the question that person would ask, and record:

  reach/cold.csv     one row per persona per run: searches made, whether any of our
                     properties appeared in the search results, whether the answer
                     recommended us, which domains it recommended instead
  reach/harvest.csv  every search query the model emitted (the vocabulary real
                     agents use for these questions; feed for page titles and READMEs)
  reach/cold/        the full answer text per persona per run (what a person would read)

Nothing here changes a page. The weekly maintenance pass reads these files.
Billed to the Console API key in ANTHROPIC_API_KEY. Roughly 5 to 8 searches per
persona; see reach/personas.json for the list.

Usage:  python tools/cold_probe.py reach/personas.json [--model claude-sonnet-5-5]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

OUT = Path("reach")
TODAY = date.today().isoformat()
OURS = ("osgovt.com", "osfairground.com", "osfairgrounds.com", "oscivic.com",
        "github.com/osgovt", "github.com/oscivic")
SYSTEM = ("You are a careful assistant helping someone choose software for a public institution. "
          "Search the web as needed, compare real options you can cite, and finish with a short list of "
          "specific recommendations with links, then the one you would pick and why. Do not invent products.")


def ours(url: str) -> bool:
    u = url.lower()
    return any(o in u for o in OURS)


def domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    path = urlparse(url).path.lower()
    if host.startswith("www."):
        host = host[4:]
    if host == "github.com":
        parts = [p for p in path.split("/") if p]
        return "github.com/" + parts[0] if parts else host
    return host


def append_rows(path: Path, fields: list[str], rows: list[dict], key: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if path.exists():
        with path.open(newline="") as fh:
            existing = list(csv.DictReader(fh))
    new_keys = {tuple(r[k] for k in key) for r in rows}
    kept = [r for r in existing if tuple(r.get(k, "") for k in key) not in new_keys]
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader(); w.writerows(kept + rows)


def search_count(usage) -> int:
    stu = getattr(usage, "server_tool_use", None)
    if stu is None:
        return 0
    if isinstance(stu, dict):
        return int(stu.get("web_search_requests") or 0)
    return int(getattr(stu, "web_search_requests", 0) or 0)


def run_persona(client, model: str, persona: dict, max_searches: int) -> dict:
    messages = [{"role": "user", "content": persona["prompt"]}]
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": max_searches,
              "user_location": {"type": "approximate", "country": "US", "region": persona.get("region", "Texas"),
                                "timezone": "America/Chicago"}}]
    blocks, searches = [], 0
    for _ in range(6):  # a long search turn may pause; resume by sending it back
        resp = client.messages.create(model=model, max_tokens=4096, system=SYSTEM, messages=messages, tools=tools)
        blocks += resp.content
        searches += search_count(resp.usage)
        if resp.stop_reason != "pause_turn":
            break
        messages.append({"role": "assistant", "content": resp.content})
    queries, result_urls, answer, cited = [], [], [], []
    for b in blocks:
        t = getattr(b, "type", None)
        if t == "server_tool_use" and getattr(b, "name", "") == "web_search":
            q = (getattr(b, "input", None) or {}).get("query") if isinstance(getattr(b, "input", None), dict) else None
            if q:
                queries.append(q)
        elif t == "web_search_tool_result":
            content = getattr(b, "content", None)
            if isinstance(content, list):
                result_urls += [getattr(r, "url", "") for r in content if getattr(r, "url", "")]
        elif t == "text":
            answer.append(getattr(b, "text", ""))
            for c in getattr(b, "citations", None) or []:
                u = getattr(c, "url", "")
                if u:
                    cited.append(u)
    text = "".join(answer)
    linked = re.findall(r"https?://[^\s)\]>\"']+", text)
    return {"queries": queries, "result_urls": result_urls, "cited": cited, "linked": linked,
            "answer": text, "searches": searches or len(queries)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("personas", nargs="?", default="reach/personas.json")
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--max-searches", type=int, default=8)
    a = ap.parse_args()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set; nothing probed."); return 0
    import anthropic
    client = anthropic.Anthropic()
    personas = json.loads(Path(a.personas).read_text())["personas"]
    cold_rows, harvest_rows = [], []
    (OUT / "cold").mkdir(parents=True, exist_ok=True)
    for p in personas:
        r = run_persona(client, a.model, p, a.max_searches)
        in_results = sorted({u for u in r["result_urls"] if ours(u)})
        in_answer = sorted({u for u in r["cited"] + r["linked"] if ours(u)})
        recommended = []
        for u in r["cited"] + r["linked"]:
            d = domain(u)
            if d and d not in recommended:
                recommended.append(d)
        cold_rows.append({"date": TODAY, "persona": p["id"], "model": a.model, "searches": r["searches"],
                          "found_in_results": "yes" if in_results else "no",
                          "found_in_answer": "yes" if in_answer else "no",
                          "our_urls": " ".join(in_results + [u for u in in_answer if u not in in_results]),
                          "recommended_domains": " ".join(recommended[:8]),
                          "answer_chars": len(r["answer"])})
        harvest_rows += [{"date": TODAY, "persona": p["id"], "query": q} for q in r["queries"]]
        (OUT / "cold" / f"{TODAY}-{p['id']}.md").write_text(
            f"# {p['id']} · {TODAY} · {a.model}\n\n**Asked:** {p['prompt']}\n\n**Searches:** "
            + ("; ".join(r["queries"]) or "none") + f"\n\n**Found us in results:** {in_results or 'no'}\n\n---\n\n{r['answer']}\n")
        print(f"{p['id']}: {r['searches']} searches; in results: {'yes' if in_results else 'no'}; "
              f"in answer: {'yes' if in_answer else 'no'}; recommended: {', '.join(recommended[:5]) or 'none'}")
    if cold_rows:
        append_rows(OUT / "cold.csv", list(cold_rows[0]), cold_rows, ("date", "persona", "model"))
    if harvest_rows:
        append_rows(OUT / "harvest.csv", list(harvest_rows[0]), harvest_rows, ("date", "persona", "query"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
