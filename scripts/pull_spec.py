"""Download the published OpenAPI document into spec/openapi.json."""
import json
import os
import urllib.request
from pathlib import Path

url = os.environ.get("SMTPFAST_SPEC_URL", "https://smtpfa.st/api/v1/openapi.json")
with urllib.request.urlopen(url, timeout=30) as res:
    spec = json.load(res)
out = Path(__file__).resolve().parent.parent / "spec/openapi.json"
out.write_text(json.dumps(spec, indent=2) + "\n")
print(f"spec/openapi.json: {len(spec['paths'])} paths from {url}")
