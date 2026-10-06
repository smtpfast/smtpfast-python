"""Read-only calls against the real API, each answer checked against the
response schema the spec documents. Runs only with SMTPFAST_API_KEY set;
a key with email:read and domain:read is enough."""
import json
import os
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

import smtpfast

KEY = os.environ.get("SMTPFAST_API_KEY")
SPEC = json.loads((Path(__file__).parent.parent / "spec/openapi.json").read_text())
pytestmark = pytest.mark.skipif(not KEY, reason="SMTPFAST_API_KEY is not set")


def check(operation_id, body):
    for item in SPEC["paths"].values():
        for op in item.values():
            if isinstance(op, dict) and op.get("operationId") == operation_id:
                res = next(v for k, v in op["responses"].items() if k.startswith("2"))
                schema = {**res["content"]["application/json"]["schema"], "components": SPEC["components"]}
                errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(body), key=str)
                assert not errors, f"{operation_id}: " + "; ".join(f"{list(e.absolute_path)}: {e.message}" for e in errors[:5])
                return
    raise AssertionError(f"no operation {operation_id}")


@pytest.fixture(scope="module")
def client():
    with smtpfast.SMTPfast(KEY) as c:
        yield c


def test_account_me(client):
    check("getCapabilities", client.account.me())


def test_emails(client):
    page = client.emails.list(limit=3)
    check("listEmails", page)
    if page["data"]:
        check("getEmail", client.emails.get(page["data"][0]["id"]))


def test_domains(client):
    domains = client.domains.list()
    check("listDomains", domains)
    if domains:
        check("getDomain", client.domains.get(domains[0]["id"]))


@pytest.mark.parametrize(
    "operation_id,call",
    [
        ("listLogs", lambda c: c.logs.list(limit=3)),
        ("getEmailMetrics", lambda c: c.emails.get_metrics()),
        ("listClickedLinks", lambda c: c.emails.list_clicked_links()),
        ("listReceivedEmails", lambda c: c.emails.receiving.list(limit=3)),
        ("getUsage", lambda c: c.account.usage()),
        ("getAnalytics", lambda c: c.analytics.get()),
    ],
)
def test_optional(client, operation_id, call):
    try:
        body = call(client)
    except smtpfast.PermissionDeniedError:
        pytest.skip(f"{operation_id}: this key lacks the scope")
    check(operation_id, body)
