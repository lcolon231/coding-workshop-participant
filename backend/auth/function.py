"""AWS Lambda entrypoint for the auth service.

Commit 1: a throwaway smoke test. It exists to prove four things before nine
commits of work depend on them:

1. the Terraform zip builds and uploads;
2. the vendored `acme_core` import resolves at /var/task;
3. CloudFront's `/api/auth*` behavior actually routes to this function;
4. what a trivial python3.13 function costs, as a memory baseline against the
   hardcoded 128 MB in infra/lambda.tf:11.

`infra/locals.tf:57` hardcodes the handler as `function.handler`, so both the
module name and the function name are load-bearing. Replaced at commit 10 by
the real dispatcher plus a lazily-constructed Mangum adapter.
"""

from __future__ import annotations

import json
import os
from typing import Any

import acme_core


def _response(status: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Build a Lambda Function URL response.

    Args:
        status: HTTP status code.
        payload: JSON-serialisable body.

    Returns:
        A response dict in the shape the Function URL runtime expects, with the
        body as a JSON *string*.
    """
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }


def handler(event: dict[str, Any] | None = None, context: Any = None) -> dict[str, Any]:
    """Report liveness and deployment provenance.

    Defaults on both parameters let this run as `python function.py`, matching
    the convention in backend/_examples/python-service/function.py.

    Args:
        event: Lambda Function URL event, or None when run directly.
        context: Lambda context object, or None when run directly.

    Returns:
        A 200 response describing the running build.
    """
    path = ""
    if isinstance(event, dict):
        path = event.get("rawPath") or ""

    return _response(
        200,
        {
            "service": "auth",
            "status": "ok",
            "stage": "commit-1-smoke-test",
            # Proves the vendored copy imported, and says which one.
            "acme_core_version": acme_core.__version__,
            "build": acme_core.build_stamp(),
            # Confirms CloudFront forwards the full path without stripping the
            # /api/auth prefix (infra/cloudfront.tf sets no origin_path).
            "seen_path": path,
            "in_lambda": "AWS_LAMBDA_FUNCTION_NAME" in os.environ,
            "memory_limit_mb": os.getenv("AWS_LAMBDA_FUNCTION_MEMORY_SIZE"),
        },
    )


if __name__ == "__main__":
    print(json.dumps(handler(), indent=2))  # noqa: T201
