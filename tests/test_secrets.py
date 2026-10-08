import pytest

from skill_hub.secrets import scan_text

AWS = "AKIA" + "Q" * 16
AWS_TEMP = "ASIA" + "Q" * 16
GH = "ghp" + "_" + "a" * 36
GH_PAT = "github" + "_pat_" + "a" * 22
SLACK = "xox" + "b-" + "1234567890ab"
SK = "sk" + "-" + "a1" * 12
GOOGLE = "AIza" + "b" * 35
PEM = "-----BEGIN " + "PRIVATE KEY-----"
PEM_ENC = "-----BEGIN " + "ENCRYPTED PRIVATE KEY-----"
PEM_RSA = "-----BEGIN " + "RSA PRIVATE KEY-----"
LIVE = "s3cr3t" + "Value99"  # 13 chars, letters + digits, no spaces


def kinds(text):
    return [hit.kind for hit in scan_text(text)]


@pytest.mark.parametrize(
    ("token", "kind"),
    [
        (AWS, "AWS access key"),
        (AWS_TEMP, "AWS access key"),
        (GH, "GitHub token"),
        (GH_PAT, "GitHub token"),
        (SLACK, "Slack token"),
        (SK, "sk- API key"),
        (GOOGLE, "Google API key"),
        (PEM, "private key"),
        (PEM_ENC, "private key"),
        (PEM_RSA, "private key"),
    ],
)
def test_known_token_shapes(token, kind):
    assert kinds(f"Use this: {token} here") == [kind]


def test_sk_inside_a_word_is_not_a_key():
    assert kinds("See the risk-assessment-framework-for-teams guide.") == []


@pytest.mark.parametrize(
    "line",
    [
        f'password = "{LIVE}"',
        f"password = '{LIVE}'",
        f'"client_secret": "{LIVE}"',
        f"access_token: {LIVE}xyz12",  # unquoted YAML, >= 16 chars
        f"API_KEY={LIVE}xyz12",  # .env
        f'db-password: "{LIVE}"',
        f'apiKey = "{LIVE}"',
        'client_secret: "exampleCompany2026!"',
        'client_secret: "changemeButActuallyLive42"',
    ],
)
def test_credential_assignments(line):
    assert kinds(line) == ["credential assignment"]


@pytest.mark.parametrize(
    "line",
    [
        'max_tokens: "1000"',
        'tokenizer: "cl100k_base"',
        'token_limit: "4096abcd"',
        'password_hint: "first pet"',
        'password: "Ask the user to sign in"',
        'api_key = "<your api key>"',
        'api_key = "<YOUR_API_KEY>"',
        'token: "${GITHUB_TOKEN}"',
        'token: "{{ secrets.TOKEN }}"',
        'token: "{{secrets.TOKEN}}"',
        'password: "your-password-here"',
        'secret: "xxxxxxxxxxxx"',
        'secret: "************"',
        'password: "changeme"',
        'api_key: "EXAMPLE"',
        'password: "redacted"',
        "password = os.environ['DB_PASSWORD']",
        "token = generate_token_v2()",
        "api_key: short123",  # unquoted, under 16 chars
        "secret: onlylettersnodigitsatall",  # unquoted, no digit
        'password: "short"',  # quoted, under 8 chars
    ],
)
def test_not_credentials(line):
    assert kinds(line) == []


def test_known_token_fires_even_inside_placeholder_looking_assignment():
    assert kinds(f'api_key: "{AWS}"  # example') == ["AWS access key"]


def test_allow_marker_skips_line():
    assert kinds(f'password = "{LIVE}"  # skill-hub: allow-secret') == []


def test_reports_line_numbers():
    hits = scan_text(f"ok\n\npassword = '{LIVE}'\n")
    assert [(hit.line, hit.kind) for hit in hits] == [(3, "credential assignment")]
