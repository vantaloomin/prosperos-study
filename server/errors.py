class DomainError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = 'request'):
        self.message = message
        self.status = status
        self.code = code
        super().__init__(message)


def require(condition: bool, message: str, status: int = 400) -> None:
    if not condition:
        raise DomainError(message, status)
