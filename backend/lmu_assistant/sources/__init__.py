from .base import DataSource


def get_source(name: str) -> DataSource:
    if name == "mock":
        from .mock import MockSource
        return MockSource()
    if name == "lmu":
        from .lmu_shared_memory import LmuSharedMemorySource
        return LmuSharedMemorySource()
    raise ValueError(f"Source inconnue : {name}")
