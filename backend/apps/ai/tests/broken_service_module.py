"""Used by test_resolve_service: an existing module whose own import is broken."""
import a_dependency_that_is_not_installed  # noqa: F401


def find_equipment(user, **kwargs):
    return {}
