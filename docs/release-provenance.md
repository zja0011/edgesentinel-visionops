# Release provenance and SBOM

EdgeSentinel release artifacts identify the exact software tree that was
tested and prepared for deployment. They are separate from runtime data and
disaster-recovery backups.

## Trust boundary

The generator uses a fixed source allowlist: application and package code,
deployment assets, scripts, tests, documentation, versioned Skills and evals,
the default zone configuration, pinned requirements, and vendored Python
distributions. It excludes `data/`, the mutable `configs/zones.json`, model
engines, credentials, TLS material, evidence, logs, and recovery backups.

Symlinks and credential-like file names are rejected. Every recorded path is
relative to the project, and generation is bounded to 4096 files and 256 MiB.
JSON output is always UTF-8 with LF line endings so Windows and Jetson produce
the same content hashes.

## Build and verify

The version is read from `VERSION` unless it is explicitly supplied:

```bash
bash scripts/build_release_artifacts.sh
bash scripts/check_release_integrity.sh
```

To prepare a specific version:

```bash
bash scripts/build_release_artifacts.sh 0.1.0
```

The output is written below `dist/releases/` and contains:

- `release-manifest.json`: relative file inventory, sizes, SHA-256 hashes,
  aggregate source identity, dependency lock status, and security boundary;
- `release-manifest.sha256`: independent manifest checksum;
- `bom.cdx.json`: deterministic CycloneDX 1.7 SBOM;
- `current-release.json`: bounded pointer to the most recently built release.

The verifier checks the manifest sidecar, SBOM, every source file, unexpected
allowlisted files, aggregate source identity, and release ID. It is read-only.

## GitHub boundary

Generated `dist/` content is intentionally ignored by Git. A future GitHub
release workflow should regenerate and verify these files from a clean commit,
then upload them as release artifacts. The repository must not publish files
from `/etc/edgesentinel-visionops`, `data/`, private model engines, or recovery
exports.

Before the repository is made public, select and add a `LICENSE`, review model
and vendored-wheel redistribution terms, and run an independent secret scan.
