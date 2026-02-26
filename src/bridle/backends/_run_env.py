from __future__ import annotations

import os


def _detect_run_env() -> dict:
    """Detect CI environment from env vars."""
    env = os.environ

    if env.get("BUILDKITE_BUILD_ID"):
        return {
            "CI": "buildkite",
            "key": env.get("BUILDKITE_BUILD_ID", ""),
            "number": env.get("BUILDKITE_BUILD_NUMBER", ""),
            "job_id": env.get("BUILDKITE_JOB_ID", ""),
            "branch": env.get("BUILDKITE_BRANCH", ""),
            "commit": env.get("BUILDKITE_COMMIT", ""),
            "message": env.get("BUILDKITE_MESSAGE", ""),
            "url": env.get("BUILDKITE_BUILD_URL", ""),
        }

    if env.get("GITHUB_ACTION"):
        return {
            "CI": "github_actions",
            "key": f"{env.get('GITHUB_RUN_ID', '')}-{env.get('GITHUB_RUN_ATTEMPT', '1')}",
            "number": env.get("GITHUB_RUN_NUMBER", ""),
            "branch": env.get("GITHUB_REF", ""),
            "commit": env.get("GITHUB_SHA", ""),
            "url": f"{env.get('GITHUB_SERVER_URL', '')}/{env.get('GITHUB_REPOSITORY', '')}/actions/runs/{env.get('GITHUB_RUN_ID', '')}",
        }

    if env.get("CIRCLE_BUILD_NUM"):
        return {
            "CI": "circleci",
            "key": env.get("CIRCLE_WORKFLOW_ID", ""),
            "number": env.get("CIRCLE_BUILD_NUM", ""),
            "branch": env.get("CIRCLE_BRANCH", ""),
            "commit": env.get("CIRCLE_SHA1", ""),
            "url": env.get("CIRCLE_BUILD_URL", ""),
        }

    return {
        "CI": "generic",
        "key": env.get("CI_BUILD_ID", ""),
    }
