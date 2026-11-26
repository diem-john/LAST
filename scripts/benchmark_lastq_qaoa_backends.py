"""Repeated, order-balanced CPU/GPU benchmark for LAST-Q QAOA.

Runs one warm-up per backend, then paired CPU/GPU trials with alternating
execution order. Each measured trial delegates to scripts.run_lastq_qaoa.
"""
from __future__ import annotations

import argparse
import csv
import json
import platform
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKENDS = {"cpu": "qpp-cpu", "gpu": "nvidia"}


def package_version(module_name: str) -> str | None:
    try:
        module = __import__(module_name)
        return str(getattr(module, "__version__", "unknown"))
    except Exception:
        return None


def hardware_metadata() -> dict:
    metadata = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "cudaq_version": package_version("cudaq"),
        "scipy_version": package_version("scipy"),
    }
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        metadata["nvidia_smi"] = (
            result.stdout.strip() if result.returncode == 0
            else result.stderr.strip()
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        metadata["nvidia_smi"] = str(exc)
    return metadata


def run_trial(
    backend: str,
    seed: int,
    repetition: int,
    output_path: Path,
    *,
    layers: int,
    starts: int,
    max_iterations: int,
    shots: int,
) -> dict:
    target = BACKENDS[backend]
    command = [
        sys.executable,
        "-m",
        "scripts.run_lastq_qaoa",
        "--target", target,
        "--shots", str(shots),
        "--layers", str(layers),
        "--max-iterations", str(max_iterations),
        "--starts", str(starts),
        "--seed", str(seed),
        "--output", str(output_path),
    ]

    wall_start = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    process_wall_seconds = time.perf_counter() - wall_start

    if completed.returncode != 0:
        raise RuntimeError(
            f"{backend.upper()} run failed (seed={seed}, repetition={repetition}).\n"
            f"Command: {' '.join(command)}\n"
            f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )

    try:
        data = json.loads(output_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(
            f"Could not read valid QAOA result JSON: {output_path}\n"
            f"Runner stdout:\n{completed.stdout}\n"
            f"Runner stderr:\n{completed.stderr}"
        ) from exc

    sample = data.get("final_sample", {})
    return {
        "backend": backend,
        "target": data.get("target", target),
        "seed": seed,
        "repetition": repetition,
        "optimizer_success": data.get("optimizer_success"),
        "all_starts_successful": data.get("all_starts_successful"),
        "selected_start_index": data.get("selected_start_index"),
        "exact_expectation": data.get("exact_final_expectation"),
        "sampled_expected_energy": sample.get("expected_qubo_energy"),
        "feasible_probability": sample.get("topology_feasible_probability"),
        "optimization_runtime_seconds": data.get("optimization_runtime_seconds"),
        "sampling_runtime_seconds": data.get("final_sampling_runtime_seconds"),
        "objective_evaluations": data.get("objective_evaluations"),
        "process_wall_seconds": process_wall_seconds,
        "output_json": str(output_path.relative_to(ROOT)),
    }


def mean_sd(values: list[float]) -> dict:
    return {
        "mean": statistics.mean(values),
        "sample_sd": statistics.stdev(values) if len(values) > 1 else 0.0,
        "median": statistics.median(values),
        "n": len(values),
    }


def summarize(records: list[dict]) -> dict:
    backend_summary = {}
    for backend in BACKENDS:
        rows = [row for row in records if row["backend"] == backend]
        backend_summary[backend] = {
            "n": len(rows),
            "exact_expectation": mean_sd(
                [float(row["exact_expectation"]) for row in rows]
            ),
            "sampled_expected_energy": mean_sd(
                [float(row["sampled_expected_energy"]) for row in rows]
            ),
            "feasible_probability": mean_sd(
                [float(row["feasible_probability"]) for row in rows]
            ),
            "optimization_runtime_seconds": mean_sd(
                [float(row["optimization_runtime_seconds"]) for row in rows]
            ),
            "sampling_runtime_seconds": mean_sd(
                [float(row["sampling_runtime_seconds"]) for row in rows]
            ),
            "process_wall_seconds": mean_sd(
                [float(row["process_wall_seconds"]) for row in rows]
            ),
            "selected_optimizer_success_rate": sum(
                bool(row["optimizer_success"]) for row in rows
            ) / len(rows),
            "all_starts_success_rate": sum(
                bool(row["all_starts_successful"]) for row in rows
            ) / len(rows),
        }

    keyed = {
        (row["seed"], row["repetition"], row["backend"]): row
        for row in records
    }
    paired_speedups = []
    paired_exact_differences = []
    paired_feasible_differences = []
    for seed in sorted({row["seed"] for row in records}):
        repetitions = sorted({
            row["repetition"] for row in records if row["seed"] == seed
        })
        for repetition in repetitions:
            cpu = keyed.get((seed, repetition, "cpu"))
            gpu = keyed.get((seed, repetition, "gpu"))
            if cpu is None or gpu is None:
                continue
            paired_speedups.append(
                float(cpu["optimization_runtime_seconds"])
                / float(gpu["optimization_runtime_seconds"])
            )
            paired_exact_differences.append(
                float(gpu["exact_expectation"])
                - float(cpu["exact_expectation"])
            )
            paired_feasible_differences.append(
                float(gpu["feasible_probability"])
                - float(cpu["feasible_probability"])
            )

    return {
        "backend_summary": backend_summary,
        "paired_comparison": {
            "complete_pairs": len(paired_speedups),
            "gpu_speedup_ratio": mean_sd(paired_speedups),
            "gpu_minus_cpu_exact_expectation": mean_sd(
                paired_exact_differences
            ),
            "gpu_minus_cpu_feasible_probability": mean_sd(
                paired_feasible_differences
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", nargs="+", type=int, default=[7, 11, 21, 42])
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--layers", type=int, default=3)
    parser.add_argument("--starts", type=int, default=5)
    parser.add_argument("--max-iterations", type=int, default=300)
    parser.add_argument("--shots", type=int, default=2048)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "reports" / "quantum" / "backend_validation",
    )
    args = parser.parse_args()

    if args.repetitions < 1 or args.warmups < 0:
        parser.error("--repetitions must be >= 1 and --warmups must be >= 0")
    if not args.seeds or len(set(args.seeds)) != len(args.seeds):
        parser.error("--seeds must be non-empty and unique")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = args.output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    config = {
        "layers": args.layers,
        "starts": args.starts,
        "max_iterations_per_start": args.max_iterations,
        "shots": args.shots,
        "seeds": args.seeds,
        "repetitions_per_seed_backend": args.repetitions,
        "warmups_per_backend": args.warmups,
        "execution_order": "alternating CPU/GPU order across seed-repetition pairs",
    }

    print("LAST-Q repeated CPU/GPU benchmark")
    print(f"Output directory: {run_dir.relative_to(ROOT)}")
    print(f"Configuration: {json.dumps(config)}")

    # Warm-up each backend once; warm-up runs are deliberately excluded.
    for backend in ("cpu", "gpu"):
        for warmup_index in range(1, args.warmups + 1):
            warmup_path = run_dir / f"warmup_{backend}_{warmup_index}.json"
            print(f"\nWARM-UP {backend.upper()} ({warmup_index}/{args.warmups})")
            run_trial(
                backend, args.seeds[0], 0, warmup_path,
                layers=args.layers,
                starts=args.starts,
                max_iterations=args.max_iterations,
                shots=args.shots,
            )

    records = []
    pair_index = 0
    for seed in args.seeds:
        for repetition in range(1, args.repetitions + 1):
            order = ("cpu", "gpu") if pair_index % 2 == 0 else ("gpu", "cpu")
            pair_index += 1
            print(
                f"\nPAIR seed={seed}, repetition={repetition}: "
                f"{order[0].upper()} then {order[1].upper()}"
            )
            for backend in order:
                output_path = run_dir / (
                    f"lastq_bus6_qaoa_{backend}_p{args.layers}_"
                    f"multistart{args.starts}_seed{seed}_rep{repetition}.json"
                )
                print(f"Running {backend.upper()} -> {output_path.name}")
                row = run_trial(
                    backend, seed, repetition, output_path,
                    layers=args.layers,
                    starts=args.starts,
                    max_iterations=args.max_iterations,
                    shots=args.shots,
                )
                records.append(row)
                print(
                    f"  exact={row['exact_expectation']:.6f}, "
                    f"feasible={row['feasible_probability']:.2%}, "
                    f"optimization={row['optimization_runtime_seconds']:.4f}s"
                )

    summary = summarize(records)
    payload = {
        "benchmark": "LAST-Q P3 repeated CPU/GPU backend validation",
        "run_id_utc": run_id,
        "configuration": config,
        "hardware_and_software": hardware_metadata(),
        "warmups_excluded_from_statistics": True,
        "records": records,
        **summary,
        "interpretation_note": (
            "This is a CPU-versus-GPU backend benchmark for a five-qubit "
            "QAOA demonstrator. It does not establish quantum advantage."
        ),
    }

    json_path = run_dir / "benchmark_summary.json"
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    csv_path = run_dir / "benchmark_records.csv"
    fieldnames = list(records[0].keys())
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    paired = summary["paired_comparison"]
    print("\nBENCHMARK SUMMARY (mean ± sample SD)")
    for backend in BACKENDS:
        metrics = summary["backend_summary"][backend]
        print(f"\n{backend.upper()} (n={metrics['n']})")
        for key in (
            "exact_expectation",
            "feasible_probability",
            "optimization_runtime_seconds",
            "sampling_runtime_seconds",
        ):
            item = metrics[key]
            suffix = "%" if key == "feasible_probability" else ""
            scale = 100 if suffix else 1
            print(
                f"  {key}: {item['mean'] * scale:.6f}"
                f"{suffix} ± {item['sample_sd'] * scale:.6f}{suffix}"
            )
        print(
            "  all-start convergence rate: "
            f"{metrics['all_starts_success_rate']:.1%}"
        )

    speedup = paired["gpu_speedup_ratio"]
    print(
        f"\nPaired GPU optimization speedup: "
        f"{speedup['mean']:.4f}x ± {speedup['sample_sd']:.4f}x "
        f"(n={paired['complete_pairs']})"
    )
    print(f"JSON summary: {json_path.relative_to(ROOT)}")
    print(f"CSV records:  {csv_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
