import argparse
import json
import logging
import sys

from pydantic import ValidationError

from joseph_pilot.runtime import bootstrap, progress, progress_enabled


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="joseph-pilot")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("runtime-check")
    check.add_argument("--json", action="store_true")
    check.add_argument("--controlled", action="store_true")
    args = parser.parse_args(argv)
    logger = logging.getLogger("joseph_pilot")
    logger.handlers.clear()
    logger.addHandler(logging.StreamHandler(sys.stderr))
    logger.propagate = False
    logger.setLevel(logging.WARNING)
    try:
        _, config, progress_value = bootstrap(controlled=args.controlled)
        with progress(progress_enabled(progress_value)):
            result = {"status": "ok", "config": config}
        print(json.dumps(result) if args.json else "Runtime check: ok")
        return 0
    except ValidationError:
        logger.error("configuration validation failed")
        return 1
    except ValueError as error:
        safe_reasons = {
            "Unsafe shared file",
            "Missing required shared file",
            "Secure shared file access unavailable",
            "Shared file path must be absolute",
            "Cannot safely read shared file",
            "Malformed dotenv line",
            "Malformed or duplicate dotenv key",
            "Invalid dotenv escape",
            "Unterminated dotenv value",
            "Invalid dotenv trailing text",
        }
        reason = str(error)
        logger.error(
            "configuration error: %s", reason if reason in safe_reasons else "invalid configuration"
        )
        return 1
    except (Exception, KeyboardInterrupt):  # noqa: BLE001
        logger.error("runtime check failed")
        return 1
