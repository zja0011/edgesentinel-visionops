# Contributing

## Development boundary

EdgeSentinel targets JetPack 4 and Python 3.6 at runtime. New source code must
remain Python 3.6 compatible unless the runtime baseline is explicitly changed.
Do not commit credentials, runtime data, evidence, model engines, TLS material,
recovery exports, or a mutable `configs/zones.json`.

## Before opening a pull request

Run:

```bash
python3 -m unittest discover -s tests -q
bash scripts/run_repository_publication_gate.sh
bash scripts/run_release_provenance_test.sh
```

Describe the behavior change, policy risk level, tests performed, and whether
the change affects API compatibility, stored data, security boundaries, model
behavior, or Jetson deployment.

## Change discipline

- keep L1/L2 side effects confirmation-gated;
- preserve default deny and bounded execution;
- update tests and operator documentation together;
- avoid adding dependencies unless they are pinned and represented in the SBOM;
- keep generated `dist/` content out of commits.

Contributions are submitted under the Apache License 2.0.
