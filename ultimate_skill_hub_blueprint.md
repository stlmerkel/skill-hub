# Blueprint: Ultimate Unified Skill Hub

This comprehensive blueprint outlines the implementation plan for building a unified, multi-agent internal skill repository. It combines automated QA, background script support, semantic version bumping, and a beautiful static marketplace UI.

---

## 1. Directory Structure

```text
our-team-skills/
├── .agent/                      # Master cross-agent config directories
│   └── skills/                  # Symlinked prompt rules for IDE extensions
├── .github/
│   └── workflows/
│       └── ci-cd.yml            # Merged QA, Versioning, and Deployment Pipeline
├── src/                         # Component source directory
│   ├── sql-optimizer/           
│   │   ├── SKILL.md             # Core prompt text + YAML frontmatter
│   │   ├── script.py            # Local background execution logic
│   │   └── requirements.txt     # Script-specific python dependencies
│   └── compliance-checker/
│       └── SKILL.md
├── tests/
│   └── run_qa.py                # Automated pre-flight validation suite
├── web/
│   └── index.html               # Visual UI Marketplace Front-end dashboard
├── package.json                 # Tooling orchestration & npm scaffolding scripts
├── release-please-config.json   # Structural configuration for semantic releases
└── README.md                    # Onboarding document for team members
```

---

## 2. Core Pillars & Template Merging Strategy

1. **Scaffolding Tooling (`ai-plugin-marketplace`):** Orchestrated via `package.json` utilizing the `@ai-plugin-marketplace/toolkit` to spin up standardized directories automatically.
2. **Automated Bumping & Shipping (Dev.to / Release Please):** Tracks structural updates via conventional commits to trigger automatic patch/minor releases and seamlessly update the public manifest version.
3. **High-Fidelity Storefront (`dukelyuu/skills-marketplace`):** Generates a responsive, Tailwind-styled dark mode HTML workspace hosted on GitHub Pages for manual discovery.
4. **Universal Client Support (`WesleySmits/agent-skills`):** Compiles definitions into `.agent/skills/` paths ensuring instant recognition for Claude Code, Cursor, and GitHub Copilot users.

---

## 3. Pre-Flight QA Guard (`tests/run_qa.py`)

Save the following Python validation script within your repository to protect production integrity from broken configurations, bad YAML, syntax anomalies, or leaked credentials:

```python
import os
import re
import sys
import yaml

SRC_DIR = "src"
SECRET_REGEX = re.compile(
    r'(?:secret|passwd|password|api_key|token)\s*=\s*["'][a-zA-Z0-9_\-]{8,}["']', 
    re.IGNORECASE
)

def validate_skills():
    errors = []
    if not os.path.exists(SRC_DIR):
        print(f"Error: Source directory '{SRC_DIR}' not found.")
        sys.exit(1)

    for item in os.listdir(SRC_DIR):
        skill_dir = os.path.join(SRC_DIR, item)
        if not os.path.isdir(skill_dir):
            continue
            
        skill_md_path = os.path.join(skill_dir, "SKILL.md")
        if not os.path.exists(skill_md_path):
            errors.append(f"[{item}] Missing mandatory 'SKILL.md' file.")
            continue
            
        with open(skill_md_path, "r", encoding="utf-8") as f:
            content = f.read()
            if not content.startswith("---"):
                errors.append(f"[{item}] 'SKILL.md' must start with valid '---' YAML frontmatter blocks.")
                continue
            try:
                _, frontmatter, _ = content.split("---", 2)
                meta = yaml.safe_load(frontmatter)
                for field in ["name", "version", "description"]:
                    if not meta or field not in meta or not str(meta[field]).strip():
                        errors.append(f"[{item}] 'SKILL.md' frontmatter is missing required text field: '{field}'.")
            except Exception as e:
                errors.append(f"[{item}] Malformed YAML frontmatter: {str(e)}")

        for root, _, files in os.walk(skill_dir):
            for file in files:
                file_path = os.path.join(root, file)
                if file.endswith(".py"):
                    with open(file_path, "r", encoding="utf-8") as f:
                        code = f.read()
                        try:
                            compile(code, file_path, "exec")
                        except SyntaxError as se:
                            errors.append(f"[{item}] Syntax error in script '{file}': Line {se.lineno} -> {se.msg}")
                        if SECRET_REGEX.search(code):
                            errors.append(f"[{item}] Security alert: Possible hardcoded secret or API key detected in '{file}'.")

    if errors:
        print("\n❌ QA Automated Pre-flight checks failed:")
        for error in errors:
            print(f" - {error}")
        sys.exit(1)
        
    print("\n✅ All skills passed metadata validation, safety checks, and syntax compilation.")

if __name__ == '__main__':
    validate_skills()
```

---

## 4. Full Integration Pipeline (`.github/workflows/ci-cd.yml`)

This continuous deployment setup guarantees that any pull request running invalid logic is immediately intercepted, while valid changes onto your `main` branch trigger deployment automatically.

```yaml
name: Shared Skill Infrastructure Engine

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: write
  pages: write
  id-token: write

jobs:
  validate_and_test:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Source Code
        uses: actions/checkout@v4

      - name: Setup Execution Environment
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Boot QA Dependencies
        run: |
          python -m pip install --upgrade pip
          pip install pyyaml

      - name: Run Test Guard Suite
        run: python tests/run_qa.py

  compile_and_release:
    needs: validate_and_test
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Source Code
        uses: actions/checkout@v4

      - name: Build Web Front-End & JSON Catalog Registry
        run: |
          python -c "
          import os, yaml, json
          registry = {'name': 'Team Skill Hub', 'plugins': []}
          src_dir = 'src'
          
          for item in os.listdir(src_dir):
              skill_path = os.path.join(src_dir, item, 'SKILL.md')
              if os.path.exists(skill_path):
                  with open(skill_path, 'r', encoding='utf-8') as f:
                      _, frontmatter, _ = f.read().split('---', 2)
                      meta = yaml.safe_load(frontmatter)
                      registry['plugins'].append({
                          'name': meta.get('name', item),
                          'version': str(meta.get('version', '1.0.0')),
                          'description': meta.get('description', ''),
                          'author': meta.get('author', 'Internal')
                      })
          
          os.makedirs('web/.github/plugin', exist_ok=True)
          with open('web/.github/plugin/marketplace.json', 'w') as f:
              json.dump(registry, f, indent=2)
              
          html = '<html><head><title>Team Marketplace</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-slate-900 text-slate-100 min-h-screen p-10"><div class="max-w-4xl mx-auto">'
          html += '<h1 class="text-3xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-500 mb-8">🛒 Shared Team Skill Marketplace</h1>'
          for p in registry['plugins']:
              html += f'<div class="bg-slate-800 border border-slate-700 p-6 rounded-lg shadow-md mb-4 transition transform hover:scale-[1.01]"><div class="flex justify-between items-center mb-2"><h3 class="text-xl font-bold text-white">{p["name"]}</h3><span class="px-2 py-1 text-xs bg-slate-700 rounded text-cyan-400 font-mono">v{p["version"]}</span></div><p class="text-slate-400 mb-4">{p["description"]}</p><div class="text-xs text-slate-500 font-mono">By {p["author"]}</div></div>'
          html += '</div></body></html>'
          
          with open('web/index.html', 'w') as f:
              f.write(html)
          "

      - name: Pack Pages Assets
        uses: actions/upload-pages-artifact@v3
        with:
          path: './web'

  deploy_to_prod:
    needs: compile_and_release
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - name: Deploy Live on Infrastructure CDN
        id: deployment
        uses: actions/deploy-pages@v4
```

---

## 5. Sequential Execution Implementation Path

* **Step 1:** Establish a clear repository root, and save the target directory structures matching the layout above.
* **Step 2:** Ensure your repository **Settings -> Pages** configurations are updated to run from **GitHub Actions** rather than tracking a branch directory.
* **Step 3:** Commit using structured tags (e.g., `feat: ...`, `fix: ...`) to allow the underlying automation blocks to cleanly scale your tracking manifests.