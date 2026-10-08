from .base import DataSource


def get_source(name: str, **kwargs) -> DataSource:
    """Crée une source par son nom ; ``kwargs`` sont passés au constructeur
    (ex. ``get_source("replay", path=..., speed=2.0, loop=True)``)."""
    if name == "mock":
        from .mock import MockSource
        return MockSource(**kwargs)
    if name == "lmu":
        from .lmu_shared_memory import LmuSharedMemorySource
        return LmuSharedMemorySource(**kwargs)
    if name == "replay":
        from .recording import ReplaySource
        return ReplaySource(**kwargs)
    raise ValueError(f"Source inconnue : {name}")
