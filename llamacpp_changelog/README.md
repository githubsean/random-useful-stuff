# llamacpp_changelog.py

With llama.cpp pushing out new releases so often, it can be difficult sometimes
to easily track what has changed. I wanted a simple table output of each
release verson on github and the details of what had changed.

This code pulls the full release history (b-numbered builds) from the ggml-org/llama.cpp
GitHub repo and writes it out as a clean table of:

    version, date, description

Each "release" in llama.cpp corresponds to one CI build off master, and the
description is just the commit message(s) merged since the previous tag, so
this script effectively gives you a per-build changelog.

## Output formats

- **CSV** (always written): description flattened to a single plain-text line.
- **Markdown** (`--markdown`): same flattened plain-text description. Note that
  markdown tables can't represent multi-line content like bullet lists, so
  any bullets/formatting in the original release notes are lost here.
- **HTML** (`--html`): preserves the original formatting (bold text, links,
  bullet lists) exactly as it appears on GitHub, since HTML table cells can
  hold arbitrary block content. Use this if you want to copy descriptions
  verbatim without losing formatting.

## Usage

```bash
python3 llamacpp_changelog.py
python3 llamacpp_changelog.py --out changelog.csv --markdown changelog.md --html changelog.html
python3 llamacpp_changelog.py --since b9800          # only fetch newer than this tag
python3 llamacpp_changelog.py --token ghp_xxx         # use a GitHub token (higher rate limit)
python3 llamacpp_changelog.py --max-pages 5           # limit how many pages (100/page) to pull
```

## Notes

- Unauthenticated GitHub API calls are capped at 60 requests/hour. Each request
  pulls up to 100 releases, so unauthenticated you can pull ~6000 releases/hour.
  If you hit the limit, pass `--token` with a GitHub personal access token (no
  special scopes needed for public repos) to raise the cap to 5000 req/hour.
- Re-running with `--since` will only fetch releases newer than that tag, useful
  for periodic incremental updates (e.g. a cron job appending to an existing CSV).

---

*This project was co-authored using AI (Claude.ai).*