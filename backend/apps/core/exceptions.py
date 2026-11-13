"""
Consistent error format for every API error:

    {"error": {"code": "validation_error",
               "message": "Human-readable summary",
               "details": {"field": ["..."]}}}
"""
import logging

from django.conf import settings
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)

_CODES = [
    (exceptions.ValidationError, "validation_error"),
    (exceptions.NotAuthenticated, "not_authenticated"),
    (exceptions.AuthenticationFailed, "authentication_failed"),
    (exceptions.PermissionDenied, "permission_denied"),
    (exceptions.NotFound, "not_found"),
    (exceptions.MethodNotAllowed, "method_not_allowed"),
    (exceptions.Throttled, "throttled"),
    (exceptions.ParseError, "parse_error"),
    (exceptions.UnsupportedMediaType, "unsupported_media_type"),
    (exceptions.NotAcceptable, "not_acceptable"),
]


def _error_code(exc) -> str:
    for exc_class, code in _CODES:
        if isinstance(exc, exc_class):
            return code
    return getattr(exc, "default_code", None) or "error"


def _first_message(detail):
    if isinstance(detail, dict):
        for value in detail.values():
            msg = _first_message(value)
            if msg:
                return msg
    elif isinstance(detail, (list, tuple)):
        for value in detail:
            msg = _first_message(value)
            if msg:
                return msg
    elif detail:
        return str(detail)
    return None


def build_error(code: str, message: str, details=None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def api_exception_handler(exc, context):
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    response = drf_exception_handler(exc, context)

    if response is None:
        # Unhandled error: log server-side (secrets are redacted by the logging
        # filter) and return a generic message. Never echo exception text.
        if settings.DEBUG:
            return None
        logger.exception("Unhandled API error")
        return Response(
            build_error("server_error", "Something went wrong on our side. Please try again."),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    code = _error_code(exc)
    detail = getattr(exc, "detail", None)
    details = {}

    if isinstance(exc, exceptions.ValidationError):
        details = {"non_field_errors": detail} if isinstance(detail, list) else detail
        if isinstance(detail, dict) and len(detail) > 1:
            message = "Some of the submitted data is invalid."
        else:
            message = _first_message(detail) or "Some of the submitted data is invalid."
    elif isinstance(detail, dict):
        # e.g. simplejwt: {"detail": "...", "code": "token_not_valid", "messages": [...]}
        message = str(detail.get("detail") or _first_message(detail) or "Request failed.")
        if detail.get("code"):
            code = str(detail["code"])
    else:
        message = _first_message(detail) or "Request failed."

    if isinstance(exc, exceptions.Throttled) and exc.wait is not None:
        details = {"retry_after_seconds": int(exc.wait)}

    response.data = build_error(code, message, details)
    return response
