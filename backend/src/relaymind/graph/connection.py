import os
from falkordb import FalkorDB


def create_client() -> FalkorDB:
    """Called explicitly, not during import or the liveness check."""
    return FalkorDB(
        host=os.getenv("FALKORDB_HOST", "127.0.0.1"),
        port=int(os.getenv("FALKORDB_PORT", "6379")),
        password=os.environ["FALKORDB_PASSWORD"],
    )

# Tenant-to-graph selection must be added behind verified server identity.
# Never call select_graph with a browser/model supplied graph name.
