import pytest
from django.contrib.auth import get_user_model


@pytest.fixture
def logged_client(client, db):
    """The app is for a single user: every page needs a logged-in session."""
    user = get_user_model().objects.create_user(username="me", password="not-used")
    client.force_login(user)
    return client
