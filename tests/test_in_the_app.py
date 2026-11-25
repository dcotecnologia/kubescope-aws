"""The extension in the window of the app, with the real services lent to
it."""

import time

import pytest
from kubescope.extensions import testing
from kubescope.extensions.context import ExtensionContext

from kubescope.aws import activate
from tests.conftest import DATABASE


@pytest.fixture
def window(monkeypatch):
    from kubescope import window as window_module

    application = testing.application()
    # the window downloads the extensions the app recommends on its first run
    monkeypatch.setattr("kubescope.extensions.defaults.DEFAULTS", ())
    monkeypatch.setattr(window_module, "list_contexts", lambda: ([], None))
    monkeypatch.setattr(
        window_module.WorkloadWindow, "refresh_overview", lambda *_a: None
    )
    shown = window_module.WorkloadWindow()
    deadline = time.monotonic() + 3
    while shown._action_workers and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.005)
    yield shown
    shown.close()


def entries(window) -> list:
    return [
        one
        for one in testing.find_all(window.ui.sidebarNav, "button")
        if one.text() == "Instances"
    ]


def test_the_page_is_in_the_menu_and_lists_the_instances(window, monkeypatch) -> None:
    from kubescope import cluster

    monkeypatch.setattr(cluster, "_aws_scope", lambda ctx: ("us-east-1", "w", "1"))
    monkeypatch.setattr(cluster, "is_eks_context", lambda context: True)
    monkeypatch.setattr(
        cluster,
        "_aws_json",
        lambda context, command, region: {"DBInstances": [DATABASE]},
    )
    window.context_combo.blockSignals(True)
    window.context_combo.addItem("prod")
    window.context_combo.setCurrentIndex(0)
    window.context_combo.blockSignals(False)
    context = ExtensionContext(
        "kubescope.aws",
        frozenset({"aws.read", "forward", "ui.page", "ui.window"}),
        window.extension_host,
    )

    activate(context)
    window._apply_extension_contributions()
    entry = entries(window)[-1]
    entry.click()
    deadline = time.monotonic() + 3
    widget = window.pages.currentWidget().layout().itemAt(0).widget()
    table = testing.find(widget, "table")
    while table.rowCount() == 0 and time.monotonic() < deadline:
        testing.settle()
        time.sleep(0.005)

    assert window.ui.pageTitle.text() == "Instances"
    assert table.rowCount() == 1
    assert table.item(0, 0).text() == "orders"
    context.close()
