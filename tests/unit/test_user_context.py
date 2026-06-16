import pytest

from app.core.auth_context import CurrentUser
from app.core.user_context import get_current_user, reset_current_user, require_current_user, set_current_user


def test_current_user_context_can_be_set_and_reset():
    user = CurrentUser(username="Zhang Wei", role="SALES_REP", region_id=1, rep_id=2)

    token = set_current_user(user)
    try:
        assert get_current_user() == user
        assert require_current_user() == user
    finally:
        reset_current_user(token)

    assert get_current_user() is None
    with pytest.raises(RuntimeError, match="current user context is not set"):
        require_current_user()


def test_current_user_context_reset_restores_previous_value():
    director = CurrentUser(username="Director", role="SALES_DIRECTOR", region_id=None, rep_id=5)
    rep = CurrentUser(username="Zhang Wei", role="SALES_REP", region_id=1, rep_id=2)

    director_token = set_current_user(director)
    try:
        rep_token = set_current_user(rep)
        try:
            assert get_current_user() == rep
        finally:
            reset_current_user(rep_token)

        assert get_current_user() == director
    finally:
        reset_current_user(director_token)

