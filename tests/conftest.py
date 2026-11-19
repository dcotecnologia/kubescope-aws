"""Fixtures of the tests of the AWS extension."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from kubescope.sdk import AwsScope


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Never read or write the real user settings during tests."""
    monkeypatch.setenv("KUBESCOPE_CONFIG_DIR", str(tmp_path / "config"))
    home = tmp_path / "isolated-home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))


@pytest.fixture(autouse=True)
def light_theme():
    from kubescope import theme

    theme.set_theme("light")
    yield
    theme.set_theme("light")


@pytest.fixture(autouse=True)
def no_blocking_dialogs(monkeypatch):
    """A modal dialog nobody can answer would hang the run; fail fast instead."""
    from PySide6.QtWidgets import QDialog, QMenu, QMessageBox

    def refuse(*_args, **_kwargs):
        running = os.environ.get("PYTEST_CURRENT_TEST", "no test")
        raise AssertionError(f"a test opened a real modal dialog ({running})")

    monkeypatch.setattr(QDialog, "exec", refuse)
    monkeypatch.setattr(QMessageBox, "exec", refuse)
    monkeypatch.setattr(QMenu, "exec", refuse)


class FakeAws:
    """`ctx.aws`: answers what the test says for a command, and remembers what
    was asked."""

    def __init__(self) -> None:
        self.answers: dict[tuple[str, ...], object] = {}
        self.asked: list[tuple[str, list[str], str]] = []
        self.using = True
        self.scope_of = AwsScope("us-east-1", "work", "123456789012")

    def uses_aws(self, context):
        return self.using

    def scope(self, context):
        return self.scope_of

    def regions(self):
        return ("us-east-1", "sa-east-1")

    def run(self, context, command, region=""):
        self.asked.append((context, list(command), region))
        answer = self.answers.get(tuple(command[:2]), {})
        if isinstance(answer, Exception):
            raise answer
        return answer


class FakeUi:
    """`ctx.ui`: runs an action at once and remembers what was shown."""

    def __init__(self) -> None:
        self.window = None
        self.messages: list[tuple[str, str, str]] = []
        self.jsons: list[tuple[str, dict]] = []
        self.logs: list[tuple[str, str, str]] = []
        self.picked: tuple[str, bool] = ("", False)
        self.picks: list[list[str]] = []

    def themed(self, color, text=False):
        return color

    def show_message(self, icon, title, text):
        self.messages.append((icon, title, text))

    def run_action(self, function, on_success, *arguments, on_error=None, quiet=False):
        try:
            answer = function(*arguments)
        except Exception as error:
            if on_error is None:
                raise
            on_error(str(error))
            return
        on_success(answer)

    def pick_item(self, title, label, items):
        self.picks.append(items)
        return self.picked

    def show_json(self, title, document):
        self.jsons.append((title, document))

    def open_log(self, title, name, read):
        self.logs.append((title, name, read()))


class FakeForwards:
    def __init__(self) -> None:
        self.started: list[tuple] = []
        self.failure: Exception | None = None
        self.accepted = True

    def port_in_use(self, port):
        return False

    def start_ssm(self, context, title, command, local, target):
        if self.failure is not None:
            raise self.failure
        self.started.append((context, title, command, local, target))
        return self.accepted


class FakeEvents:
    def __init__(self) -> None:
        self.handlers: dict[str, list] = {}

    def on(self, event, handler):
        self.handlers.setdefault(event, []).append(handler)
        return lambda: None


class FakeCtx:
    """What the app gives the extension, in the hands of the test."""

    id = "kubescope.aws"
    permissions = frozenset({"aws.read", "forward", "ui.page", "ui.window"})

    def __init__(self) -> None:
        self.aws = FakeAws()
        self.ui = FakeUi()
        self.forwards = FakeForwards()
        self.events = FakeEvents()
        self.current_context: str | None = (
            "arn:aws:eks:us-east-1:123456789012:cluster/x"
        )
        self.pages: list[dict] = []

        class App:
            write_mode = True

        self.app = App()

    def add_page(
        self, section, group, title, factory, subtitle="", visible=None, refresh=None
    ):
        self.pages.append(
            {
                "section": section,
                "group": group,
                "title": title,
                "factory": factory,
                "subtitle": subtitle,
                "visible": visible,
                "refresh": refresh,
            }
        )


@pytest.fixture
def ctx():
    return FakeCtx()


DATABASE = {
    "DBInstanceIdentifier": "orders",
    "Engine": "postgres",
    "EngineVersion": "15.4",
    "DBInstanceClass": "db.t3.micro",
    "DBInstanceStatus": "available",
    "AllocatedStorage": 20,
    "MultiAZ": True,
    "Endpoint": {"Address": "orders.example.com", "Port": 5432},
    "DBSubnetGroup": {"VpcId": "vpc-1"},
}
