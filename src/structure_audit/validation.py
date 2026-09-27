"""Small validator for the shipped JSON Schema subset, without a runtime dependency.

This is not a general JSON Schema implementation. Unknown schema keywords fail.
"""
import json
import math
import re
from pathlib import Path

_KEYS = {"$schema", "title", "description", "type", "required", "properties",
         "additionalProperties", "items", "enum", "minimum", "minLength", "pattern"}


def validate(value, schema, path="$"):
    unknown = set(schema) - _KEYS
    if unknown:
        raise ValueError(f"Unsupported schema keywords: {sorted(unknown)}")
    types = schema.get("type", [])
    types = [types] if isinstance(types, str) else types
    matches = {
        "null": value is None, "object": isinstance(value, dict),
        "array": isinstance(value, list), "string": isinstance(value, str),
        "boolean": type(value) is bool, "integer": type(value) is int,
        "number": type(value) in (int, float),
    }
    if types and not any(matches[t] for t in types):
        raise ValueError(f"{path}: expected {types}")
    if type(value) is float and not math.isfinite(value):
        raise ValueError(f"{path}: non-finite JSON number")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: invalid value {value!r}")
    if value is None:
        return
    if isinstance(value, dict):
        if any(not isinstance(k, str) for k in value):
            raise ValueError(f"{path}: JSON object keys must be strings")
        for key in schema.get("required", []):
            if key not in value:
                raise ValueError(f"{path}.{key}: missing required field")
        props = schema.get("properties", {})
        for key, item in value.items():
            extra = schema.get("additionalProperties", True)
            if key not in props and extra is False:
                raise ValueError(f"{path}.{key}: unexpected field")
            child = props.get(key, extra if isinstance(extra, dict) else {})
            validate(item, child, f"{path}.{key}")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            validate(item, schema.get("items", {}), f"{path}[{i}]")
    elif isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise ValueError(f"{path}: string too short")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            raise ValueError(f"{path}: invalid string")
    elif type(value) in (int, float) and "minimum" in schema:
        if value < schema["minimum"]:
            raise ValueError(f"{path}: below minimum")
    elif not isinstance(value, (bool, int, float)):
        raise ValueError(f"{path}: not a JSON value")


def validate_named(value, name):
    schema = json.loads((Path(__file__).parent / "schemas" / f"{name}.schema.json").read_text())
    validate(value, schema)


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    def invalid(token):
        raise ValueError(f"Non-finite JSON token: {token}")
    return json.loads(Path(path).read_text(), object_pairs_hook=pairs, parse_constant=invalid)
