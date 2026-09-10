"""The frontend recognizes the exact immutable console profile on every OS."""

from app.console_profile import current_console_profile


def test_console_profile_matches_the_published_frontend_contract():
    # A checkout newline conversion must not create an unsupported profile.
    # A deliberate profile revision requires a new version and frontend support.
    assert current_console_profile() == {
        "id": "mission-console",
        "version": 1,
        "sha256": "55df7b7b1ea4b48cbc6c0a70412bc01c3e8436a26a8c6968676d76c3df7314b9",
    }
