#!/usr/bin/env -S uv run python
import argparse
import json
import pathlib
import random
import shutil

VOCAB = [
    "Data Collection",
    "Data Preparation",
    "Data Modeling",
    "Model Evaluation",
    "Model Deployment",
    "Save Results",
]

NEEDLES: dict[str, list[str]] = {
    "adjacent_model_deploy": ["Data Modeling", "Model Deployment"],
    "gapped_model_deploy": [
        "Data Modeling",
        "Model Evaluation",
        "Model Evaluation",
        "Model Deployment",
    ],
    "triple_prep_run": [
        "Data Preparation",
        "Data Preparation",
        "Data Preparation",
        "Data Modeling",
    ],
    "anchored_start": ["Data Collection", "Data Preparation", "Data Modeling"],
    "modeling_eval_loop": [
        "Data Modeling",
        "Model Evaluation",
        "Data Modeling",
        "Model Evaluation",
        "Data Modeling",
        "Model Evaluation",
    ],
    "long_full_pipeline": [
        "Data Collection",
        "Data Preparation",
        "Data Preparation",
        "Data Modeling",
        "Model Evaluation",
        "Data Preparation",
        "Data Modeling",
        "Model Evaluation",
        "Data Modeling",
        "Model Evaluation",
        "Model Deployment",
        "Save Results",
    ],
    "long_dense_cycle": [
        "Data Collection",
        "Data Preparation",
        "Data Modeling",
        "Model Evaluation",
        "Data Modeling",
        "Model Evaluation",
        "Data Preparation",
        "Data Modeling",
        "Model Evaluation",
        "Data Modeling",
        "Model Evaluation",
        "Model Deployment",
        "Save Results",
    ],
}

NEEDLE_RATE = 0.1
ANCHORED_NEEDLES = {"anchored_start"}


def assign_needles(num_notebooks: int) -> dict[int, str]:
    per_needle = round(num_notebooks * NEEDLE_RATE)
    indices = list(range(num_notebooks))
    random.shuffle(indices)

    assignment: dict[int, str] = {}
    cursor = 0
    for needle_name in NEEDLES:
        for index in indices[cursor : cursor + per_needle]:
            assignment[index] = needle_name
        cursor += per_needle
    return assignment


def build_sequence(min_steps: int, max_steps: int, needle_name: str | None) -> list[str]:
    sequence = [random.choice(VOCAB) for _ in range(random.randint(min_steps, max_steps))]
    if needle_name is None:
        return sequence
    needle_terms = NEEDLES[needle_name]
    insert_at = 0 if needle_name in ANCHORED_NEEDLES else random.randint(0, len(sequence))
    return sequence[:insert_at] + needle_terms + sequence[insert_at:]


def generate(
    out_dir: pathlib.Path, num_notebooks: int, min_steps: int, max_steps: int
) -> dict:
    needle_assignment = assign_needles(num_notebooks)
    manifest_notebooks = {}

    for index in range(num_notebooks):
        needle_name = needle_assignment.get(index)
        sequence = build_sequence(min_steps, max_steps, needle_name)
        name = f"notebook-{index:05d}"

        notebook = {"name": name, "source": [{"name": step} for step in sequence]}
        (out_dir / f"{name}.json").write_text(json.dumps(notebook, indent=2))

        manifest_notebooks[name] = {"needle": needle_name, "steps": sequence}

    needle_counts = {
        needle_name: sum(
            1 for nb in manifest_notebooks.values() if nb["needle"] == needle_name
        )
        for needle_name in NEEDLES
    }

    return {
        "num_notebooks": num_notebooks,
        "vocab": VOCAB,
        "needles": NEEDLES,
        "needle_counts": needle_counts,
        "notebooks": manifest_notebooks,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out-dir",
        type=pathlib.Path,
        default=pathlib.Path(__file__).resolve().parent.parent / "data" / "notebooks",
    )
    parser.add_argument("--num-notebooks", type=int, default=1000)
    parser.add_argument("--min-steps", type=int, default=20)
    parser.add_argument("--max-steps", type=int, default=60)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--reset", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    random.seed(args.seed)

    if args.out_dir.exists() and any(args.out_dir.iterdir()):
        if not args.reset:
            raise SystemExit(f"{args.out_dir} already has files in it, pass --reset")
        shutil.rmtree(args.out_dir)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    manifest = generate(args.out_dir, args.num_notebooks, args.min_steps, args.max_steps)
    manifest_path = args.out_dir.parent / f"{args.out_dir.name}.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    print(f"notebooks={args.num_notebooks} out_dir={args.out_dir}")
    print(f"needle_counts={manifest['needle_counts']}")
    print(f"manifest={manifest_path}")


if __name__ == "__main__":
    main()
