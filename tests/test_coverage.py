"""Every operation in the spec is reachable as client.<group>.<method>() and
sends the method and path the spec documents."""
import json
import re
from pathlib import Path

import pytest
from conftest import make

SPEC = json.loads((Path(__file__).parent.parent / "spec/openapi.json").read_text())
OPS = [
    (path, method, op)
    for path, item in SPEC["paths"].items()
    for method, op in item.items()
    if method in ("get", "post", "put", "patch", "delete")
]


def snake(s):
    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", s).lower()


@pytest.mark.parametrize("path,method,op", OPS, ids=[".".join(o["x-sdk-group"] + [o["x-sdk-method"]]) for _, _, o in OPS])
def test_operation(path, method, op):
    client, rec = make()
    target = client
    for g in op["x-sdk-group"]:
        target = getattr(target, snake(g))
    fn = getattr(target, snake(op["x-sdk-method"]))
    names = re.findall(r"\{(\w+)\}", path)
    args = [f"p{i}" for i in range(len(names))]
    if op.get("requestBody"):
        args.append({})
    kwargs = {snake(q["name"]): "x" for q in op.get("parameters", []) if q["in"] == "query" and q.get("required")}
    fn(*args, **kwargs)
    assert rec.calls[0].method == method.upper()
    expected = path
    for i, n in enumerate(names):
        expected = expected.replace("{" + n + "}", f"p{i}")
    assert rec.calls[0].url.path == "/api" + expected
