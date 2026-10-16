# Contribution Compass

[![CI](https://github.com/amirimi/contribution-compass/actions/workflows/ci.yml/badge.svg)](https://github.com/amirimi/contribution-compass/actions/workflows/ci.yml)
[![Pages](https://github.com/amirimi/contribution-compass/actions/workflows/pages.yml/badge.svg)](https://amirimi.github.io/contribution-compass/)
[![License: MIT](https://img.shields.io/badge/license-MIT-4c9aff.svg)](LICENSE)

> **V2 rewrite in progress:** the previous repository-monitoring and issue-feed prototype has been
> retired. The current branch is a deliberately small foundation, not a usable recommender yet.

Contribution Compass is becoming a personalized **OSS investment recommender**. It will help a
serious engineer decide which few open-source projects deserve the next several months of their
attention, given their background, desired growth, career goals, and the project’s ability to absorb
outside contributors.

**Product rule: project first, issue second.** Concrete GitHub issues become calls to action only
after their repository has been judged worth a sustained investment.

Read the authoritative [product and architecture specification](docs/product-spec-v2.md).

## Product direction

```text
developer profile
→ semantic and dependency neighborhood
→ candidate discovery
→ evidence collection
→ hard taste floors
→ Fit / Absorption / Upside
→ Pareto shortlist and diverse portfolio
→ 2–4 concrete issues per recommended project
```

The final output should feel like:

> These are the few open-source projects where your next six months of effort are most likely to
> teach you something, matter to the community, and strengthen your engineering career—and here is
> the evidence.

## Reset status

The August 2026 reset removed the v1 product model and all generated v1 artifacts:

- fixed repository groups and Project Sensors;
- daily Signals, full snapshots, Observation Events, state, and reports;
- Contribution Lead and Triage Lead scoring;
- Hacker News, news feeds, RSS, catalog overlays, and browser-only personalization;
- catalog-shaped CLI and MCP tools;
- the scheduled collector that would otherwise regenerate obsolete output.

The retained foundation is intentionally narrow:

- Python 3.12, `uv`, Ruff, mypy, and pytest;
- domain/application/adapter/controller/view separation;
- bounded GitHub transport and pagination;
- dependency-manifest parsing and package-to-repository resolution;
- Jinja2 static publication and GitHub Pages;
- an MCP transport entry point with a rewrite-status resource;
- GitHub Actions CI;
- evidence/measurement/taste separation as an architectural invariant.

## Development

Requirements: Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --all-extras
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
uv run contribution-compass site
```

The generated reset page is written to `.site/`. No model credential is required. Future GitHub
profile, discovery, and evidence commands will use `GITHUB_TOKEN`.

## Architecture

```text
src/contribution_compass/
  domain/          factual, transport-independent concepts
  application/     recommendation use cases as they are validated
  ports.py         seams introduced only when real adapters vary
  adapters/        GitHub, manifests, and package registries
  controllers/     CLI and MCP transports
  views/           packaged Jinja2 static presentation
```

The intended v2 domain is described in [CONTEXT.md](CONTEXT.md). Architectural decisions live in
[docs/adr](docs/adr).

## Contributing

The rewrite is validation-first. Please read [CONTRIBUTING.md](CONTRIBUTING.md) and discuss a task
before implementing a broad feature. The first milestone is proving project evaluation quality—not
maximizing repositories indexed or commands shipped.

## License and attribution

MIT—see [LICENSE](LICENSE). Some retained GitHub and dependency-discovery patterns originated in or
were adapted during work based on the MIT-licensed
[agents-radar](https://github.com/duanyytop/agents-radar); see [NOTICE.md](NOTICE.md).
