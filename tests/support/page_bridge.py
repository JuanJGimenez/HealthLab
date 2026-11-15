"""Load the app page in a real browser, wired to an ``Api`` without the app window.

The page talks to Python through ``window.pywebview.api``. In the app that object
is provided by the window; here a browser driven by Playwright gets an equivalent
one, so the page script runs exactly as it does in the app.
"""

from __future__ import annotations

from typing import Any

from misalud.interface.api import Api
from misalud.interface.window import WEB_DIR

BRIDGE_SCRIPT = """
window.pywebview = {api: {}};
for (const name of %s) {
  window.pywebview.api[name] = (...args) => window['misalud_' + name](...args);
}
"""


def api_methods(api: Api) -> list[str]:
    """Return the names of the methods the window exposes to the page."""
    return sorted(
        name for name in dir(api) if not name.startswith("_") and callable(getattr(api, name))
    )


def open_page(page: Any, api: Api) -> list[str]:
    """Load the app page in ``page`` and connect it to ``api``.

    Args:
        page: A Playwright page.
        api: The bridge the page will call.

    Returns:
        A list that collects page errors and console errors as they happen.
    """
    problems: list[str] = []
    page.on("pageerror", lambda error: problems.append(str(error)))
    page.on(
        "console",
        lambda message: problems.append(message.text) if message.type == "error" else None,
    )
    names = api_methods(api)
    for name in names:
        page.expose_function(f"misalud_{name}", getattr(api, name))
    page.add_init_script(BRIDGE_SCRIPT % names)
    page.goto((WEB_DIR / "index.html").as_uri())
    page.wait_for_function("document.querySelector('#foot').textContent !== ''")
    return problems
