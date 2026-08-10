"""Read-only Harness wrapper for fixed project data usage."""

from packages.monitoring.storage import ProjectStorageInventory


class StorageUsageTools(object):
    def __init__(self, project_dir, inventory=None):
        self.inventory = inventory or ProjectStorageInventory(
            project_dir
        )

    def get_usage(self, unused_arguments):
        return self.inventory.snapshot()
