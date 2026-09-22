# Contributing

Keep the public repository focused on the application and documentation someone can use today. These conventions apply to human contributors and coding agents.

## Where files belong

| Material | Location |
| --- | --- |
| Short overview and setup | `README.md` |
| Maintained workflows and compatibility guides | `docs/` |
| Release summary, measured checks and known limits | `releases/vX.Y.Z.md`, with a concise entry in `CHANGELOG.md` |
| Approved current roadmap or security policy | `ROADMAP.md` or `SECURITY.md`, when deliberately published |
| Temporary implementation goals, plans, checkpoints, handoffs and art prompts | `planning/<topic>/` — ignored by Git |
| Raw test logs, evaluation output, screenshots and local bundles | `test-results/<topic>/` — ignored by Git |
| Reusable test fixtures and evaluation tools | `tests/` and `scripts/` |
| Shipped artwork and its maintained design guidance | `public/`, `design/brand.md`, and selected illustrated guides |

Only README, changelog, contributing guidance, an approved roadmap and a security policy belong in root Markdown files. Update an existing guide before adding another. Do not commit agent scratch notes or a new status file for every work session. Keep local agent instructions local.

## Finishing work

Before publication, fold lasting behavior and compatibility information into the relevant guide. Summarize actual verification and limitations in the release notes; raw logs stay local. Commit a reviewed file list and preserve unrelated work.

Completed development records already published with v0.9.0 remain available in [that tagged snapshot](https://github.com/vantaloomin/prosperos-study/tree/v0.9.0). Historical evidence links use the tag, so cleaning the current branch does not erase or relocate the original record. Future release summaries should be self-contained; attach substantial supporting artifacts to the GitHub release when needed. Never rewrite a published tag to tidy documentation.

## Checks

See [development setup](docs/development.md) for the application checks. The small repository check needs only Python's standard library:

```sh
python scripts/check_repository.py
python scripts/check_repository.py --staged
python -m unittest discover -s tests -p test_repository_hygiene.py
```

The first command checks current files; `--staged` checks exactly what Git will commit, including Markdown links against the staged file list. It rejects unexpected root documents, session records under `docs/`, art prompts and accidentally tracked local working directories. `.gitignore` prevents common mistakes during ordinary staging; the check also catches forced additions.

`check.ps1` runs it before the application suite. The **Repository hygiene** GitHub workflow runs it and its regression tests on pushes to `main` and on pull requests. A failing workflow reports the problem; branch protection must separately require it if merges should be blocked.
