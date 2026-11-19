"""Compare what ``Api`` really answers with the shape it declares.

Each ``Api`` method declares its answer as a ``TypedDict``. The type checker
compares that declaration with the code; the helpers here compare it with the
real answers, at any depth, while the tests run. ``checked`` makes an ``Api``
verify every answer it gives, so every interface test is also a contract test.
"""

from __future__ import annotations

import functools
import types
from typing import Any, Union, get_args, get_origin, get_type_hints, is_typeddict

from healthlab.interface.api import Api


class ContractError(AssertionError):
    """An answer does not have the shape its method declares."""


def public_methods(api: Api) -> list[str]:
    """Return the names of the methods the window exposes to the page."""
    return sorted(
        name for name in dir(api) if not name.startswith("_") and callable(getattr(api, name))
    )


def declared_answer(name: str) -> Any:
    """Return the answer type a method of ``Api`` declares."""
    method = getattr(Api, name)
    return get_type_hints(method.__wrapped__)["return"]


def _typed_dict_problems(value: Any, declared: Any, path: str) -> list[str]:
    """Compare a dictionary with a ``TypedDict``: its keys, then each value."""
    if not isinstance(value, dict):
        return [f"{path}: expected {declared.__name__}, got {type(value).__name__}"]
    problems = [f"{path}.{key}: missing" for key in sorted(declared.__required_keys__ - set(value))]
    known = declared.__required_keys__ | declared.__optional_keys__
    problems += [f"{path}.{key}: not declared" for key in sorted(set(value) - known)]
    hints = get_type_hints(declared)
    for key in sorted(set(value) & known):
        problems += problems_in(value[key], hints[key], f"{path}.{key}")
    return problems


def _container_problems(value: Any, declared: Any, path: str) -> list[str]:
    """Compare a list or a dictionary with ``list[T]`` or ``dict[str, T]``."""
    origin, arguments = get_origin(declared), get_args(declared)
    if not isinstance(value, origin):
        return [f"{path}: expected {origin.__name__}, got {type(value).__name__}"]
    if origin is list:
        items = [(f"{path}[{index}]", item, arguments[0]) for index, item in enumerate(value)]
    else:
        items = [(f"{path}.{key}", item, arguments[1]) for key, item in value.items()]
    return [problem for where, item, kind in items for problem in problems_in(item, kind, where)]


def problems_in(value: Any, declared: Any, path: str = "answer") -> list[str]:
    """List every way a value differs from a declared type.

    Args:
        value: Plain data: dictionaries, lists, texts, numbers, booleans, ``None``.
        declared: A ``TypedDict``, ``list[T]``, ``dict[str, T]``, a union, a
            plain type, ``Any`` or ``object``.
        path: Where the value sits in the answer, for the messages.

    Returns:
        One message per difference; empty when the value fits.
    """
    if declared is Any or declared is object:
        return []
    if is_typeddict(declared):
        return _typed_dict_problems(value, declared, path)
    origin = get_origin(declared)
    if origin in (Union, types.UnionType):
        options = [problems_in(value, option, path) for option in get_args(declared)]
        return [] if any(not found for found in options) else min(options, key=len)
    if origin in (list, dict):
        return _container_problems(value, declared, path)
    if declared is type(None):
        fits = value is None
    elif declared is float:
        fits = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif declared is int:
        fits = isinstance(value, int) and not isinstance(value, bool)
    else:
        fits = isinstance(value, declared)
    return [] if fits else [f"{path}: expected {declared.__name__}, got {value!r}"]


def answer_problems(name: str, answer: dict[str, Any]) -> list[str]:
    """List how an answer of a method differs from what the method declares."""
    if answer.get("ok") is not True:
        return [] if set(answer) == {"ok", "error"} else [f"{name}: malformed failure {answer}"]
    payload = {key: value for key, value in answer.items() if key != "ok"}
    return problems_in(payload, declared_answer(name), name)


def checked(api: Api) -> Api:
    """Make an ``Api`` verify the shape of every answer it gives.

    Args:
        api: The bridge to watch.

    Returns:
        The same object; each public method now raises ``ContractError`` when
        its answer does not match its declared shape.
    """
    for name in public_methods(api):
        method = getattr(api, name)

        @functools.wraps(method)
        def verified(*args: Any, _name: str = name, _method: Any = method) -> Any:
            answer = _method(*args)
            problems = answer_problems(_name, answer)
            if problems:
                raise ContractError("; ".join(problems))
            return answer

        setattr(api, name, verified)
    return api
