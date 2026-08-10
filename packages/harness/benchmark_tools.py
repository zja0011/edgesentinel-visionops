"""Read-only Harness access to persisted runtime benchmark evidence."""

from packages.monitoring.benchmark_store import RuntimeBenchmarkStore


class RuntimeBenchmarkTools(object):
    def __init__(self, project_dir, store=None):
        self.store = store or RuntimeBenchmarkStore(project_dir)

    def get_latest(self, unused_arguments):
        return self.store.get_latest()
