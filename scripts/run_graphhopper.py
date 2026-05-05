from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("graphhopper/config.yml")
DEFAULT_RUNTIME_DIR = Path("graphhopper/runtime")
GRAPHHOPPER_JAR_GLOB = "graphhopper-web-*.jar"


def resolve_jar_path(runtime_dir: Path) -> Path:
    jars = sorted(runtime_dir.glob(GRAPHHOPPER_JAR_GLOB))
    if not jars:
        raise FileNotFoundError(
            f"No GraphHopper jar found in {runtime_dir}. Run scripts/setup_graphhopper.py first."
        )
    return jars[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the self-hosted GraphHopper server for CyclePass.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--command", default="server", choices=["server", "import"])
    parser.add_argument("--java-bin", default="java")
    parser.add_argument("--xms", default="1g")
    parser.add_argument("--xmx", default="2g")
    args = parser.parse_args()

    runtime_dir = Path(args.runtime_dir)
    jar_path = resolve_jar_path(runtime_dir)
    command = [
        args.java_bin,
        f"-Xms{args.xms}",
        f"-Xmx{args.xmx}",
        "-jar",
        str(jar_path),
        args.command,
        args.config,
    ]
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
