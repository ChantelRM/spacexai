"""
Tool registry: the ONLY way Grok can affect anything.

Declare a tool once:

    @register_tool(
        name="find_nearby_farmers",
        description="Find farmers near the current user...",
        input_serializer=FindNearbyFarmersInput,
        allowed_roles={"FARMER", "WHOLESALE_BUYER"},
        requires_confirmation=False,
    )
    def find_nearby_farmers(user, data):
        return call_service("find_nearby_farmers", user, data)

For every call the registry re-checks the user and role, validates the
arguments with the serializer, runs the tool as the requesting user, scrubs
private fields from the result and writes an AIActionLog row.

Tools with ``requires_confirmation=True`` never run from a Grok call. They
create a PendingAction that only the user can confirm through the API.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from importlib import import_module
from typing import Any, Callable

from django.conf import settings
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone
from rest_framework import exceptions as drf_exceptions

from apps.accounts.models import Role

from ..exceptions import ActionExpired, ActionNotPending
from ..models import AIActionLog, AIMessage, PendingAction
from ..services_contract import NOT_AVAILABLE, SERVICE_PROVIDERS
from .privacy import scrub_private_fields
from .schema import serializer_schema

logger = logging.getLogger(__name__)

MAX_LOGGED_ARG_CHARS = 4000


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_serializer: type
    allowed_roles: frozenset
    requires_confirmation: bool
    func: Callable[[Any, dict], dict]
    summarize: Callable[[dict], str] | None = None
    service: str | None = None  # SERVICE_PROVIDERS key this tool depends on
    json_schema: dict | None = None

    def parameters_schema(self) -> dict:
        return self.json_schema or serializer_schema(self.input_serializer)

    def as_grok_tool(self) -> dict:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters_schema(),
        }

    def is_available(self) -> bool:
        return self.service is None or resolve_service(self.service) is not None


REGISTRY: dict[str, ToolSpec] = {}


def register_tool(*, name, description, input_serializer, allowed_roles, requires_confirmation=False,
                  summarize=None, service=None, json_schema=None, replace=False):
    roles = frozenset(allowed_roles)
    if not roles or not roles <= set(Role.values):
        raise ValueError(f"Tool {name!r}: allowed_roles must be a non-empty subset of {Role.values}")
    if requires_confirmation and summarize is None:
        raise ValueError(f"Tool {name!r}: confirmation tools need a summarize(data) -> str function")

    def decorator(func):
        if name in REGISTRY and not replace:
            raise ValueError(f"Tool {name!r} is already registered (pass replace=True to override)")
        REGISTRY[name] = ToolSpec(
            name=name, description=description, input_serializer=input_serializer, allowed_roles=roles,
            requires_confirmation=requires_confirmation, func=func, summarize=summarize,
            service=service, json_schema=json_schema,
        )
        return func

    return decorator


def get_tool(name: str) -> ToolSpec | None:
    return REGISTRY.get(name)


def user_can_use(user, spec: ToolSpec) -> bool:
    return bool(
        user is not None and user.is_authenticated and user.is_active
        and getattr(user, "role", None) in spec.allowed_roles
    )


def tools_for_user(user) -> list[ToolSpec]:
    return [spec for spec in REGISTRY.values() if user_can_use(user, spec)]


def grok_tools_for_user(user) -> list[dict]:
    """The ``tools`` parameter for Grok: only what this user's role may use."""
    return [spec.as_grok_tool() for spec in tools_for_user(user)]


# --- Service resolution ------------------------------------------------------------

def _provider_path(service_name: str) -> str | None:
    overrides = getattr(settings, "AI_SERVICE_PROVIDERS", {}) or {}
    return overrides.get(service_name, SERVICE_PROVIDERS.get(service_name))


def resolve_service(service_name: str):
    """Return the service callable, or None if its module/function doesn't exist yet."""
    path = _provider_path(service_name)
    if not path:
        return None
    module_path, func_name = path.rsplit(".", 1)
    try:
        module = import_module(module_path)
    except ModuleNotFoundError as exc:
        # Only "the module isn't written yet" counts as unavailable. A missing
        # import *inside* an existing module is a real bug and must surface.
        if exc.name and (module_path == exc.name or module_path.startswith(exc.name + ".")):
            return None
        raise
    return getattr(module, func_name, None)


def call_service(service_name: str, user, data: dict) -> dict:
    """Call a feature service with validated data, or report it's not built yet."""
    func = resolve_service(service_name)
    if func is None:
        return dict(NOT_AVAILABLE)
    return func(user, **_plain(data))


def _plain(value):
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


# --- Execution ------------------------------------------------------------------------

@dataclass
class ToolOutcome:
    name: str
    status: str  # an AIActionLog.Status value
    result: dict  # what Grok sees (already scrubbed)
    pending_action: PendingAction | None = None
    data: dict | None = field(default=None)  # what the app may render (successful results only)


def _json_safe(value):
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def _loggable_args(args) -> dict:
    if isinstance(args, dict):
        text = json.dumps(args, cls=DjangoJSONEncoder)
        if len(text) <= MAX_LOGGED_ARG_CHARS:
            return _json_safe(args)
        return {"_truncated": text[:MAX_LOGGED_ARG_CHARS]}
    return {"_raw": str(args)[:MAX_LOGGED_ARG_CHARS]}


def summarize_result(result) -> str:
    if not isinstance(result, dict):
        return str(result)[:300]
    if result.get("available") is False:
        return "Feature not available yet"
    if "error" in result:
        return f"{result['error']}: {result.get('message', '')}"[:300]
    if isinstance(result.get("results"), list):
        return f"{len(result['results'])} result(s)"
    return json.dumps(result, cls=DjangoJSONEncoder)[:300]


def _log(user, conversation, spec_name, arguments, status, summary="", requires_confirmation=False, executed=False):
    return AIActionLog.objects.create(
        user=user,
        conversation=conversation,
        tool_name=spec_name[:64],
        arguments=_loggable_args(arguments),
        result_summary=summary[:1000],
        status=status,
        requires_confirmation=requires_confirmation,
        executed_at=timezone.now() if executed else None,
    )


def _parse_arguments(raw):
    if isinstance(raw, dict):
        return raw, None
    if raw in (None, ""):
        return {}, None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return raw, "Arguments must be valid JSON."
    if not isinstance(parsed, dict):
        return parsed, "Arguments must be a JSON object."
    return parsed, None


def execute_tool_call(user, name: str, raw_arguments, conversation=None) -> ToolOutcome:
    """Run one tool call requested by Grok, as ``user``. Never raises for tool problems."""
    S = AIActionLog.Status
    args, parse_error = _parse_arguments(raw_arguments)
    spec = get_tool(name)

    if spec is None:
        _log(user, conversation, name or "?", args, S.INVALID, "Unknown tool")
        return ToolOutcome(name, S.INVALID, {"error": "unknown_tool", "message": f"There is no tool called {name!r}."})

    if not user_can_use(user, spec):
        _log(user, conversation, name, args, S.DENIED, "Role not allowed", spec.requires_confirmation)
        return ToolOutcome(name, S.DENIED, {
            "error": "permission_denied",
            "message": "This user's account type is not allowed to use this tool.",
        })

    if parse_error:
        _log(user, conversation, name, args, S.INVALID, parse_error, spec.requires_confirmation)
        return ToolOutcome(name, S.INVALID, {"error": "invalid_arguments", "details": {"non_field_errors": [parse_error]}})

    serializer = spec.input_serializer(data=args, context={"user": user})
    if not serializer.is_valid():
        errors = _json_safe(serializer.errors)
        _log(user, conversation, name, args, S.INVALID, json.dumps(errors)[:1000], spec.requires_confirmation)
        return ToolOutcome(name, S.INVALID, {"error": "invalid_arguments", "details": errors})
    data = serializer.validated_data

    if spec.requires_confirmation:
        if not spec.is_available():
            _log(user, conversation, name, args, S.SUCCESS, "Feature not available yet", True, executed=True)
            return ToolOutcome(name, S.SUCCESS, dict(NOT_AVAILABLE), data=dict(NOT_AVAILABLE))
        pending = PendingAction.objects.create(
            user=user,
            conversation=conversation,
            tool_name=name,
            arguments=_json_safe(serializer.data),
            summary=spec.summarize(data),
        )
        _log(user, conversation, name, args, S.PENDING_CONFIRMATION, pending.summary, True)
        return ToolOutcome(
            name,
            S.PENDING_CONFIRMATION,
            {
                "status": "confirmation_required",
                "summary": pending.summary,
                "expires_at": pending.expires_at.isoformat(),
                "message": (
                    "Nothing has been done yet. The app is showing the user a confirmation "
                    "card. Ask them to review it and tap Confirm if it is correct."
                ),
            },
            pending_action=pending,
        )

    return _run(spec, user, data, args, conversation, success_status=S.SUCCESS)


def _run(spec, user, data, log_args, conversation, success_status) -> ToolOutcome:
    S = AIActionLog.Status
    try:
        raw_result = spec.func(user, data)
    except (DjangoPermissionDenied, drf_exceptions.PermissionDenied):
        _log(user, conversation, spec.name, log_args, S.DENIED, "Permission denied by service", spec.requires_confirmation)
        return ToolOutcome(spec.name, S.DENIED, {"error": "permission_denied", "message": "The user is not allowed to do that."})
    except drf_exceptions.ValidationError as exc:
        errors = _json_safe(exc.detail)
        _log(user, conversation, spec.name, log_args, S.INVALID, json.dumps(errors)[:1000], spec.requires_confirmation)
        return ToolOutcome(spec.name, S.INVALID, {"error": "invalid_arguments", "details": errors})
    except Exception:  # noqa: BLE001
        logger.exception("AI tool %s failed", spec.name)
        _log(user, conversation, spec.name, log_args, S.ERROR, "Tool raised an exception", spec.requires_confirmation)
        return ToolOutcome(spec.name, S.ERROR, {
            "error": "tool_failed",
            "message": "This tool failed unexpectedly. Tell the user something went wrong and to try again later.",
        })

    result = _json_safe(scrub_private_fields(raw_result if isinstance(raw_result, dict) else {"result": raw_result}))
    _log(user, conversation, spec.name, log_args, success_status, summarize_result(result),
         spec.requires_confirmation, executed=True)
    return ToolOutcome(spec.name, success_status, result, data=result)


# --- Confirmation flow (called from the API only; Grok has no path here) -----------

def _get_owned_pending(user, action_id) -> PendingAction:
    action = PendingAction.objects.filter(pk=action_id, user=user).first()
    if action is None:
        raise drf_exceptions.NotFound("Action not found.")
    return action


def _expire(action: PendingAction):
    updated = PendingAction.objects.filter(pk=action.pk, status=PendingAction.Status.PENDING).update(
        status=PendingAction.Status.EXPIRED
    )
    if updated:
        _log(action.user, action.conversation, action.tool_name, action.arguments,
             AIActionLog.Status.EXPIRED, action.summary, True)


def confirm_pending_action(user, action_id) -> dict:
    """Execute a PendingAction once, on the owner's explicit confirmation."""
    P = PendingAction.Status
    action = _get_owned_pending(user, action_id)
    if action.status == P.EXPIRED:
        raise ActionExpired()
    if action.status != P.PENDING:
        raise ActionNotPending()
    if action.is_expired:
        _expire(action)
        raise ActionExpired()

    # Atomic claim: only one request can move PENDING -> EXECUTING.
    with transaction.atomic():
        claimed = PendingAction.objects.filter(pk=action.pk, status=P.PENDING).update(status=P.EXECUTING)
    if not claimed:
        raise ActionNotPending()

    def fail(status_code_exc, log_status, summary):
        PendingAction.objects.filter(pk=action.pk).update(status=P.FAILED)
        _log(user, action.conversation, action.tool_name, action.arguments, log_status, summary, True)
        raise status_code_exc

    spec = get_tool(action.tool_name)
    if spec is None:
        fail(drf_exceptions.ValidationError("This action can no longer be performed."),
             AIActionLog.Status.INVALID, "Tool no longer registered")
    if not user_can_use(user, spec):
        fail(drf_exceptions.PermissionDenied("Your account type cannot perform this action."),
             AIActionLog.Status.DENIED, "Role not allowed at confirmation")
    serializer = spec.input_serializer(data=action.arguments, context={"user": user})
    if not serializer.is_valid():
        fail(drf_exceptions.ValidationError(serializer.errors), AIActionLog.Status.INVALID,
             "Arguments failed re-validation")

    outcome = _run(spec, user, serializer.validated_data, action.arguments, action.conversation,
                   success_status=AIActionLog.Status.CONFIRMED)
    if outcome.status != AIActionLog.Status.CONFIRMED:
        PendingAction.objects.filter(pk=action.pk).update(status=P.FAILED, result=outcome.result)
        if outcome.status == AIActionLog.Status.DENIED:
            raise drf_exceptions.PermissionDenied(outcome.result.get("message"))
        if outcome.status == AIActionLog.Status.INVALID:
            raise drf_exceptions.ValidationError(outcome.result.get("details"))
        raise drf_exceptions.APIException("The action failed. Nothing was saved. Please try again later.")

    now = timezone.now()
    PendingAction.objects.filter(pk=action.pk).update(status=P.CONFIRMED, executed_at=now, result=outcome.result)
    if action.conversation_id:
        AIMessage.objects.create(conversation=action.conversation, role=AIMessage.Role.ASSISTANT,
                                 content=f"Confirmed by the user and done: {action.summary}")
    action.refresh_from_db()
    return {"id": str(action.id), "status": action.status, "tool_name": action.tool_name,
            "summary": action.summary, "executed_at": action.executed_at, "result": outcome.result}


def cancel_pending_action(user, action_id) -> dict:
    P = PendingAction.Status
    action = _get_owned_pending(user, action_id)
    if action.status == P.EXPIRED:
        raise ActionExpired()
    if action.status != P.PENDING:
        raise ActionNotPending()
    if action.is_expired:
        _expire(action)
        raise ActionExpired()
    if not PendingAction.objects.filter(pk=action.pk, status=P.PENDING).update(status=P.CANCELLED):
        raise ActionNotPending()
    _log(user, action.conversation, action.tool_name, action.arguments, AIActionLog.Status.CANCELLED,
         action.summary, True)
    if action.conversation_id:
        AIMessage.objects.create(conversation=action.conversation, role=AIMessage.Role.ASSISTANT,
                                 content=f"Cancelled by the user, nothing was done: {action.summary}")
    action.refresh_from_db()
    return {"id": str(action.id), "status": action.status, "tool_name": action.tool_name,
            "summary": action.summary, "executed_at": None, "result": None}
