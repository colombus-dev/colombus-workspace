#!/usr/bin/env -S uv run python
import argparse
import csv
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
COLOMBUS_DIR = ROOT / "submodules" / "colombus"
FLINK_DIR = ROOT / "submodules" / "colombus-flink"
BENCHMARKS_DIR = ROOT / "data" / "benchmarks"

TOKEN_DELIMITER = "\x1f"


def flat_steps(terms: list[str]) -> list[str]:
    return ["--steps", *terms]


def flat_pattern_define(terms: list[str]) -> tuple[str, str]:
    var_names = [f"A{i}" for i in range(len(terms))]
    pattern = " ".join(var_names)
    define = ",".join(f"{v}={t}" for v, t in zip(var_names, terms))
    return pattern, define


LONG_CHAIN_TERMS = [
    "Data Collection", "Data Preparation", "Data Preparation", "Data Modeling",
    "Model Evaluation", "Data Preparation", "Data Modeling", "Model Evaluation",
    "Data Modeling", "Model Evaluation", "Model Deployment", "Save Results",
]

CASES = [
    {
        "name": "short_adjacent",
        "colombus_args": flat_steps(["Data Modeling", "Model Deployment"]),
        "flink_pattern_define": flat_pattern_define(["Data Modeling", "Model Deployment"]),
    },
    {
        "name": "gap",
        "colombus_args": [
            "--regex",
            f"{TOKEN_DELIMITER}Data Modeling(?={TOKEN_DELIMITER}).*"
            f"{TOKEN_DELIMITER}Model Deployment(?={TOKEN_DELIMITER})",
        ],
        "flink_pattern_define": ("A X*? B", "A=Data Modeling,X=*,B=Model Deployment"),
    },
    {
        "name": "quantifier",
        "colombus_args": [
            "--regex",
            f"({TOKEN_DELIMITER}Data Preparation){{2,3}}{TOKEN_DELIMITER}Data Modeling"
            f"(?={TOKEN_DELIMITER})",
        ],
        "flink_pattern_define": ("A{2,3} B", "A=Data Preparation,B=Data Modeling"),
    },
    {
        "name": "long_chain",
        "colombus_args": flat_steps(LONG_CHAIN_TERMS),
        "flink_pattern_define": flat_pattern_define(LONG_CHAIN_TERMS),
    },
    {
        "name": "no_match",
        "colombus_args": flat_steps(["Save Results"] * 6),
        "flink_pattern_define": flat_pattern_define(["Save Results"] * 6),
    },
]


def run(cmd: list[str], cwd: pathlib.Path, capture: bool = False) -> str:
    result = subprocess.run(
        cmd, cwd=cwd, check=True, capture_output=capture, text=True
    )
    return result.stdout if capture else ""


def regenerate_notebooks(num_notebooks: int) -> None:
    run(
        [sys.executable, str(ROOT / "scripts" / "generate_notebooks.py"),
         "--num-notebooks", str(num_notebooks), "--reset"],
        cwd=ROOT,
    )


def seed_colombus() -> None:
    run(["uv", "run", "python", "scripts/benchmark/seed.py", "--reset"], cwd=COLOMBUS_DIR)


def query_colombus(case: dict, repeat: int) -> dict:
    out = run(
        ["uv", "run", "python", "scripts/benchmark/query.py",
         *case["colombus_args"], "--repeat", str(repeat)],
        cwd=COLOMBUS_DIR, capture=True,
    )
    return json.loads(out)


def seed_flink() -> None:
    run(["docker", "compose", "exec", "-T", "pyflink", "python", "seed.py", "--truncate"],
        cwd=FLINK_DIR)


def query_flink(case: dict, repeat: int) -> dict:
    pattern, define = case["flink_pattern_define"]
    out = run(
        ["docker", "compose", "exec", "-T", "pyflink", "python", "query.py",
         "--pattern", pattern, "--define", define,
         "--repeat", str(repeat), "--quiet"],
        cwd=FLINK_DIR, capture=True,
    )
    return json.loads(out)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", default="100,500,1000,5000")
    parser.add_argument("--repeat", type=int, default=10)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    sizes = [int(s) for s in args.sizes.split(",")]

    run(["docker", "compose", "up", "-d", "--build", "pyflink"], cwd=FLINK_DIR)

    BENCHMARKS_DIR.mkdir(parents=True, exist_ok=True)
    files = {}
    writers = {}
    for case in CASES:
        f = open(BENCHMARKS_DIR / f"{case['name']}.csv", "w", newline="")
        files[case["name"]] = f
        writers[case["name"]] = csv.writer(f)
        writers[case["name"]].writerow(
            ["num_notebooks", "postgres_median_ms", "postgres_p95_ms", "postgres_matches",
             "flink_median_ms", "flink_p95_ms", "flink_matches"]
        )

    for num_notebooks in sizes:
        print(f"=== num_notebooks={num_notebooks} ===")
        regenerate_notebooks(num_notebooks)
        seed_colombus()
        seed_flink()

        for case in CASES:
            postgres_result = query_colombus(case, args.repeat)
            flink_result = query_flink(case, args.repeat)

            writers[case["name"]].writerow([
                num_notebooks,
                postgres_result["timing_ms"]["median_ms"],
                postgres_result["timing_ms"]["p95_ms"],
                len(postgres_result["matches"]),
                flink_result["timing_ms"]["median_ms"],
                flink_result["timing_ms"]["p95_ms"],
                len(flink_result["matches"]),
            ])
            files[case["name"]].flush()
            print(
                f"  {case['name']}: postgres={postgres_result['timing_ms']['median_ms']}ms "
                f"flink={flink_result['timing_ms']['median_ms']}ms"
            )

    for f in files.values():
        f.close()

    print(f"wrote {BENCHMARKS_DIR}")


if __name__ == "__main__":
    main()
