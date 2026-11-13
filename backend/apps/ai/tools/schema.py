"""Generate a JSON Schema (for Grok's ``tools`` parameter) from a DRF serializer."""
from rest_framework import serializers


def _number(value):
    return float(value) if value is not None else None


def field_schema(field) -> dict:
    if isinstance(field, serializers.ListSerializer):
        schema = {"type": "array", "items": serializer_schema(field.child)}
        if getattr(field, "min_length", None) is not None:
            schema["minItems"] = field.min_length
        if getattr(field, "max_length", None) is not None:
            schema["maxItems"] = field.max_length
    elif isinstance(field, serializers.Serializer):
        schema = serializer_schema(field)
    elif isinstance(field, serializers.ListField):
        schema = {"type": "array", "items": field_schema(field.child)}
        if field.min_length is not None:
            schema["minItems"] = field.min_length
        if field.max_length is not None:
            schema["maxItems"] = field.max_length
    elif isinstance(field, serializers.BooleanField):
        schema = {"type": "boolean"}
    elif isinstance(field, serializers.ChoiceField):
        schema = {"type": "string", "enum": [str(k) for k in field.choices]}
    elif isinstance(field, serializers.IntegerField):
        schema = {"type": "integer"}
        if field.min_value is not None:
            schema["minimum"] = int(field.min_value)
        if field.max_value is not None:
            schema["maximum"] = int(field.max_value)
    elif isinstance(field, (serializers.DecimalField, serializers.FloatField)):
        schema = {"type": "number"}
        if field.min_value is not None:
            schema["minimum"] = _number(field.min_value)
        if field.max_value is not None:
            schema["maximum"] = _number(field.max_value)
    elif isinstance(field, serializers.DateTimeField):
        schema = {"type": "string", "format": "date-time"}
    elif isinstance(field, serializers.DateField):
        schema = {"type": "string", "format": "date", "description": "ISO date, YYYY-MM-DD"}
    elif isinstance(field, serializers.CharField):
        schema = {"type": "string"}
        if field.max_length is not None:
            schema["maxLength"] = field.max_length
        if field.min_length is not None:
            schema["minLength"] = field.min_length
    else:
        raise TypeError(f"No JSON Schema mapping for {type(field).__name__}; add one or pass json_schema=")

    help_text = getattr(field, "help_text", None)
    if help_text:
        existing = schema.get("description")
        schema["description"] = f"{help_text} ({existing})" if existing else str(help_text)
    default = getattr(field, "default", serializers.empty)
    if default is not serializers.empty and not callable(default) and default is not None:
        schema["default"] = default
    return schema


def serializer_schema(serializer) -> dict:
    if isinstance(serializer, type):
        serializer = serializer()
    properties, required = {}, []
    for name, field in serializer.fields.items():
        if field.read_only:
            continue
        properties[name] = field_schema(field)
        if field.required:
            required.append(name)
    schema = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema
