from rest_framework import status
from rest_framework.exceptions import APIException


class AIServiceUnavailable(APIException):
    """Grok/xAI could not be reached or refused the request. Maps to HTTP 503."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = "ai_service_unavailable"
    default_detail = "The AI assistant is temporarily unavailable. Please try again shortly."


class ActionExpired(APIException):
    status_code = status.HTTP_410_GONE
    default_code = "action_expired"
    default_detail = "This action has expired. Ask the assistant again to get a new one."


class ActionNotPending(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "action_not_pending"
    default_detail = "This action has already been confirmed, cancelled or has expired."
