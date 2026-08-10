#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
WHEEL_DIR="${PROJECT_DIR}/vendor/wheels"
TARGET_DIR="${PROJECT_DIR}/vendor/python"
BOOTSTRAP_DIR="${PROJECT_DIR}/vendor/pip"
REQUIREMENTS="${PROJECT_DIR}/requirements-api-py36.txt"
BOOTSTRAP_WHEEL="${WHEEL_DIR}/pip-21.3.1-py3-none-any.whl"

if [[ ! -d "${WHEEL_DIR}" ]]; then
    echo "ERROR: offline package directory not found: ${WHEEL_DIR}" >&2
    echo "Run scripts/download_api_dependencies.ps1 on Windows and upload the whole project again." >&2
    exit 1
fi

if [[ ! -f "${REQUIREMENTS}" ]]; then
    echo "ERROR: requirements file not found: ${REQUIREMENTS}" >&2
    exit 1
fi

if [[ ! -f "${BOOTSTRAP_WHEEL}" ]]; then
    echo "ERROR: Python 3.6 pip bootstrap not found: ${BOOTSTRAP_WHEEL}" >&2
    echo "Run scripts/download_api_dependencies.ps1 on Windows and upload the whole project again." >&2
    exit 1
fi

mkdir -p "${TARGET_DIR}"
mkdir -p "${BOOTSTRAP_DIR}"

echo "Bootstrapping pip 21.3.1 inside the mounted project..."
python3 -m pip install \
    --disable-pip-version-check \
    --no-index \
    --no-deps \
    --target "${BOOTSTRAP_DIR}" \
    --upgrade \
    "${BOOTSTRAP_WHEEL}"

echo
echo "Bootstrap pip version:"
PYTHONPATH="${BOOTSTRAP_DIR}" \
python3 -m pip --version

echo
echo "Installing the offline API dependencies into:"
echo "  ${TARGET_DIR}"
PYTHONPATH="${BOOTSTRAP_DIR}" \
python3 -m pip install \
    --disable-pip-version-check \
    --no-index \
    --find-links "${WHEEL_DIR}" \
    --target "${TARGET_DIR}" \
    --upgrade \
    -r "${REQUIREMENTS}"

echo
echo "Verifying the Python 3.6 API environment..."
PYTHONPATH="${TARGET_DIR}:${PROJECT_DIR}${PYTHONPATH:+:${PYTHONPATH}}" \
python3 -c "import fastapi, uvicorn; print('FastAPI', fastapi.__version__, 'Uvicorn', uvicorn.__version__)"

echo
echo "API dependencies are ready and persist in the mounted project directory."
