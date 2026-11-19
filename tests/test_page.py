import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from kubescope.sdk import CONTEXT_CHANGED, WriteModeOff
from kubescope.sdk.errors import ClusterError
from kubescope.sdk.models import RdsInstance
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QPushButton

from kubescope.aws import extension
from kubescope.aws.badge import BADGE_ROLE
from kubescope.aws.rds_page import RdsPage, compile_query
from tests.conftest import DATABASE

application = QApplication.instance() or QApplication([])


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
    shown.deleteLater()


def rows(page: RdsPage) -> list[str]:
    table = page.ui.instancesTable
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
    assert isinstance(added["factory"](), RdsPage)
    ctx.aws.answers[("rds", "describe-db-instances")] = {"DBInstances": [DATABASE]}
    added["refresh"]()  # the refresh button of the header asks again
    assert ctx.aws.asked[-1][1] == ["rds", "describe-db-instances"]
    assert added["visible"]() is True
    ctx.aws.using = False
    assert added["visible"]() is False


def test_the_instances_are_listed_when_the_page_is_opened(page) -> None:
    page.shown()

    assert rows(page) == ["billing", "orders"]
    assert page.ui.noticeLabel.text() == "2 instances"
    assert page.ui.regionCombo.currentData() == "us-east-1"
    assert page.ctx.aws.asked[-1][2] == "us-east-1"
    assert page.ui.instancesTable.item(0, 4).data(BADGE_ROLE) is not None


def test_the_page_does_not_ask_again_for_the_same_context(page) -> None:
    page.shown()
    page.shown()

    assert len(page.ctx.aws.asked) == 1


def test_another_context_asks_again_with_its_own_region(page, ctx) -> None:
    page.shown()
    ctx.aws.scope_of = ctx.aws.scope_of._replace(region="sa-east-1")
    ctx.current_context = "other"
    page.shown()

    assert page.ui.regionCombo.currentData() == "sa-east-1"
    assert len(ctx.aws.asked) == 2 and ctx.aws.asked[-1][2] == "sa-east-1"


def test_a_region_the_list_does_not_know_is_added(page, ctx) -> None:
    ctx.aws.scope_of = ctx.aws.scope_of._replace(region="mars-north-1")

    page.shown()

    assert page.ui.regionCombo.currentData() == "mars-north-1"


def test_a_context_that_is_not_eks_keeps_the_region_that_was_chosen(page, ctx) -> None:
    def refuse(context):
        raise ClusterError("not eks")

    ctx.aws.scope = refuse

    page.shown()

    assert page.ui.regionCombo.currentData() == "us-east-1"


def test_choosing_another_region_asks_again(page) -> None:
    page.shown()

    page.ui.regionCombo.setCurrentIndex(page.ui.regionCombo.findData("sa-east-1"))

    assert page.ctx.aws.asked[-1][2] == "sa-east-1"


def test_without_a_context_it_says_so(page, ctx) -> None:
    ctx.current_context = None

    page.shown()

    assert page.ui.noticeLabel.text() == "Select a context."
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

    assert page.ui.rdsBanner.isHidden() is False
    assert page.ui.bannerLabel.text() == "Access denied"
    assert page.ui.instancesTable.rowCount() == 0
    page.ui.detailsButton.click()
    assert page.ui.bannerDetails.isHidden() is False
    assert page.ui.detailsButton.text() == "Hide"
    page.ui.detailsButton.click()
    assert page.ui.bannerDetails.isHidden() is True
    page.ui.dismissButton.click()
    assert page.ui.rdsBanner.isHidden()


def test_the_answer_of_a_context_that_is_no_longer_chosen_is_dropped(page, ctx) -> None:
    page._failed("old", "us-east-1", "late")
    page._loaded("old", "us-east-1", [instance()])

    assert page.instances is None and page.ui.rdsBanner.isHidden()


def test_the_search_looks_through_every_column(page) -> None:
    page.shown()

    page.ui.searchInput.setText("mysql")

    assert rows(page) == ["billing"]
    assert page.ui.noticeLabel.text() == "1 of 2 instances"
    page.ui.searchInput.setText("")
    assert rows(page) == ["billing", "orders"]


def test_the_search_can_match_the_case_and_be_a_regular_expression(page) -> None:
    page.shown()
    page.ui.searchInput.setText("MYSQL")
    assert rows(page) == ["billing"]
    page.case_button.setChecked(True)
    assert rows(page) == []
    page.case_button.setChecked(False)
    page.regex_button.setChecked(True)
    page.ui.searchInput.setText("^(orders|nothing)$")
    assert rows(page) == ["orders"]


def test_a_regular_expression_that_does_not_compile_keeps_every_row(page) -> None:
    page.shown()
    page.regex_button.setChecked(True)

    page.ui.searchInput.setText("(")

    assert rows(page) == ["billing", "orders"]
    assert page.ui.searchInput.toolTip()


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

    ctx.ui.picked = (ctx.ui.picks[0][0], True)
    page.logs(instance())

    assert re.fullmatch(
        r"error\.log  \(2 KiB, \d{4}-\d\d-\d\d \d\d:\d\d\)", ctx.ui.picks[0][0]
    )
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
    assert page.ui.noticeLabel.text() == "Select a context."


def open_dialog(page, monkeypatch, ctx, act):
    """Run the forward dialog with `act` in place of its exec."""
    monkeypatch.setattr(QDialog, "exec", lambda dialog: act(dialog) or 0)
    page.forward(instance())


def buttons(dialog) -> dict[str, QPushButton]:
    return {one.text(): one for one in dialog.findChildren(QPushButton)}


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
        dialog.findChild(QComboBox).setEditText("i-0123456789abcdef0")
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
        dialog.findChild(QComboBox).setEditText("i-0123456789abcdef0")
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
        combo = dialog.findChild(QComboBox)
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
        from PySide6.QtWidgets import QLabel

        seen["hint"] = [one.text() for one in dialog.findChildren(QLabel)]

    open_dialog(page, monkeypatch, ctx, act)

    assert "denied" in seen["hint"]


def test_a_context_that_changes_while_the_page_is_open_loads_the_new_one(
    page, ctx
) -> None:
    page.show()
    page.shown()
    ctx.current_context = "other"

    page._context_changed(context="other")

    assert page.instances is not None  # it asked again at once, not on the next opening
    assert ctx.aws.asked[-1][0] == "other"
    page.close()


def test_the_menu_of_an_instance_offers_the_forward_only_in_the_write_mode(
    page, ctx, monkeypatch
) -> None:
    from PySide6.QtCore import QPoint

    page.show()
    page.shown()
    offered: list[list[str]] = []
    monkeypatch.setattr(
        page,
        "_popup",
        lambda menu, where: offered.append([a.text() for a in menu.actions()]),
    )
    table = page.ui.instancesTable
    point = QPoint(5, table.rowViewportPosition(0) + 5)

    ctx.app.write_mode = False
    page._menu(point)
    ctx.app.write_mode = True
    page._menu(point)
    page._menu(QPoint(5, 10_000))  # below the rows: nothing

    assert offered == [["Details", "Logs"], ["Details", "Logs", "Forward with SSM"]]
    assert table.currentRow() == 0
    page.instances = None
    page._menu(point)  # nothing loaded: nothing
    assert len(offered) == 2
    page.close()


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
        from PySide6.QtWidgets import QPlainTextEdit

        seen["boxes"] = [
            box.toPlainText() for box in dialog.findChildren(QPlainTextEdit)
        ]
        seen["copies"] = [b.text() for b in buttons(dialog).values()]

    open_dialog(page, monkeypatch, ctx, act)

    assert len(seen["boxes"]) == 2  # PowerShell and cmd
    assert "aws ssm start-session" in seen["boxes"][0]
    assert seen["copies"].count("Copy") == 1  # a button text is one key: one per name


def test_what_was_typed_stays_when_the_instances_come(page) -> None:
    from kubescope.sdk.models import SsmTarget
    from PySide6.QtWidgets import QComboBox, QLabel

    combo = QComboBox()
    combo.setEditable(True)
    combo.setEditText("i-0123456789abcdef0")
    hint = QLabel()

    page._fill_targets(combo, hint, [SsmTarget("i-aaa", "bastion", "vpc-1", True)])

    assert combo.currentText() == "i-0123456789abcdef0"
    assert combo.count() == 1 and "can be reached" in hint.text()


def test_the_menu_is_shown_where_the_person_clicked(page) -> None:
    from PySide6.QtCore import QPoint, QTimer
    from PySide6.QtWidgets import QMenu

    menu = QMenu()
    menu.addAction("Details")
    QTimer.singleShot(0, menu.close)  # nobody answers it: close it at once

    page._popup(menu, QPoint(0, 0))

    assert not menu.isVisible()
