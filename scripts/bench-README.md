# Benchmark scripts

- `bench-generate.py`: generates synthetic notebooks with planted sequences and a manifest used to check correctness.
- `bench-run.py`: for each size, regenerates notebooks, seeds database, times and checks all approaches.

## Requirements

Bring up colombus and colombus-flink first:
```
make up ENV=dev APPS="colombus colombus-flink"
```

## Usage

```
uv run scripts/bench-run.py --sizes 100 500 1000
```

Only `bench-run.py` needs to be run directly as it calls `bench-generate.py` itself for each size.

Options:
- `--sizes`: notebook counts to test, one row per size.
- `--repeat`: queries per case, used for timing stats.
- `--approaches`: subset of `regex`, `flink`, `multijoin` to run.
