"""
Startup self-check: validate critical dependencies before the server starts
accepting traffic. All checks are synchronous — no database I/O happens here.
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def run_startup_checks(scenarios_dir: Path, app_name: str = "") -> None:
    """
    Validate that required resources exist and are readable.

    Raises RuntimeError with a human-readable message if any check fails
    so that the process exits immediately with a clear log entry rather than
    silently serving broken responses.

    Invalid scenario files are logged as warnings and skipped (matching the
    existing behaviour of _load_scenario_by_id), but if NO valid scenario
    can be found the check fails hard.
    """
    extra = {"app": app_name, "event": "startup_self_check"}

    # 1. Scenarios directory must exist.
    if not scenarios_dir.exists():
        raise RuntimeError(
            f"SCENARIOS_DIR does not exist: {scenarios_dir}. "
            "Set the SCENARIOS_DIR environment variable to the correct path."
        )

    # 2. At least one .json file must be present.
    all_files = sorted(scenarios_dir.glob("*.json"))
    if not all_files:
        raise RuntimeError(
            f"SCENARIOS_DIR contains no .json scenario files: {scenarios_dir}. "
            "Ensure scenario files are copied to the container or volume."
        )

    # 3. Attempt to parse each file; log warnings for invalid ones.
    valid_count = 0
    for path in all_files:
        try:
            content = path.read_text(encoding="utf-8-sig")
            if not content.strip():
                logger.warning(
                    f"Scenario file is empty and will be ignored: {path.name}",
                    extra=extra,
                )
                continue
            json.loads(content)
            valid_count += 1
        except Exception as exc:
            logger.warning(
                f"Scenario file is invalid and will be ignored: {path.name} — {exc}",
                extra=extra,
            )

    # 4. Fail if no file survived the parse step.
    if valid_count == 0:
        raise RuntimeError(
            f"No valid scenario files found in {scenarios_dir}. "
            "All .json files are either empty or contain invalid JSON."
        )

    logger.info(
        f"Startup self-check passed: {valid_count} valid scenario(s) in {scenarios_dir}",
        extra=extra,
    )
