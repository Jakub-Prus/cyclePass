from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.scoring import classify_way

EXAMPLE_SEGMENTS = [
    {"highway": "cycleway", "cycleway": "track", "bicycle": "designated"},
    {"highway": "residential", "maxspeed": "30", "sidewalk": "both"},
    {"highway": "trunk", "maxspeed": "80", "bicycle": "no"},
]


def main() -> None:
    for index, tags in enumerate(EXAMPLE_SEGMENTS, start=1):
        result = classify_way(tags)
        print(f"Segment {index}: {result['bike_crossable_label']} ({result['bike_comfort']}/100)")
        for reason in result["reasons"]:
            print(f"  - {reason}")


if __name__ == "__main__":
    main()
