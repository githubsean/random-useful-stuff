#!/usr/bin/env python3
"""
llamacpp_changelog.py

Pulls the full release history (b-numbered builds) from the ggml-org/llama.cpp
GitHub repo and writes it out as a clean table of:

    version, date, description

Each "release" in llama.cpp corresponds to one CI build off master, and the
description is just the commit message(s) merged since the previous tag, so
this script effectively gives you a per-build changelog.

Output formats:
- CSV (always written): description flattened to a single plain-text line.
- Markdown (--markdown): same flattened plain-text description. Note that
  markdown tables can't represent multi-line content like bullet lists, so
  any bullets/formatting in the original release notes are lost here.
- HTML (--html): preserves the original formatting (bold text, links,
  bullet lists) exactly as it appears on GitHub, since HTML table cells can
  hold arbitrary block content. Use this if you want to copy descriptions
  verbatim without losing formatting.

Usage:
    python3 llamacpp_changelog.py
    python3 llamacpp_changelog.py --out changelog.csv --markdown changelog.md --html changelog.html
    python3 llamacpp_changelog.py --since b9800          # only fetch newer than this tag
    python3 llamacpp_changelog.py --token ghp_xxx         # use a GitHub token (higher rate limit)
    python3 llamacpp_changelog.py --max-pages 5           # limit how many pages (100/page) to pull

Notes:
- Unauthenticated GitHub API calls are capped at 60 requests/hour. Each request
  pulls up to 100 releases, so unauthenticated you can pull ~6000 releases/hour.
  If you hit the limit, pass --token with a GitHub personal access token (no
  special scopes needed for public repos) to raise the cap to 5000 req/hour.
- Re-running with --since will only fetch releases newer than that tag, useful
  for periodic incremental updates (e.g. a cron job appending to an existing CSV).
"""

import argparse
import csv
import html
import json
import re
import sys
import time
import urllib.request
import urllib.error

try:
    import markdown
except ImportError:
    print(
        "This script requires the 'markdown' package for HTML output.\n"
        "Install it with: pip install markdown --break-system-packages\n"
        "(or just: pip install markdown)",
        file=sys.stderr,
    )
    sys.exit(1)

REPO = "ggml-org/llama.cpp"
API_URL = f"https://api.github.com/repos/{REPO}/releases"


def fetch_page(page, per_page=100, token=None):
    url = f"{API_URL}?per_page={per_page}&page={page}"
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "llamacpp-changelog-script")
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(req) as resp:
            remaining = resp.headers.get("X-RateLimit-Remaining")
            reset = resp.headers.get("X-RateLimit-Reset")
            data = json.loads(resp.read().decode("utf-8"))
            return data, remaining, reset
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP error {e.code} fetching page {page}: {body}", file=sys.stderr)
        if e.code == 403:
            print("Likely rate-limited. Try again later or pass --token.", file=sys.stderr)
        sys.exit(1)


def _extract_inner(body):
    """Pull out the raw text inside the <details>...</details> wrapper that
    llama.cpp's release CI puts around the actual commit message(s). Falls
    back to cutting off at the first platform-links heading if no <details>
    block is present."""
    if not body:
        return ""
    text = body.strip()
    m = re.search(r"<details[^>]*>(.*?)</details>", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return re.split(r"\*\*(macOS|Linux|Windows|Android)", text)[0].strip()


def _linkify_refs(text):
    """Turn bare #1234 issue/PR refs and @username mentions into markdown
    links, matching how GitHub renders them."""
    text = re.sub(
        r"(?<!\w)#(\d+)",
        rf"[#\1](https://github.com/{REPO}/pull/\1)",
        text,
    )
    text = re.sub(
        r"(?<!\w)@([A-Za-z0-9-]+)",
        r"[@\1](https://github.com/\1)",
        text,
    )
    return text


def _ensure_blank_line_before_lists(text):
    """The python-markdown library (like most markdown parsers) only
    recognizes a bullet list if it's preceded by a blank line. llama.cpp's
    release bodies often go straight from a title line into a `* item`
    list with no blank line between them, so insert one where needed."""
    lines = text.split("\n")
    out = []
    for i, line in enumerate(lines):
        is_list_item = re.match(r"^\s*[-*+]\s", line)
        prev_is_list_or_blank = i == 0 or lines[i - 1].strip() == "" or re.match(r"^\s*[-*+]\s", lines[i - 1])
        if is_list_item and not prev_is_list_or_blank:
            out.append("")
        out.append(line)
    return "\n".join(out)


def extract_details_html(body):
    """Render the release description as real HTML (proper <ul>/<li> bullet
    lists, <strong> bold text, resolved links for #PR refs and @mentions)
    instead of leaving it as flattened markdown source. This matches how
    GitHub itself renders these release bodies."""
    inner = _extract_inner(body)
    if not inner:
        return ""

    prepped = _ensure_blank_line_before_lists(_linkify_refs(inner))
    return markdown.markdown(prepped)


def clean_body(body):
    """Flatten the release description to a single plain-text line, for the
    CSV / markdown-table outputs. Strips markdown list markers, link syntax,
    and any stray HTML tags, separating bullet items with ' | '."""
    inner = _extract_inner(body)
    if not inner:
        return ""

    # Separate bullet items with a clear delimiter before collapsing newlines,
    # so "* item one\n* item two" doesn't become an unreadable run-on sentence.
    inner = re.sub(r"^\s*[-*+]\s+", " | ", inner, flags=re.MULTILINE)
    # Strip markdown links: [text](url) -> text
    inner = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", inner)
    # Strip any HTML tags (e.g. stray <p>, <a>, <summary> on older releases)
    inner = re.sub(r"<[^>]+>", " ", inner)
    # Unescape HTML entities (&lt;, &gt;, &amp;, etc.)
    inner = html.unescape(inner)
    # Collapse whitespace/newlines into single spaces
    inner = re.sub(r"\s+", " ", inner).strip()
    # Tidy up spacing artifacts left from stripped tags, e.g. "( #123 )" -> "(#123)"
    inner = re.sub(r"\(\s+", "(", inner)
    inner = re.sub(r"\s+\)", ")", inner)
    # Drop a leading " | " left over if the body started with a bullet item
    inner = re.sub(r"^\s*\|\s*", "", inner)

    return inner


def main():
    ap = argparse.ArgumentParser(description="Fetch llama.cpp release changelog")
    ap.add_argument("--out", default="llamacpp_changelog.csv", help="CSV output path")
    ap.add_argument("--markdown", default=None, help="Optional markdown table output path (descriptions flattened to one line)")
    ap.add_argument("--html", default=None, help="Optional HTML table output path (preserves original formatting: bold, links, bullet lists)")
    ap.add_argument("--since", default=None, help="Stop once this tag (e.g. b9800) is reached")
    ap.add_argument("--token", default=None, help="GitHub token for higher rate limits")
    ap.add_argument("--max-pages", type=int, default=200, help="Safety cap on number of pages (100 releases/page)")
    args = ap.parse_args()

    rows = []
    page = 1
    hit_since = False

    while page <= args.max_pages:
        data, remaining, reset = fetch_page(page, token=args.token)
        if not data:
            break  # no more releases

        for rel in data:
            tag = rel.get("tag_name", "")
            published = rel.get("published_at", "")
            raw_body = rel.get("body", "")
            desc = clean_body(raw_body)
            desc_html = extract_details_html(raw_body)
            rows.append((tag, published, desc, desc_html))

            if args.since and tag == args.since:
                hit_since = True
                break

        print(f"Fetched page {page} ({len(data)} releases). Rate limit remaining: {remaining}", file=sys.stderr)

        if hit_since or len(data) < 100:
            break

        page += 1

        # Be polite / avoid hammering the API
        if remaining is not None and int(remaining) <= 1:
            wait = max(int(reset) - int(time.time()), 1) if reset else 60
            print(f"Rate limit nearly exhausted, sleeping {wait}s...", file=sys.stderr)
            time.sleep(wait)

    # Write CSV (plain-text description column)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["version", "date", "description"])
        writer.writerows((tag, published, desc) for tag, published, desc, _ in rows)
    print(f"Wrote {len(rows)} releases to {args.out}", file=sys.stderr)

    # Optional markdown (plain-text description; markdown tables can't hold
    # multi-line content like bullet lists, so this is flattened to one line)
    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8") as f:
            f.write("| Version | Date | Description |\n")
            f.write("|---|---|---|\n")
            for tag, published, desc, _ in rows:
                date_only = published.split("T")[0] if published else ""
                desc_escaped = desc.replace("|", "\\|")
                f.write(f"| {tag} | {date_only} | {desc_escaped} |\n")
        print(f"Wrote markdown table to {args.markdown}", file=sys.stderr)

    # Optional HTML (preserves original formatting: bold, links, bullet lists)
    if args.html:
        with open(args.html, "w", encoding="utf-8") as f:
            f.write("<!DOCTYPE html>\n<html>\n<head>\n<meta charset=\"utf-8\">\n")
            f.write(f"<title>llama.cpp changelog</title>\n")
            f.write("""<style>
body { font-family: system-ui, sans-serif; margin: 2rem; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #ccc; padding: 8px 12px; text-align: left; vertical-align: top; }
th { background: #f0f0f0; position: sticky; top: 0; }
td:nth-child(1) { white-space: nowrap; font-family: monospace; }
td:nth-child(2) { white-space: nowrap; }
tr:nth-child(even) { background: #fafafa; }
td p { margin: 0 0 0.5em 0; }
td p:last-child { margin-bottom: 0; }
td ul, td ol { margin: 0.3em 0; padding-left: 1.3em; }
</style>
</head>
<body>
""")
            f.write(f"<h1>llama.cpp release changelog</h1>\n")
            f.write("<table>\n<thead><tr><th>Version</th><th>Date</th><th>Description</th></tr></thead>\n<tbody>\n")
            for tag, published, _, desc_html in rows:
                date_only = published.split("T")[0] if published else ""
                f.write(f"<tr><td>{tag}</td><td>{date_only}</td><td>{desc_html}</td></tr>\n")
            f.write("</tbody>\n</table>\n</body>\n</html>\n")
        print(f"Wrote HTML table to {args.html}", file=sys.stderr)


if __name__ == "__main__":
    main()