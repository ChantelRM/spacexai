"""Test doubles for Grok. Tests must never reach the real xAI API."""
import itertools
import json

from apps.ai.client import ModelTurn, ToolCall

_ids = itertools.count(1)


def tool_turn(name, text="", **arguments) -> ModelTurn:
    return ModelTurn(text=text, tool_calls=[ToolCall(call_id=f"call_{next(_ids)}", name=name,
                                                     arguments=json.dumps(arguments))])


def text_turn(text) -> ModelTurn:
    return ModelTurn(text=text)


class FakeGrok:
    """
    Scripted stand-in for ``apps.ai.client.create_response``.

    ``turns`` is a list of ModelTurn (or exceptions to raise). Each call
    records its kwargs so tests can inspect the tools/prompt sent.
    If ``repeat_last`` is True the final turn is returned forever.
    """

    def __init__(self, *turns, repeat_last=False):
        self.turns = list(turns)
        self.calls = []
        self.repeat_last = repeat_last

    def __call__(self, *, instructions, input_items, tools):
        self.calls.append({"instructions": instructions, "input_items": list(input_items), "tools": tools})
        if self.repeat_last and len(self.turns) == 1:
            turn = self.turns[0]
        else:
            turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        return turn

    def tool_names(self, call_index=0):
        return sorted(t["name"] for t in self.calls[call_index]["tools"])


def coordinate_fragments(location) -> list[str]:
    """Short text fragments of a location's coordinates, to catch leaks in any number format."""
    if location.latitude is None:
        return []
    return [f"{abs(float(location.latitude)):.4f}", f"{abs(float(location.longitude)):.4f}"]
