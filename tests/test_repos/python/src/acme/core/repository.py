class RepositoryManager:
    def __init__(self, prefix: str) -> None:
        self._prefix = prefix

    def build(self, name: str) -> str:
        return f"{self._prefix}:{name}"


def build_repository_id(name: str) -> str:
    manager = RepositoryManager("repo")
    return manager.build(name)
