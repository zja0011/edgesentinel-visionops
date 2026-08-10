"""Run the fail-closed repository publication gate."""

import os
import sys

from packages.harness.repository_publication import RepositoryPublicationGate
from packages.harness.utf8 import print_json_utf8


PROJECT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir)
)


def main():
    result = RepositoryPublicationGate(PROJECT_DIR).check()
    print_json_utf8(result)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
