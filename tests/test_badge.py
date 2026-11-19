import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
)

from kubescope.aws.badge import (
    BADGE_PADDING,
    BADGE_ROLE,
    PADDING,
    BadgeDelegate,
    status_colors,
)

application = QApplication.instance() or QApplication([])


def themed(color: str) -> str:
    return color


@pytest.mark.parametrize(
    ("status", "text"),
    [
        ("available", "#176b58"),  # fine: green
        ("AVAILABLE", "#176b58"),
        ("backing-up", "#985415"),  # changing: amber
        ("pending-reboot", "#985415"),
        ("failed", "#a33d45"),  # failed: red
        ("incompatible-parameters", "#a33d45"),
        ("stopped", "#505963"),  # anything else: neutral
        ("", "#505963"),
    ],
)
def test_the_status_of_a_database_is_green_amber_red_or_neutral(status, text) -> None:
    assert status_colors(status, themed)[0] == text


def table_with(*cells: tuple[str, bool]) -> QTableWidget:
    table = QTableWidget(len(cells), 1)
    table.setItemDelegateForColumn(0, BadgeDelegate(table))
    for row, (text, badge) in enumerate(cells):
        item = QTableWidgetItem(text)
        if badge:
            item.setData(BADGE_ROLE, ("#176b58", "#e5f4eb"))
        table.setItem(row, 0, item)
    table.resize(300, 200)
    return table


def test_a_badge_is_drawn_and_a_plain_cell_is_drawn_as_usual() -> None:
    table = table_with(("available", True), ("plain", False))
    table.show()

    image = table.grab().toImage()  # paints every cell through the delegate

    assert not image.isNull()
    table.close()


def test_the_badge_draws_the_text_so_the_cell_has_none() -> None:
    table = table_with(("available", True), ("plain", False))
    delegate = table.itemDelegateForColumn(0)
    assert isinstance(delegate, BadgeDelegate)

    badge, plain = QStyleOptionViewItem(), QStyleOptionViewItem()
    delegate.initStyleOption(badge, table.model().index(0, 0))
    delegate.initStyleOption(plain, table.model().index(1, 0))

    assert badge.text == "" and plain.text == "plain"


def test_a_badge_leaves_room_for_its_padding_around_the_text() -> None:
    table = table_with(("available", True), ("plain", False))
    delegate = table.itemDelegateForColumn(0)
    assert isinstance(delegate, BadgeDelegate)
    option = QStyleOptionViewItem()

    badge = delegate.sizeHint(option, table.model().index(0, 0))
    plain = delegate.sizeHint(option, table.model().index(1, 0))

    assert badge.width() >= 2 * BADGE_PADDING + PADDING
    assert badge.height() == plain.height()
