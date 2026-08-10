# GitHub publication runbook

## Publication model

Start with a private repository. The Windows working tree is the authoritative
source; Jetson is a deployment and hardware-acceptance target. Runtime data and
credentials never flow back into Git or GitHub.

The default branch is `main`. Pull requests must pass the `CI / validate` job.
Recommended branch protection settings are:

- require a pull request and one approval;
- require the CI status check and branches to be up to date;
- dismiss stale approvals after new commits;
- block force pushes and branch deletion;
- require conversation resolution;
- restrict direct pushes to administrators during the private pilot.

## Local preflight

```bash
python3 -m unittest discover -s tests -q
bash scripts/run_repository_publication_gate.sh
bash scripts/run_release_provenance_test.sh
```

The publication gate scans only files eligible for Git tracking. It fails on
runtime data, mutable zone configuration, credentials, private keys, model
engines, databases, logs, unexpected binaries, oversized files, or recognized
secret formats. Findings contain only issue codes and relative paths.

## Repository creation

Create an empty private GitHub repository named `edgesentinel-visionops`; do
not initialize it with a README, license, or `.gitignore`. Then configure the
local remote and push `main`. Do not place a personal access token in a remote
URL or shell script; use Git Credential Manager, SSH, or GitHub CLI login.

After the repository owner and name are known, enable private vulnerability
reporting and update issue-template security guidance if needed.

## Release process

1. Update `VERSION` and merge through a passing pull request.
2. From a clean `main`, create an annotated tag matching `v$(cat VERSION)`.
3. Push the tag.
4. The Release workflow reruns all gates, generates the Manifest and CycloneDX
   SBOM, verifies their hashes, and publishes them through the repository-scoped
   `GITHUB_TOKEN`.

Example for the development release:

```bash
git tag -a v0.1.0-dev.1 -m "EdgeSentinel VisionOps v0.1.0-dev.1"
git push origin v0.1.0-dev.1
```

Prerelease versions containing `-` are marked as GitHub prereleases. The
workflow accepts annotated tags only and requires the tag to match `VERSION`.

## Public-release checklist

- repository publication gate passes on tracked files;
- no Git history contains credentials or operational data;
- Apache-2.0 project license is visible;
- third-party wheel and model redistribution terms have been reviewed;
- Security Advisories/private vulnerability reporting are enabled;
- branch protection and required checks are active;
- the private release has been installed and verified on Jetson;
- backup, restore drill, authentication, TLS, and rollback runbooks are current.
