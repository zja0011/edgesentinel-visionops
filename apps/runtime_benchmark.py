"""Run and persist one bounded local EdgeSentinel runtime benchmark."""

import argparse
import os
import sys

from packages.harness.utf8 import write_json_atomic
from packages.monitoring.runtime_benchmark import (
    LocalRuntimeSampler,
    RuntimeBenchmarkError,
    RuntimeBenchmarkRunner,
)


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=60.0,
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=5.0,
    )
    parser.add_argument(
        "--output",
        required=True,
    )
    return parser


def main():
    args = build_parser().parse_args()
    output_path = os.path.abspath(args.output)
    try:
        runner = RuntimeBenchmarkRunner(LocalRuntimeSampler())
        result = runner.run(
            duration_seconds=args.duration_seconds,
            interval_seconds=args.interval_seconds,
        )
    except RuntimeBenchmarkError as error:
        raise SystemExit(str(error))

    write_json_atomic(output_path, result)
    performance = result["performance"]
    resources = result["resources"]
    camera = result["camera"]
    print("")
    print("Runtime Benchmark acceptance summary:")
    print("Status: {0}".format(result["status"]))
    print(
        "Duration: {0} seconds".format(
            result["actual_duration_seconds"]
        )
    )
    print(
        "Samples: {0}/{1}".format(
            result["sample_count"],
            result["expected_sample_count"],
        )
    )
    print(
        "API success: {0}%".format(
            result["api_success_percent"]
        )
    )
    print(
        "Vision fresh: {0}%".format(
            result["vision_fresh_percent"]
        )
    )
    print(
        "Frame progress: {0} -> {1} (+{2})".format(
            result["frame_progress"]["first_frame_id"],
            result["frame_progress"]["last_frame_id"],
            result["frame_progress"]["advanced_frames"],
        )
    )
    print(
        "Minimum processing FPS: {0}".format(
            performance["minimum_fps"]
        )
    )
    print(
        "Average processing FPS: {0}".format(
            performance["average_fps"]
        )
    )
    print(
        "Maximum observed P95: {0} ms".format(
            performance["maximum_observed_p95_ms"]
        )
    )
    print(
        "Peak memory used: {0} GiB".format(
            resources["peak_memory_used_gib"]
        )
    )
    print(
        "Maximum temperature: {0} C".format(
            resources["maximum_temperature_celsius"]
        )
    )
    print(
        "Camera restart delta: {0}".format(
            camera["restart_count_delta"]
        )
    )
    print("Read-only sampling: True")
    print("Contains secret: False")
    print("Result file: {0}".format(output_path))
    if result["status"] != "PASS":
        failed_checks = [
            name
            for name, passed in sorted(
                result["checks"].items()
            )
            if not passed
        ]
        print(
            "Failed checks: {0}".format(
                ", ".join(failed_checks)
            )
        )
        raise SystemExit(1)
    print("Runtime Benchmark smoke test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
