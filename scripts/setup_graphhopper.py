from __future__ import annotations

import argparse
import shutil
import urllib.parse
import urllib.request
from pathlib import Path

GRAPHHOPPER_VERSION = "11.0"
DEFAULT_PBF_URL = "https://download.geofabrik.de/europe/poland/wielkopolskie-latest.osm.pbf"
MAVEN_CENTRAL_BASE_URL = "https://repo1.maven.org/maven2/com/graphhopper/graphhopper-web"
DOWNLOAD_CHUNK_SIZE = 1024 * 1024


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as response, destination.open("wb") as output_file:
        while True:
            chunk = response.read(DOWNLOAD_CHUNK_SIZE)
            if not chunk:
                break
            output_file.write(chunk)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download GraphHopper and a regional OSM extract for CyclePass.")
    parser.add_argument("--graphhopper-version", default=GRAPHHOPPER_VERSION)
    parser.add_argument("--pbf-url", default=DEFAULT_PBF_URL)
    parser.add_argument("--runtime-dir", default="graphhopper/runtime")
    args = parser.parse_args()

    runtime_dir = Path(args.runtime_dir)
    runtime_dir.mkdir(parents=True, exist_ok=True)

    jar_name = f"graphhopper-web-{args.graphhopper_version}.jar"
    jar_path = runtime_dir / jar_name
    jar_url = f"{MAVEN_CENTRAL_BASE_URL}/{args.graphhopper_version}/{jar_name}"
    if not jar_path.exists():
        print(f"Downloading {jar_url} -> {jar_path}")
        download_file(jar_url, jar_path)
    else:
        print(f"Reusing existing {jar_path}")

    pbf_name = Path(urllib.parse.urlparse(args.pbf_url).path).name
    pbf_path = runtime_dir / pbf_name
    if not pbf_path.exists():
        print(f"Downloading {args.pbf_url} -> {pbf_path}")
        download_file(args.pbf_url, pbf_path)
    else:
        print(f"Reusing existing {pbf_path}")

    expected_config_target = runtime_dir / "wielkopolskie-latest.osm.pbf"
    if pbf_path != expected_config_target:
        shutil.copyfile(pbf_path, expected_config_target)
        print(f"Copied {pbf_path.name} to {expected_config_target.name} for config compatibility")

    print("GraphHopper runtime assets are ready.")


if __name__ == "__main__":
    main()
