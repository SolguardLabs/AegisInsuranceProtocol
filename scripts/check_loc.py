from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
MINIMUM_NON_EMPTY_LINES = 3_000


def main() -> None:
    files = sorted((*SOURCE.rglob("*.py"), *SOURCE.rglob("*.vy")))
    physical = 0
    non_empty = 0
    for path in files:
        lines = path.read_text(encoding="utf-8").splitlines()
        physical += len(lines)
        non_empty += sum(1 for line in lines if line.strip())

    print(f"src_files={len(files)} physical_loc={physical} non_empty_loc={non_empty}")
    if non_empty < MINIMUM_NON_EMPTY_LINES:
        raise SystemExit(
            f"source must contain at least {MINIMUM_NON_EMPTY_LINES} non-empty lines"
        )


if __name__ == "__main__":
    main()
