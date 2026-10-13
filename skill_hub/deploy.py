"""Check hub.yml's deploy block (checks H12-H16) and render it for the deploy workflows."""

from dataclasses import dataclass
from pathlib import Path

from skill_hub.contract import (
    DEFAULT_RSYNC_PORT,
    DEPLOY_SETTING_RULES,
    DEPLOY_TARGET_SETTINGS,
    HUB_FILE,
    REQUIRED_DEPLOY_SETTINGS,
    is_blank,
    is_valid_name,
    type_name,
)
from skill_hub.findings import ERROR, WARNING, Finding

SETTINGS_BLOCKS = tuple(target for target, keys in DEPLOY_TARGET_SETTINGS.items() if keys)
DEPLOY_KEYS = ("target", *SETTINGS_BLOCKS)


@dataclass(frozen=True)
class DeploySettings:
    target: str = ""
    outputs: tuple[tuple[str, str], ...] = ()  # the selected target's filled-in settings, as (output name, value)


def deploy_workflow(target: str) -> Path:
    return Path(".github") / "workflows" / f"deploy-{target}.yml"


def _error(check_id: str, message: str) -> Finding:
    return Finding(ERROR, check_id, HUB_FILE, message)


def _warning(check_id: str, message: str) -> Finding:
    return Finding(WARNING, check_id, HUB_FILE, message)


def _either(keys: tuple[str, ...]) -> str:
    return ", ".join(keys[:-1]) + " or " + keys[-1]


def _check_target(deploy: dict) -> tuple[list[Finding], str]:
    """H12: `target` is "" or a kebab-case name. Returns "" when it is not."""
    target = deploy.get("target", "")
    if not isinstance(target, str):
        return [_error("H12", f"deploy.target must be a string, found {type_name(target)}; quote it")], ""
    if target and not is_valid_name(target):
        message = "deploy.target must be empty or 1-64 characters of a-z, 0-9 and single hyphens"
        return [_error("H12", message)], ""
    return [], target


def _check_block(deploy: dict, block: str) -> tuple[list[Finding], dict]:
    """H13: a settings block's types. Returns its findings and its well-typed values."""
    settings = deploy.get(block)
    if settings is None:
        return [], {}
    if not isinstance(settings, dict):
        return [_error("H13", f"deploy.{block} must be a mapping, found {type_name(settings)}")], {}

    keys = DEPLOY_TARGET_SETTINGS[block]
    findings: list[Finding] = []
    if any(key not in keys for key in settings):
        findings.append(_warning("H13", f"deploy.{block} has an unknown key; expected {_either(keys)}"))
    values: dict = {}
    for key in keys:
        if key not in settings:
            continue
        value = settings[key]
        if key == "port":
            if isinstance(value, int) and not isinstance(value, bool):
                values[key] = value
            else:
                findings.append(_error("H13", f"deploy.{block}.port must be a number, found {type_name(value)}"))
        elif isinstance(value, str):
            values[key] = value
        else:
            message = f"deploy.{block}.{key} must be a string, found {type_name(value)}; quote it"
            findings.append(_error("H13", message))
    return findings, values


def _check_required(deploy: dict, target: str, values: dict) -> list[Finding]:
    """H14: the selected built-in target has its required settings."""
    raw = deploy.get(target)
    if target not in REQUIRED_DEPLOY_SETTINGS or not (raw is None or isinstance(raw, dict)):
        return []  # no required settings, or H13 already reported the block
    findings = []
    for key in REQUIRED_DEPLOY_SETTINGS[target]:
        if raw is not None and key in raw and key not in values:
            continue  # H13 already reported its type
        if is_blank(values.get(key, "")):
            findings.append(_error("H14", f"deploy.target needs deploy.{target}.{key}, which is empty"))
    return findings


def _check_values(blocks: dict[str, dict]) -> list[Finding]:
    """H15: every filled-in setting, selected target or not, passes its value rule."""
    findings = []
    for block, values in blocks.items():
        for key, value in values.items():
            if isinstance(value, str) and is_blank(value):
                continue
            rule, rule_text = DEPLOY_SETTING_RULES[(block, key)]
            if not rule(value):
                findings.append(_error("H15", f"deploy.{block}.{key} {rule_text}"))
    return findings


def _outputs(target: str, values: dict) -> tuple[tuple[str, str], ...]:
    if target == "rsync":
        values = {"port": DEFAULT_RSYNC_PORT, **values}
    return tuple(
        (f"{target}_{key}", str(values[key]))
        for key in DEPLOY_TARGET_SETTINGS.get(target, ())
        if key in values and not is_blank(str(values[key]))
    )


def check_deploy(root: Path, data: dict) -> tuple[list[Finding], DeploySettings]:
    deploy = data.get("deploy")
    if deploy is None:  # absent, or a `deploy:` block with every key commented out
        return [], DeploySettings()
    if not isinstance(deploy, dict):
        return [_error("H12", f"deploy must be a mapping, found {type_name(deploy)}")], DeploySettings()

    findings: list[Finding] = []
    if any(key not in DEPLOY_KEYS for key in deploy):
        findings.append(_warning("H12", f"deploy has an unknown key; expected {_either(DEPLOY_KEYS)}"))
    target_findings, target = _check_target(deploy)
    findings.extend(target_findings)

    blocks: dict[str, dict] = {}
    for block in SETTINGS_BLOCKS:
        block_findings, blocks[block] = _check_block(deploy, block)
        findings.extend(block_findings)

    findings.extend(_check_required(deploy, target, blocks.get(target, {})))
    findings.extend(_check_values(blocks))
    if target and not (root / deploy_workflow(target)).is_file():
        findings.append(_error("H16", "deploy.target has no matching .github/workflows/deploy-<target>.yml"))

    if any(finding.level == ERROR for finding in findings):
        return findings, DeploySettings()
    return findings, DeploySettings(target, _outputs(target, blocks.get(target, {})))


def render_outputs(settings: DeploySettings) -> str:
    """The `name=value` lines `skill-hub deploy-config` writes to $GITHUB_OUTPUT: the target, then its settings."""
    lines = [f"target={settings.target}", *(f"{name}={value}" for name, value in settings.outputs)]
    return "\n".join(lines) + "\n"
