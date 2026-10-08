from abc import ABC, abstractmethod

from ..model import Snapshot


class DataSource(ABC):
    """Une source lit le jeu (ou simule) et renvoie un Snapshot à chaque appel."""

    name = "base"

    @abstractmethod
    def read(self) -> Snapshot: ...

    def close(self) -> None:
        pass
