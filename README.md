# skill-hub

A starter kit for standing up your own agent-skill marketplace. Clone it, set your hub name and host, add your skills, and you get QA-gated `SKILL.md` packages, semantic releases, a static marketplace page on the host of your choice, and install paths for Claude Code, Cursor, and GitHub Copilot.

skill-hub is not a marketplace itself. It is the scaffolding for yours: everything that identifies your hub lives in one config file, and the skills are yours.

> **Work in progress.** The skill contract and the QA guard work today. Releases, the marketplace page and client install paths are next; see [Roadmap](#roadmap).

## What you get

| Piece | What it does | Status |
|---|---|---|
| **Skill contract** | Each skill is a folder under `src/` with a `SKILL.md` that follows the [Agent Skills specification](https://agentskills.io/specification), so it installs in any client that reads the spec | Available |
| **QA guard** | `skill-hub qa` checks your hub config and every skill: valid frontmatter, a name that matches its folder, a SemVer version, Python that compiles, and no committed secrets. It runs locally and on every pull request | Available |
| **Semantic releases** | Conventional commits (`feat:`, `fix:`) drive version bumps and changelogs through [Release Please](https://github.com/googleapis/release-please), one version per skill | Planned |
| **Marketplace page** | A static, browsable catalog of your skills, built from `src/` and deployed to the host you choose (no GitHub Pages lock-in) | Planned |
| **Client install paths** | Install a skill from your hub into Claude Code, Cursor or GitHub Copilot by a documented path | Planned |
| **Skill scaffolding** | `skill-hub new-skill <name>` creates a skill that already passes QA | Planned |

## Quick start

You need [uv](https://docs.astral.sh/uv/). It installs a matching Python for you, and there is no Node toolchain.

```bash
git clone <your copy of this repo> my-hub
cd my-hub
uv sync
uv run skill-hub qa
```

A fresh clone passes with two warnings. They are reminders to make the hub yours:

1. **Edit `hub.yml`.** Set `hub.name` (lowercase letters, digits and single hyphens), `display_name`, `owner`, `description` and `repo_url`. Every skill-hub command reads identity from this file and nowhere else.
2. **Replace the example skill.** `src/example-skill/` shows the shape of a skill. Rewrite it, or delete it once you have your own.
3. **Run `uv run skill-hub qa` again.** With no warnings left, your hub is ready for skills.

## Layout

```text
hub.yml                    your hub's identity and QA options (yours to edit)
src/<skill>/SKILL.md       your skills, one folder each (yours)
src/<skill>/...            optional scripts/, references/, assets/
skill_hub/                 the QA tool (part of the kit)
tests/                     the kit's own tests
.github/workflows/qa.yml   runs tests and skill-hub qa on every pull request
```

You own `hub.yml` and `src/`. Everything else belongs to the kit, which keeps pulling in kit updates simple. New config keys are always optional with a default, so your `hub.yml` keeps working.

## Writing a skill

A skill is a folder whose name matches the `name` in its `SKILL.md`:

```markdown
---
name: changelog-formatter
description: "Formats changelog entries. Use when the user asks to write or tidy a changelog."
metadata:
  version: "1.0.0" # x-release-please-version
---

# Changelog formatter

Instructions for the agent go here.
```

The rules QA enforces:

- **Frontmatter keys:** only the six from the Agent Skills spec: `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`. Strict consumers such as claude.ai uploads reject anything else. If your hub only targets Claude Code, you can allow its extra keys (for example `when_to_use`) in `hub.yml` under `qa.allow_keys`.
- **`name`:** 1 to 64 characters of lowercase letters, digits and single hyphens, matching the folder name.
- **`description`:** up to 1024 characters. Say what the skill does and when to use it, since that is how agents decide to load it.
- **Version:** a quoted SemVer string in `metadata.version`. A top-level `version` key is not part of the spec and fails QA. Keep the `# x-release-please-version` marker on that line; release automation will use it.
- **Secrets:** every file in a skill, hidden files included, is scanned for known token shapes and credential assignments. For a deliberate example in documentation, put `skill-hub: allow-secret` on that line.

## QA checks

`uv run skill-hub qa` prints one line per finding and exits non-zero on any error. Add `--strict` to fail on warnings too, or `--root PATH` to check another hub. Findings never print the value that triggered them, so a leaked secret doesn't end up in your CI logs.

| ID | Checks | Level |
|---|---|---|
| H1 | `hub.yml` exists and is a regular file | error |
| H2 | `hub.yml` is UTF-8, valid YAML (no duplicate or merge keys) and a mapping | error |
| H3 | `hub.name`, `display_name`, `owner`, `description` and `repo_url` are filled in | error |
| H4 | `hub.name` uses lowercase letters, digits and single hyphens | error |
| H5 | `qa` is a mapping and `qa.allow_keys` is a list of strings | error |
| H6 | `hub.name` or `repo_url` is still the kit's default | warning |
| S1 | The skill has a `SKILL.md` | error |
| S2 | `SKILL.md` is UTF-8 and opens with a `---` frontmatter block | error |
| S3 | The frontmatter is valid YAML and a mapping | error |
| S4 | `name` is valid and matches the folder | error |
| S5 | `description` is present and at most 1024 characters | error |
| S6 | No top-level keys outside the spec (and `qa.allow_keys`) | error |
| S7 | `metadata.version` is a quoted SemVer string | error |
| S8 | `metadata`, `compatibility`, `license` and `allowed-tools` have the right types and lengths | error |
| S9 | Every `.py` file compiles | error |
| S10 | No secrets in any file of the skill | error |
| S11 | `SKILL.md` has instructions after the frontmatter | warning |
| S12 | Symlinks and non-regular files are skipped | warning |
| S13 | A file or folder in the skill could not be read | error |
| S14 | `description` is still the placeholder written by `skill-hub new-skill` | warning |
| R1 | `src/` exists and can be read | error |
| R2 | `src/` holds at least one skill | error |
| R3 | A loose file sits directly in `src/` | warning |
| R4 | A symlink sits directly in `src/` | warning |

## Contributing

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `chore:`). Once releases are wired up, these prefixes decide each skill's next version, so pick them with care: `feat` for new behaviour, `fix` for corrected behaviour.

Run `uv run ruff check`, `uv run pytest` and `uv run skill-hub qa` before opening a pull request. CI runs all three. To lint on every commit, install the hook once with `uv run pre-commit install`.

## Roadmap

1. **Semantic releases:** Release Please in manifest mode, one component per skill, bumping `metadata.version` and writing changelogs.
2. **Catalog and marketplace page:** build a catalog from `src/` and a static page from it; the deploy step is swappable so you can use Cloudflare Pages, Netlify, an S3 bucket or your own server.
3. **Client install paths:** documented install for Claude Code, Cursor and GitHub Copilot, possibly an [Open Plugins](https://open-plugins.com) `marketplace.json` as well.
4. **Skill scaffolding:** `skill-hub new-skill`.

## Prior art

skill-hub borrows ideas from these projects, without sharing code:

- [googleapis/release-please](https://github.com/googleapis/release-please): conventional-commit releases, the planned versioning engine.
- [ai-plugin-marketplace/tools](https://github.com/ai-plugin-marketplace/tools): a TypeScript toolkit that builds plugin marketplaces for several AI clients. skill-hub stays independent of it, to keep a single config file, a skill-as-folder model, Copilot support and a Python-only toolchain, and borrows its default-name warning and strict name rule.
- [dukelyuu/skills-marketplace](https://github.com/dukelyuu/skills-marketplace): a full-stack skill marketplace app; a reference for what a catalog page should show.
- [WesleySmits/agent-skills](https://github.com/WesleySmits/agent-skills): a skills library with per-client pointer files; a reference for cross-client install patterns.
