#!/usr/bin/env python3
"""Build the publishable files using the tracked scientific inputs."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "roseires-pipeline" / "outputs" / "pilot"


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    cli.add_argument("--revision", default=os.environ.get("GITHUB_SHA") or os.environ.get("CF_PAGES_COMMIT_SHA"))
    args = cli.parse_args()

    if args.revision and not re.fullmatch("[a-f0-9]{40}", args.revision):
        cli.error("--revision must be a full Git commit SHA")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(path.name not in {"index.html", "version.json"} or not path.is_file() or path.is_symlink()
           for path in output.iterdir()):
        cli.error("Choose an output directory containing only generated site files.")

    subprocess.run(
        [sys.executable, str(ROOT / "roseires-visuals" / "build_infrasar.py"),
         "--pilot", str(PILOT / "comparator.html"),
         "--patch", str(PILOT / "inlet_patch_mask.tif"),
         "--output", str(output / "index.html")],
        check=True,
    )
    (output / "version.json").write_text(json.dumps({"commit": args.revision}) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
