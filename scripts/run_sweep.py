#!/usr/bin/env -S uv run python
import argparse
import csv
import datetime
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
COLOMBUS_DIR = ROOT / "submodules" / "colombus"
FLINK_DIR = ROOT / "submodules" / "colombus-flink"
BENCHMARKS_DIR = ROOT / "data" / f"benchmark-{datetime.datetime.now():%Y%m%d-%H%M%S}"

TOKEN_DELIMITER = "\x1f"

POSTGRES = "postgres"
FLINK = "flink"
DSL = "dsl"
APPROACHES = [POSTGRES, FLINK, DSL]


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
        "dsl_steps": ["Data Modeling", "Model Deployment"],
    },
    {
        "name": "gap",
        "colombus_args": [
            "--regex",
            f"{TOKEN_DELIMITER}Data Modeling(?={TOKEN_DELIMITER}).*?"
            f"{TOKEN_DELIMITER}Model Deployment(?={TOKEN_DELIMITER})",
        ],
        "flink_pattern_define": ("A X*? B", "A=Data Modeling,X=*,B=Model Deployment"),
        "dsl_steps": ["Data Modeling", "*", "Model Deployment"],
    },
    {
        "name": "long_chain",
        "colombus_args": flat_steps(LONG_CHAIN_TERMS),
        "flink_pattern_define": flat_pattern_define(LONG_CHAIN_TERMS),
        "dsl_steps": LONG_CHAIN_TERMS,
    },
    {
        "name": "no_match",
        "colombus_args": flat_steps(["Save Results"] * 6),
        "flink_pattern_define": flat_pattern_define(["Save Results"] * 6),
        "dsl_steps": ["Save Results"] * 6,
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
         *case["colombus_args"], "--repeat", str(repeat), "--mode", "sequences"],
        cwd=COLOMBUS_DIR, capture=True,
    )
    return json.loads(out)


def query_dsl(case: dict, repeat: int) -> dict:
    out = run(
        ["uv", "run", "python", "scripts/benchmark/query_dsl.py",
         "--steps", *case["dsl_steps"], "--repeat", str(repeat)],
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


QUERY_FUNCTIONS = {
    POSTGRES: query_colombus,
    FLINK: query_flink,
    DSL: query_dsl,
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", nargs="+", type=int, default=[100, 500, 1000, 5000])
    parser.add_argument("--repeat", type=int, default=10)
    parser.add_argument("--approaches", nargs="+", choices=APPROACHES, default=APPROACHES)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    sizes = args.sizes
    approaches = [a for a in APPROACHES if a in set(args.approaches)]

    needs_colombus = POSTGRES in approaches or DSL in approaches
    needs_flink = FLINK in approaches

    if needs_flink:
        run(["docker", "compose", "up", "-d", "--build", "pyflink"], cwd=FLINK_DIR)

    BENCHMARKS_DIR.mkdir(parents=True, exist_ok=True)
    files = {}
    writers = {}
    for case in CASES:
        f = open(BENCHMARKS_DIR / f"{case['name']}.csv", "w", newline="")
        files[case["name"]] = f
        writers[case["name"]] = csv.writer(f)
        header = ["num_notebooks"]
        for approach in approaches:
            header += [f"{approach}_median_ms", f"{approach}_p95_ms", f"{approach}_matches"]
        writers[case["name"]].writerow(header)

    for num_notebooks in sizes:
        print(f"=== num_notebooks={num_notebooks} ===")
        regenerate_notebooks(num_notebooks)
        if needs_colombus:
            seed_colombus()
        if needs_flink:
            seed_flink()

        for case in CASES:
            row = [num_notebooks]
            summary_parts = []
            for approach in approaches:
                result = QUERY_FUNCTIONS[approach](case, args.repeat)

                row += [
                    result["timing_ms"]["median_ms"],
                    result["timing_ms"]["p95_ms"],
                    result["match_occurrences"],
                ]
                summary_parts.append(f"{approach}={result['timing_ms']['median_ms']}ms")

            writers[case["name"]].writerow(row)
            files[case["name"]].flush()
            print(f"  {case['name']}: " + " ".join(summary_parts))

    for f in files.values():
        f.close()

    print(f"wrote {BENCHMARKS_DIR}")


if __name__ == "__main__":
    main()
