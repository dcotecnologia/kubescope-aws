import re

import pytest
from kubescope.extensions import testing
from kubescope.extensions.components import UiComponents
from kubescope.sdk import CONTEXT_CHANGED, WriteModeOff
from kubescope.sdk.errors import ClusterError
from kubescope.sdk.models import RdsInstance

from kubescope.aws import extension
from kubescope.aws.rds_page import RdsPage, compile_query
from tests.conftest import DATABASE

application = testing.application()


@pytest.fixture
def page(ctx):
    ctx.aws.answers[("rds", "describe-db-instances")] = {
        "DBInstances": [
            DATABASE,
            {
                **DATABASE,
                "DBInstanceIdentifier": "billing",
                "Engine": "mysql",
                "DBInstanceStatus": "failed",
            },
        ]
    }
    shown = RdsPage(ctx)
    yield shown
    shown.widget.deleteLater()


def rows(page: RdsPage) -> list[str]:
    table = page.table
    names = []
    for row in range(table.rowCount()):
        item = table.item(row, 0)
        assert item is not None
        if not table.isRowHidden(row):
            names.append(item.text())
    return names


def instance(**changes) -> RdsInstance:
    values = dict(
        account="1", region="us-east-1", identifier="orders", engine="postgres",
        version="15", size="db.t3", status="available", storage=20, multi_az=False,
        endpoint="orders.example.com", port=5432, profile="work", vpc="vpc-1",
    )  # fmt: skip
    return RdsInstance(**{**values, **changes})


def test_the_extension_adds_one_page_to_the_aws_part_of_the_menu(ctx) -> None:
    extension.activate(ctx)  # type: ignore[arg-type]

    [added] = ctx.pages
    assert (added["section"], added["group"], added["title"]) == (
        "AWS",
        "RDS",
        "Instances",
    )
    assert added["factory"]() is not None  # the widget of the page
    ctx.aws.answers[("rds", "describe-db-instances")] = {"DBInstances": [DATABASE]}
    added["refresh"]()  # the refresh button of the header asks again
    assert ctx.aws.asked[-1][1] == ["rds", "describe-db-instances"]
    assert added["visible"]() is True
    ctx.aws.using = False
    assert added["visible"]() is False


def test_the_instances_are_listed_when_the_page_is_opened(page) -> None:
    page.shown()

    assert rows(page) == ["billing", "orders"]
    assert page.notice.text() == "2 instances"
    assert page.region.currentData() == "us-east-1"
    assert page.ctx.aws.asked[-1][2] == "us-east-1"
    status = page.table.item(0, 4)
    assert testing.badge_of(status) is not None  # the badge


def test_the_page_does_not_ask_again_for_the_same_context(page) -> None:
    page.shown()
    page.shown()

    assert len(page.ctx.aws.asked) == 1


def test_another_context_asks_again_with_its_own_region(page, ctx) -> None:
    page.shown()
    ctx.aws.scope_of = ctx.aws.scope_of._replace(region="sa-east-1")
    ctx.current_context = "other"
    page.shown()

    assert page.region.currentData() == "sa-east-1"
    assert len(ctx.aws.asked) == 2 and ctx.aws.asked[-1][2] == "sa-east-1"


def test_a_region_the_list_does_not_know_is_added(page, ctx) -> None:
    ctx.aws.scope_of = ctx.aws.scope_of._replace(region="mars-north-1")

    page.shown()

    assert page.region.currentData() == "mars-north-1"


def test_a_context_that_is_not_eks_keeps_the_region_that_was_chosen(page, ctx) -> None:
    def refuse(context):
        raise ClusterError("not eks")

    ctx.aws.scope = refuse

    page.shown()

    assert page.region.currentData() == "us-east-1"


def test_choosing_another_region_asks_again(page) -> None:
    page.shown()

    page.region.setCurrentIndex(page.region.findData("sa-east-1"))

    assert page.ctx.aws.asked[-1][2] == "sa-east-1"


def test_without_a_context_it_says_so(page, ctx) -> None:
    ctx.current_context = None

    page.shown()

    assert page.notice.text() == "Select a context."
    assert ctx.aws.asked == []


def test_the_context_changing_makes_the_page_ask_again_when_it_is_shown(
    page, ctx
) -> None:
    page.shown()
    handler = ctx.events.handlers[CONTEXT_CHANGED][0]

    handler(context="other")

    assert page.instances is None  # not visible: it asks when it is shown


def test_an_error_shows_in_the_banner_with_its_details(page, ctx) -> None:
    ctx.aws.answers[("rds", "describe-db-instances")] = ClusterError(
        "Access denied\nfor rds:DescribeDBInstances"
    )

    page.shown()

    assert page.banner.frame.isHidden() is False
    assert page.banner.label.text() == "Access denied"
    assert page.table.rowCount() == 0
    page.banner.details_button.click()
    assert page.banner.details_label.isHidden() is False
    assert page.banner.details_button.text() == "Hide"
    page.banner.details_button.click()
    assert page.banner.details_label.isHidden() is True
    page.banner.dismiss_button.click()
    assert page.banner.frame.isHidden()


def test_the_answer_of_a_context_that_is_no_longer_chosen_is_dropped(page, ctx) -> None:
    page._failed("old", "us-east-1", "late")
    page._loaded("old", "us-east-1", [instance()])

    assert page.instances is None and page.banner.frame.isHidden()


def test_the_search_looks_through_every_column(page) -> None:
    page.shown()

    page.search.setText("mysql")

    assert rows(page) == ["billing"]
    assert page.notice.text() == "1 of 2 instances"
    page.search.setText("")
    assert rows(page) == ["billing", "orders"]


def test_the_search_can_match_the_case_and_be_a_regular_expression(page) -> None:
    page.shown()
    page.search.setText("MYSQL")
    assert rows(page) == ["billing"]
    page.case_button.setChecked(True)
    assert rows(page) == []
    page.case_button.setChecked(False)
    page.regex_button.setChecked(True)
    page.search.setText("^(orders|nothing)$")
    assert rows(page) == ["orders"]


def test_a_regular_expression_that_does_not_compile_keeps_every_row(page) -> None:
    page.shown()
    page.regex_button.setChecked(True)

    page.search.setText("(")

    assert rows(page) == ["billing", "orders"]
    assert page.search.toolTip()


def test_compile_query() -> None:
    assert compile_query("", False, False) is None
    pattern = compile_query("a.b", False, False)
    assert pattern is not None
    assert pattern.search("A.B") and not pattern.search("axb")


def test_double_click_opens_the_details_in_a_tab(page, ctx) -> None:
    ctx.aws.answers[("rds", "describe-db-instances")] = {"DBInstances": [DATABASE]}
    page.shown()

    page._double_clicked(0, 0)
    page._double_clicked(9, 0)  # nothing there

    assert ctx.ui.jsons == [("RDS: orders", DATABASE)]


def test_the_logs_of_an_instance_are_picked_then_opened(page, ctx) -> None:
    ctx.aws.answers[("rds", "describe-db-log-files")] = {
        "DescribeDBLogFiles": [
            {"LogFileName": "error.log", "Size": 2048, "LastWritten": 0}
        ]
    }
    ctx.aws.answers[("rds", "download-db-log-file-portion")] = {"LogFileData": "boom"}

    page.logs(instance())
    assert ctx.ui.logs == []  # nothing picked

    ctx.ui.picked_row = (0, True)
    page.logs(instance())

    headers, rows, moments = ctx.ui.row_picks[0]
    assert headers == ["File", "Size", "Written"]
    assert rows[0][:2] == ["error.log", "2 KiB"]
    assert re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d", rows[0][2])
    assert len(moments) == 1
    assert ctx.ui.logs == [("orders", "error.log", "boom")]


def test_an_instance_without_logs_says_so(page, ctx) -> None:
    page.logs(instance())

    assert ctx.ui.messages == [("information", "Logs", "orders has no log files.")]


def test_without_the_window_the_page_does_nothing(page, ctx) -> None:
    ctx.ui = None

    page.details(instance())
    page.logs(instance())
    page.forward(instance())
    page.shown()

    assert ctx.aws.asked == []
    assert page.notice.text() == "Select a context."


def open_dialog(page, monkeypatch, ctx, act):
    """Run the forward dialog with `act` in place of its exec."""
    testing.answer_dialogs(monkeypatch, act)
    page.forward(instance())


def buttons(dialog) -> dict:
    return testing.buttons(dialog)


def test_the_forward_needs_the_id_of_an_instance(page, ctx, monkeypatch) -> None:
    ctx.aws.answers[("ssm", "describe-instance-information")] = {}

    open_dialog(
        page, monkeypatch, ctx, lambda d: buttons(d)["Run in KubeScope"].click()
    )

    assert ctx.forwards.started == []
    assert ctx.ui.messages[0][0] == "warning"
    assert "Type the ID of the EC2 instance" in ctx.ui.messages[0][2]


def test_the_forward_runs_with_the_ports_and_the_target_that_were_filled(
    page, ctx, monkeypatch
) -> None:
    ctx.aws.answers[("ssm", "describe-instance-information")] = {}

    def act(dialog) -> None:
        testing.find(dialog, "combo").setEditText("i-0123456789abcdef0")
        buttons(dialog)["Run in KubeScope"].click()

    open_dialog(page, monkeypatch, ctx, act)

    [(context, title, command, local, target)] = ctx.forwards.started
    assert title == "RDS orders" and local == 15432
    assert target == "orders.example.com:5432"
    assert command[:5] == [
        "aws",
        "ssm",
        "start-session",
        "--target",
        "i-0123456789abcdef0",
    ]
    assert command[-2:] == ["--profile", "work"] and context == ctx.current_context


def test_a_forward_the_app_refuses_is_told_to_the_person(
    page, ctx, monkeypatch
) -> None:
    ctx.aws.answers[("ssm", "describe-instance-information")] = {}
    ctx.forwards.failure = WriteModeOff("turn on the write mode to start a forward")

    def act(dialog) -> None:
        testing.find(dialog, "combo").setEditText("i-0123456789abcdef0")
        buttons(dialog)["Run in KubeScope"].click()

    open_dialog(page, monkeypatch, ctx, act)

    assert ctx.ui.messages[-1][2] == "turn on the write mode to start a forward"


def test_the_instances_systems_manager_can_reach_are_offered(
    page, ctx, monkeypatch
) -> None:
    ctx.aws.answers[("ssm", "describe-instance-information")] = {
        "InstanceInformationList": [
            {"InstanceId": "i-0123456789abcdef0", "PingStatus": "Online"}
        ]
    }
    ctx.aws.answers[("ec2", "describe-instances")] = {
        "Reservations": [
            {
                "Instances": [
                    {
                        "InstanceId": "i-0123456789abcdef0",
                        "VpcId": "vpc-1",
                        "Tags": [{"Key": "Name", "Value": "bastion"}],
                    }
                ]
            }
        ]
    }
    seen = {}

    def act(dialog) -> None:
        combo = testing.find(dialog, "combo")
        seen["items"] = [combo.itemText(i) for i in range(combo.count())]
        seen["chosen"] = combo.currentText()

    open_dialog(page, monkeypatch, ctx, act)

    assert seen["items"] == ["bastion  (i-0123456789abcdef0)"]
    assert seen["chosen"] == "bastion  (i-0123456789abcdef0)"


def test_the_forward_dialog_says_when_no_instance_can_be_reached(
    page, ctx, monkeypatch
) -> None:
    ctx.aws.answers[("ssm", "describe-instance-information")] = ClusterError("denied")
    seen = {}

    def act(dialog) -> None:
        seen["hint"] = testing.texts(dialog)

    open_dialog(page, monkeypatch, ctx, act)

    assert "denied" in seen["hint"]


def test_a_context_that_changes_while_the_page_is_open_loads_the_new_one(
    page, ctx
) -> None:
    page.widget.show()
    page.shown()
    ctx.current_context = "other"

    page._context_changed(context="other")

    assert page.instances is not None  # it asked again at once, not on the next opening
    assert ctx.aws.asked[-1][0] == "other"
    page.widget.close()


def test_the_menu_of_an_instance_offers_the_forward_only_in_the_write_mode(
    page, ctx, monkeypatch
) -> None:
    page.widget.show()
    page.shown()
    offered: list[list[str]] = []
    monkeypatch.setattr(
        page.components,
        "show_menu",
        lambda menu, _table, _x, _y: offered.append([a.text() for a in menu.actions()]),
    )
    table = page.table
    y = table.rowViewportPosition(0) + 5

    ctx.app.write_mode = False
    page._menu(5, y)
    ctx.app.write_mode = True
    page._menu(5, y)
    page._menu(5, 10_000)  # below the rows: nothing

    assert offered == [["Details", "Logs"], ["Details", "Logs", "Forward with SSM"]]
    assert table.currentRow() == 0
    page.instances = None
    page._menu(5, 5)  # nothing loaded: nothing
    assert len(offered) == 2
    page.widget.close()


def test_the_choice_of_a_log_without_the_window_does_nothing(page, ctx) -> None:
    ctx.ui = None

    page._choose_log(instance(), [])

    assert ctx.aws.asked == []


def test_the_forward_dialog_has_a_command_for_each_shell_on_windows(
    page, ctx, monkeypatch
) -> None:
    from kubescope.aws import ssm

    monkeypatch.setattr(ssm.sys, "platform", "win32")
    ctx.aws.answers[("ssm", "describe-instance-information")] = {}
    seen = {}

    def act(dialog) -> None:
        seen["boxes"] = testing.texts(dialog, "text")
        seen["copies"] = [b.text() for b in buttons(dialog).values()]

    open_dialog(page, monkeypatch, ctx, act)

    assert len(seen["boxes"]) == 2  # PowerShell and cmd
    assert "aws ssm start-session" in seen["boxes"][0]
    assert seen["copies"].count("Copy") == 1  # a button text is one key: one per name


def test_what_was_typed_stays_when_the_instances_come(page) -> None:
    from kubescope.sdk.models import SsmTarget

    components = UiComponents()
    combo = components.filter_select()
    combo.setEditable(True)
    combo.setEditText("i-0123456789abcdef0")
    hint = components.label()

    page._fill_targets(combo, hint, [SsmTarget("i-aaa", "bastion", "vpc-1", True)])

    assert combo.currentText() == "i-0123456789abcdef0"
    assert combo.count() == 1 and "can be reached" in hint.text()


def test_a_click_on_a_header_sorts_the_instances_and_a_second_one_reverses_them(
    page,
) -> None:
    page.shown()
    assert rows(page) == ["billing", "orders"]

    page.sorter.clicked(0)
    assert rows(page) == ["billing", "orders"]
    assert page.table.horizontalHeader().sortIndicatorSection() == 0

    page.sorter.clicked(0)
    assert rows(page) == ["orders", "billing"]

    page.sorter.clicked(5)  # the storage, a number
    assert page.table.horizontalHeader().sortIndicatorOrder() is not None
