"""The status of a database drawn as a badge, a rounded outlined pill."""

from collections.abc import Callable

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

BADGE_ROLE = Qt.ItemDataRole.UserRole + 5  # (text color, fill color)
BADGE_PADDING = 10
BADGE_HEIGHT = 20
PADDING = 8

_GOOD = {"NORMAL", "ACTIVE", "DEPLOYED", "AVAILABLE", "RUNNING"}
_WARNING = {
    "WARNING",
    "CREATING",
    "UPDATING",
    "DELETING",
    "MODIFYING",
    "BACKING-UP",
    "REBOOTING",
    "STARTING",
    "STOPPING",
    "UPGRADING",
    "RENAMING",
}
_BAD = ("FAIL", "ERROR", "DEGRADED", "INCOMPATIBLE")


def status_colors(status: str, themed: Callable[[str], str]) -> tuple[str, str]:
    """The text and fill colors of a status: green when fine, amber while it
    changes, red when it failed."""
    word = status.upper()
    if any(bad in word for bad in _BAD):
        return themed("#a33d45"), themed("#fce9ea")
    if word in _GOOD:
        return themed("#176b58"), themed("#e5f4eb")
    if word in _WARNING or word.startswith("PENDING"):
        return themed("#985415"), themed("#fff2de")
    return themed("#505963"), themed("#eff1f3")


class BadgeDelegate(QStyledItemDelegate):
    """Draws the text of a cell as a badge when the cell carries its colors;
    any other cell is drawn as usual."""

    def initStyleOption(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        super().initStyleOption(option, index)
        if index.data(BADGE_ROLE):
            option.text = ""  # the badge draws the text

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        colors = index.data(BADGE_ROLE)
        super().paint(painter, option, index)
        if not colors:
            return
        text_color, fill = (QColor(color) for color in colors)
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        font = QFont(option.font)
        font.setBold(True)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(font)
        width = painter.fontMetrics().horizontalAdvance(text) + 2 * BADGE_PADDING
        rect = QRectF(
            option.rect.left() + PADDING,
            option.rect.top() + (option.rect.height() - BADGE_HEIGHT) / 2,
            min(width, option.rect.width() - PADDING),
            BADGE_HEIGHT,
        )
        border = QColor(text_color)
        border.setAlpha(90)
        painter.setPen(border)
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, BADGE_HEIGHT / 2, BADGE_HEIGHT / 2)
        painter.setPen(text_color)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QSize:
        hint = super().sizeHint(option, index)
        if not index.data(BADGE_ROLE):
            return hint
        return QSize(hint.width() + 2 * BADGE_PADDING + PADDING, hint.height())
