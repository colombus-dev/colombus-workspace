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
BENCHMARKS_DIR = ROOT / "data" / f"benchmark-{datetime.datetime.now():%Y%m%d-%H%M%S}"

TOKEN_DELIMITER = "\x1f"

REGEX = "regex"
FLINK = "flink"
MULTIJOIN = "multijoin"
APPROACHES = [REGEX, FLINK, MULTIJOIN]


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
        "regex_args": flat_steps(["Data Modeling", "Model Deployment"]),
        "flink_pattern_define": flat_pattern_define(["Data Modeling", "Model Deployment"]),
        "multijoin_steps": ["Data Modeling", "Model Deployment"],
    },
    {
        "name": "gap",
        "regex_args": [
            "--regex",
            f"{TOKEN_DELIMITER}Data Modeling(?={TOKEN_DELIMITER}).*?"
            f"{TOKEN_DELIMITER}Model Deployment(?={TOKEN_DELIMITER})",
        ],
        "flink_pattern_define": ("A X*? B", "A=Data Modeling,X=*,B=Model Deployment"),
        "multijoin_steps": ["Data Modeling", "*", "Model Deployment"],
    },
    {
        "name": "long_chain",
        "regex_args": flat_steps(LONG_CHAIN_TERMS),
        "flink_pattern_define": flat_pattern_define(LONG_CHAIN_TERMS),
        "multijoin_steps": LONG_CHAIN_TERMS,
    },
    {
        "name": "no_match",
        "regex_args": flat_steps(["Save Results"] * 6),
        "flink_pattern_define": flat_pattern_define(["Save Results"] * 6),
        "multijoin_steps": ["Save Results"] * 6,
    },
]


def run(cmd: list[str], cwd: pathlib.Path, capture: bool = False) -> str:
    result = subprocess.run(cmd, cwd=cwd, capture_output=capture, text=True)
    if result.returncode != 0:
        if capture:
            sys.stderr.write(result.stderr)
        raise subprocess.CalledProcessError(result.returncode, cmd)
    return result.stdout if capture else ""


def regenerate_notebooks(num_notebooks: int) -> None:
    run(
        [sys.executable, str(ROOT / "scripts" / "bench-generate.py"),
         "--num-notebooks", str(num_notebooks), "--reset"],
        cwd=ROOT,
    )


def seed_colombus() -> None:
    run(["uv", "run", "python", "scripts/benchmark/seed.py", "--reset"], cwd=COLOMBUS_DIR)


def query_regex(case: dict, repeat: int) -> dict:
    out = run(
        ["uv", "run", "python", "scripts/benchmark/query.py",
         *case["regex_args"], "--repeat", str(repeat), "--mode", "sequences"],
        cwd=COLOMBUS_DIR, capture=True,
    )
    return json.loads(out)


def query_multijoin(case: dict, repeat: int) -> dict:
    out = run(
        ["uv", "run", "python", "scripts/benchmark/query_dsl.py",
         "--steps", *case["multijoin_steps"], "--repeat", str(repeat), "--quiet"],
        cwd=COLOMBUS_DIR, capture=True,
    )
    return json.loads(out)


def query_flink(case: dict, repeat: int) -> dict:
    pattern, define = case["flink_pattern_define"]
    out = run(
        ["docker", "compose", "-f", "docker-compose.dev.yml", "exec", "-T",
         "pyflink", "python", "query.py",
         "--pattern", pattern, "--define", define,
         "--repeat", str(repeat), "--quiet"],
        cwd=ROOT, capture=True,
    )
    return json.loads(out)


QUERY_FUNCTIONS = {
    REGEX: query_regex,
    FLINK: query_flink,
    MULTIJOIN: query_multijoin,
}


TIMED_OUT_RESULT = {
    "matches": [],
    "match_occurrences": -1,
    "timing_ms": {"median_ms": -1, "p95_ms": -1},
    "timed_out": True,
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

    needs_colombus = REGEX in approaches or MULTIJOIN in approaches

    BENCHMARKS_DIR.mkdir(parents=True, exist_ok=True)
    files = {}
    writers = {}
    for case in CASES:
        f = open(BENCHMARKS_DIR / f"{case['name']}.csv", "w", newline="")
        files[case["name"]] = f
        writers[case["name"]] = csv.writer(f)
        header = ["num_notebooks"]
        header += [f"{approach}_median_ms" for approach in approaches]
        header += [f"{approach}_matches" for approach in approaches]
        header += [f"{approach}_p95_ms" for approach in approaches]
        writers[case["name"]].writerow(header)

    timed_out_pairs: set[tuple[str, str]] = set()

    for num_notebooks in sizes:
        print(f"=== num_notebooks={num_notebooks} ===")
        regenerate_notebooks(num_notebooks)
        if needs_colombus:
            seed_colombus()

        for case in CASES:
            results = {}
            summary_parts = []
            for approach in approaches:
                key = (case["name"], approach)
                if key in timed_out_pairs:
                    results[approach] = TIMED_OUT_RESULT
                else:
                    results[approach] = QUERY_FUNCTIONS[approach](case, args.repeat)
                    if results[approach].get("timed_out"):
                        timed_out_pairs.add(key)
                summary_parts.append(
                    f"{approach}={results[approach]['timing_ms']['median_ms']}ms"
                )

            row = [num_notebooks]
            row += [results[a]["timing_ms"]["median_ms"] for a in approaches]
            row += [results[a]["match_occurrences"] for a in approaches]
            row += [results[a]["timing_ms"]["p95_ms"] for a in approaches]

            writers[case["name"]].writerow(row)
            files[case["name"]].flush()
            print(f"  {case['name']}: " + " ".join(summary_parts))

    for f in files.values():
        f.close()

    print(f"wrote {BENCHMARKS_DIR}")


if __name__ == "__main__":
    main()
