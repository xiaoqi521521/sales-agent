from contextvars import ContextVar, Token

from app.core.auth_context import CurrentUser


_current_user: ContextVar[CurrentUser | None] = ContextVar("current_user", default=None)


def get_current_user() -> CurrentUser | None:
    return _current_user.get()


def require_current_user() -> CurrentUser:
    user = get_current_user()
    if user is None:
        raise RuntimeError("current user context is not set")
    return user


def set_current_user(user: CurrentUser) -> Token[CurrentUser | None]:
    return _current_user.set(user)


def reset_current_user(token: Token[CurrentUser | None]) -> None:
    _current_user.reset(token)
