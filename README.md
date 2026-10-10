# skill-hub

A starter kit for standing up your own agent-skill marketplace. Clone it, set your hub name and host, add your skills, and you get QA-gated `SKILL.md` packages, semantic releases, a static marketplace page on the host of your choice, and install paths for Claude Code, Cursor, and GitHub Copilot.

skill-hub is not a marketplace itself. It is the scaffolding for yours: everything that identifies your hub lives in one config file, and the skills are yours.

> **Work in progress.** The skill contract, the QA guard, skill scaffolding, releases and the marketplace page build work today. Deploying the page and client install paths are next; see [Roadmap](#roadmap).

## What you get

| Piece | What it does | Status |
|---|---|---|
| **Skill contract** | Each skill is a folder under `skills/` with a `SKILL.md` that follows the [Agent Skills specification](https://agentskills.io/specification), so it installs in any client that reads the spec | Available |
| **QA guard** | `skill-hub qa` checks your hub config and every skill: valid frontmatter, a name that matches its folder, a SemVer version, Python that compiles, and no committed secrets. It runs locally and on every pull request | Available |
| **Semantic releases** | Conventional commits (`feat:`, `fix:`) drive version bumps and changelogs through [Release Please](https://github.com/googleapis/release-please), one version per skill | Available |
| **Marketplace page** | `skill-hub build` turns your skills into a static, self-contained page and a `catalog.json`, restyled from `hub.yml` or replaced by your own theme. Host it anywhere | Available |
| **Client install paths** | Install a skill from your hub into Claude Code, Cursor or GitHub Copilot by a documented path | Planned |
| **Skill scaffolding** | `skill-hub new-skill <name>` creates a skill that already passes QA | Available |

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
2. **Replace the example skill.** `skills/example-skill/` shows the shape of a skill. Create your own with `uv run skill-hub new-skill <name>`, then delete the example once you have real skills. QA warns (S14) until you replace the new skill's placeholder description.
3. **Run `uv run skill-hub qa` again.** With no warnings left, your hub is ready for skills.

## Layout

```text
hub.yml                    your hub's identity and QA options (yours to edit)
skills/<skill>/SKILL.md    your skills, one folder each (yours)
skills/<skill>/...         optional scripts/, references/, assets/
skill_hub/                 the QA tool (part of the kit)
skill_hub/themes/default/  the built-in marketplace theme (copy it to make your own)
site/                      build output from skill-hub build (git-ignored)
tests/                     the kit's own tests
.github/workflows/qa.yml   runs tests and skill-hub qa on every pull request
.github/workflows/release.yml  opens release PRs and tags skill releases
release-please-config.json     which skills Release Please versions (skill-hub new-skill adds to it)
.release-please-manifest.json  each skill's last released version (Release Please maintains it)
```

You own `hub.yml`, `skills/` and the two release files, which list your skills. Everything else belongs to the kit, which keeps pulling in kit updates simple. New config keys are always optional with a default, so your `hub.yml` keeps working.

## Writing a skill

A skill is a folder whose name matches the `name` in its `SKILL.md`:

```markdown
---
name: changelog-formatter
description: "Formats changelog entries. Use when the user asks to write or tidy a changelog."
metadata:
  version: "0.1.0" # x-release-please-version
---

# Changelog formatter

Instructions for the agent go here.
```

The rules QA enforces:

- **Frontmatter keys:** only the six from the Agent Skills spec: `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`. Strict consumers such as claude.ai uploads reject anything else. If your hub only targets Claude Code, you can allow its extra keys (for example `when_to_use`) in `hub.yml` under `qa.allow_keys`.
- **`name`:** 1 to 64 characters of lowercase letters, digits and single hyphens, matching the folder name.
- **`description`:** up to 1024 characters. Say what the skill does and when to use it, since that is how agents decide to load it.
- **Version:** a quoted SemVer string in `metadata.version`. A top-level `version` key is not part of the spec and fails QA. Keep the `# x-release-please-version` marker on that line: Release Please bumps the version there.
- **Secrets:** every file in a skill, hidden files included, is scanned for known token shapes and credential assignments. For a deliberate example in documentation, put `skill-hub: allow-secret` on that line.

## Releasing a skill

Each skill has its own version, bumped by [Release Please](https://github.com/googleapis/release-please) from your commit messages:

- `fix:` bumps the patch version, `feat:` the minor, and a breaking change (`feat!:` or a `BREAKING CHANGE:` footer) the major. To force a version, add a `Release-As: 1.0.0` footer.
- A commit counts toward a skill when it changes files in that skill's folder.

On every push to `main`, the release workflow opens or updates one release PR. Merging it bumps each changed skill's `metadata.version`, writes its `CHANGELOG.md`, and tags the release `<skill>-v<version>`. A skill's first release is `0.1.0`, whatever its `metadata.version` says. If you bring in a skill that is already at a higher version, add a `Release-As: <that version>` footer to a commit that changes it before its first release; QA warns (S16) until that first release.

Before your first release:

1. **Let Actions open pull requests.** In your repository, go to Settings → Actions → General and turn on "Allow GitHub Actions to create and approve pull requests".
2. **Optional: run QA on release PRs.** A PR opened with GitHub's default token does not trigger other workflows, so QA runs on `main` after the release PR merges, not on the PR. If you require checks before merging, create a fine-grained personal access token (or a GitHub App token) with contents and pull-request write access, and save it as the `RELEASE_PLEASE_TOKEN` Actions secret.

`skill-hub new-skill` registers each new skill in `release-please-config.json`. To opt out of releases, delete `release-please-config.json` and `.release-please-manifest.json`; QA then skips its release checks.

## Marketplace page

`uv run skill-hub build` checks the hub with QA, then writes the marketplace page into `site/`: an `index.html` with a card for every skill and a search box, plus `catalog.json`. Any QA error stops the build; warnings don't. Upload the folder to any static host. CI builds it on every push to `main` and attaches it to the workflow run as the `marketplace-page` artifact. Use `--out PATH` to write elsewhere. The build only replaces a folder it created itself, so it refuses to write into a folder that holds anything else.

Restyle the default page from `hub.yml`:

```yaml
site:
  accent: "#4f46e5"   # hex colour for links and highlights; keep the quotes
  logo_url: "https://example.com/logo.png"   # or a path relative to the page
  theme: ""           # your own theme folder; empty = the built-in default
```

The default page is one file with its styles inlined and no outside requests, so it works offline and on locked-down hosts. It follows the visitor's light or dark setting, and with JavaScript off it shows every card without the search box.

### Catalog format

`catalog.json` is the contract every theme renders from. Version 1:

```json
{
  "schema_version": 1,
  "hub": {"name": "...", "display_name": "...", "owner": "...", "description": "...", "repo_url": "..."},
  "skills": [{
    "name": "...", "description": "...", "version": "1.2.0",
    "license": null, "compatibility": null,
    "links": {"source": "<repo_url>/tree/HEAD/skills/<name>", "changelog": null, "release": null}
  }]
}
```

Skills are sorted by name. `license` and `compatibility` are `null` when the skill doesn't set them. `changelog` links to the skill's `CHANGELOG.md` when it has one, and `release` links to the `<name>-v<version>` release once Release Please has published one. New fields may be added within version 1; a breaking change bumps `schema_version`.

### Custom themes

A theme is a folder with an `index.html.j2` [Jinja2](https://jinja.palletsprojects.com/) template. To make your own, copy `skill_hub/themes/default/` into your hub (for example to `theme/`), set `site.theme: "theme"` in `hub.yml`, and edit it.

- `index.html.j2` renders to `index.html`. Other `*.j2` files are partials it can `{% include %}`; they're not copied.
- Every other file (CSS, images, fonts) is copied as-is, keeping its subfolders. Dot-files are skipped, and symlinks are skipped with a warning.
- The template receives `catalog` (the data in `catalog.json`) and `site` (`accent` and `logo_url` from `hub.yml`).
- Every value is HTML-escaped automatically, so skill text can't inject markup. An undefined variable fails the build with the file and line, instead of rendering blank.
- A theme can't contain its own `index.html` or `catalog.json`, and it must sit inside the hub.

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
| H7 | `site` is a mapping and `accent`, `logo_url` and `theme` are strings (an unknown key under `site` is a warning) | error |
| H8 | `site.accent` is a hex colour such as `"#4f46e5"` | error |
| H9 | `site.logo_url` is an `https://` URL or a relative path | error |
| H10 | `site.theme` is a folder inside the hub root that contains `index.html.j2` | error |
| H11 | `hub.name` is not a marketplace name Claude Code reserves (such as `agent-skills`, `github` or anything starting `claudeai-`) | error |
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
| S15 | `metadata.version` matches the skill's manifest entry, and its `version.txt` if it has one | error |
| S16 | A registered skill that has never been released has a `metadata.version` other than its first-release version (`initial-version`), which the first release would overwrite | warning |
| S17 | The skill's name doesn't pass for one of Anthropic's own plugins (such as a `claude-` or `anthropic-` prefix), which Claude Code refuses | warning |
| R1 | `skills/` exists and can be read | error |
| R2 | `skills/` holds at least one skill | error |
| R3 | A loose file sits directly in `skills/` | warning |
| R4 | A symlink sits directly in `skills/` | warning |
| R5 | `release-please-config.json` lists every skill under `packages`, `.release-please-manifest.json` exists, and both are JSON objects (skipped when the config is absent) | error |
| R6 | No release config or manifest entry names a path under `skills/` that is not a skill | error |
| R7 | `.claude-plugin/marketplace.json` and `.cursor-plugin/marketplace.json` exist and match what `skill-hub manifests` would write (checked only when nothing else failed) | error |

## Contributing

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `chore:`). These prefixes decide each skill's next version, so pick them with care: `feat` for new behaviour, `fix` for corrected behaviour.

Run `uv run ruff check`, `uv run pytest` and `uv run skill-hub qa` before opening a pull request. CI runs all three. To lint on every commit, install the hook once with `uv run pre-commit install`.

## Roadmap

1. **Deploying the marketplace page:** a swappable deploy step for Cloudflare Pages, Netlify, an S3 bucket or your own server.
2. **Client install paths:** documented install for Claude Code, Cursor and GitHub Copilot, possibly an [Open Plugins](https://open-plugins.com) `marketplace.json` as well.

## Prior art

skill-hub borrows ideas from these projects, without sharing code:

- [googleapis/release-please](https://github.com/googleapis/release-please): conventional-commit releases, the versioning engine.
- [ai-plugin-marketplace/tools](https://github.com/ai-plugin-marketplace/tools): a TypeScript toolkit that builds plugin marketplaces for several AI clients. skill-hub stays independent of it, to keep a single config file, a skill-as-folder model, Copilot support and a Python-only toolchain, and borrows its default-name warning and strict name rule.
- [dukelyuu/skills-marketplace](https://github.com/dukelyuu/skills-marketplace): a full-stack skill marketplace app; a reference for what a catalog page should show.
- [WesleySmits/agent-skills](https://github.com/WesleySmits/agent-skills): a skills library with per-client pointer files; a reference for cross-client install patterns.
