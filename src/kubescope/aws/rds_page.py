"""The page of the RDS instances of the AWS account of the selected cluster."""

import datetime
import re
from functools import partial
from typing import Any

from kubescope.sdk import (
    CONTEXT_CHANGED,
    Context,
    WriteModeOff,
)
from kubescope.sdk.errors import ClusterError, first_line
from kubescope.sdk.models import RdsInstance, RdsLogFile, SsmTarget
from kubescope.sdk.timezone import to_zone
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kubescope.aws import rds, ssm
from kubescope.aws.badge import BADGE_ROLE, BadgeDelegate, status_colors
from kubescope.aws.ui_rds_page import Ui_RdsPage


def compile_query(query: str, match_case: bool, regex: bool) -> re.Pattern[str] | None:
    """The pattern of a search, None for an empty one; `re.error` when a
    regular expression does not compile."""
    if not query:
        return None
    return re.compile(query if regex else re.escape(query), 0 if match_case else re.I)


def _switch(text: str, tip: str) -> QPushButton:
    button = QPushButton(text)
    button.setCheckable(True)
    button.setToolTip(tip)
    button.setFixedSize(38, 32)
    button.setProperty("variant", "secondary")
    return button


class RdsPage(QWidget):
    def __init__(self, ctx: Context) -> None:
        super().__init__()
        self.ctx = ctx
        self.ui = Ui_RdsPage()
        self.ui.setupUi(self)
        self.instances: list[RdsInstance] | None = None
        self.loaded_context = ""
        self.case_button = _switch("Aa", self.tr("Match case"))
        self.regex_button = _switch(".*", self.tr("Regular expression"))
        header = self.ui.rdsHeaderRow
        after = header.indexOf(self.ui.searchInput) + 1
        for button in (self.regex_button, self.case_button):
            header.insertWidget(after, button)
        self.ui.searchInput.textChanged.connect(self.filter)
        self.case_button.toggled.connect(self.filter)
        self.regex_button.toggled.connect(self.filter)
        for code in ctx.aws.regions():
            self.ui.regionCombo.addItem(code, code)
        self.ui.regionCombo.currentIndexChanged.connect(self._region_changed)
        self.ui.dismissButton.clicked.connect(self.ui.rdsBanner.hide)
        self.ui.detailsButton.clicked.connect(self._toggle_details)
        self.ui.rdsBanner.hide()
        table = self.ui.instancesTable
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(self._menu)
        table.cellDoubleClicked.connect(self._double_clicked)
        for column, width in enumerate((300, 100, 80, 120, 100, 90, 90, 100, 150)):
            table.setColumnWidth(column, width)
        table.setItemDelegateForColumn(4, BadgeDelegate(table))
        ctx.events.on(CONTEXT_CHANGED, self._context_changed)

    # what is shown

    def shown(self) -> None:
        """The page was opened."""
        context = self.ctx.current_context or ""
        if self.loaded_context != context:  # another context: its region first
            self._sync_region(context)
        if self.instances is None or self.loaded_context != context:
            self.load()

    def _context_changed(self, context: str | None = None, **_rest: Any) -> None:
        self.instances = None  # the instances are those of the context
        if self.isVisible():
            self.shown()

    def _sync_region(self, context: str) -> None:
        """Choose in the region select the region of the context, which is
        where the instances are looked for until another is chosen."""
        combo = self.ui.regionCombo
        try:
            region = self.ctx.aws.scope(context).region if context else ""
        except ClusterError:
            region = ""
        region = region or combo.currentData() or "us-east-1"
        combo.blockSignals(True)
        if combo.findData(region) < 0:  # a region the list does not know
            combo.insertItem(0, region, region)
        combo.setCurrentIndex(combo.findData(region))
        combo.blockSignals(False)

    def _region_changed(self, _index: int) -> None:
        self.instances = None
        self.load()

    def _themed(self, color: str) -> str:
        ui = self.ctx.ui
        return ui.themed(color) if ui is not None else color

    def load(self, _checked: bool = False) -> None:
        """Ask for the instances of the account of the selected context in the
        region chosen, off the UI thread."""
        ui = self.ctx.ui
        context = self.ctx.current_context or ""
        region = self.ui.regionCombo.currentData() or ""
        if not context or ui is None:
            self.ui.instancesTable.setRowCount(0)
            self.ui.noticeLabel.setText(self.tr("Select a context."))
            return
        self.ui.rdsBanner.hide()
        self.ui.noticeLabel.setText(self.tr("Loading RDS instances..."))
        ui.run_action(
            partial(rds.instances, self.ctx.aws),
            partial(self._loaded, context, region),
            context,
            region,
            on_error=partial(self._failed, context, region),
        )

    def _is_current(self, context: str, region: str) -> bool:
        return context == (self.ctx.current_context or "") and region == (
            self.ui.regionCombo.currentData() or ""
        )

    def _failed(self, context: str, region: str, message: str) -> None:
        if not self._is_current(context, region):
            return  # the answer of a context or a region that is no longer chosen
        self.ui.instancesTable.setRowCount(0)
        self.ui.noticeLabel.setText("")
        self.ui.bannerLabel.setText(first_line(message))
        self.ui.bannerDetails.setText(message.strip())
        self.ui.bannerDetails.hide()
        self.ui.detailsButton.setText(self.tr("Details"))
        self.ui.detailsButton.setVisible(message.strip() != first_line(message))
        self.ui.rdsBanner.show()

    def _toggle_details(self) -> None:
        showing = not self.ui.bannerDetails.isHidden()
        self.ui.bannerDetails.setVisible(not showing)
        self.ui.detailsButton.setText(
            self.tr("Details") if showing else self.tr("Hide")
        )

    def _loaded(self, context: str, region: str, instances: list[RdsInstance]) -> None:
        if not self._is_current(context, region):
            return
        self.instances = instances
        self.loaded_context = context
        table = self.ui.instancesTable
        table.setRowCount(len(instances))
        for row, item in enumerate(instances):
            cells = (
                item.identifier,
                item.engine,
                item.version,
                item.size,
                item.status,
                f"{item.storage} GiB",
                self.tr("Yes") if item.multi_az else self.tr("No"),
                item.region,
                item.account,
                item.endpoint,
            )
            for column, text in enumerate(cells):
                cell = QTableWidgetItem(text)
                if column == 4:  # the status, as a badge
                    cell.setData(BADGE_ROLE, status_colors(text, self._themed))
                table.setItem(row, column, cell)
        self.filter()

    def filter(self, *_args: object) -> None:
        """Show the instances that have what the search looks for in some
        column, and count them."""
        ui = self.ui
        ui.searchInput.setToolTip("")
        pattern = None
        text = ui.searchInput.text()
        try:
            pattern = compile_query(
                text if self.regex_button.isChecked() else text.strip(),
                self.case_button.isChecked(),
                self.regex_button.isChecked(),
            )
        except re.error as error:  # every row stays until it compiles
            ui.searchInput.setToolTip(str(error))
        table = ui.instancesTable
        visible = 0
        for row in range(table.rowCount()):
            matches = pattern is None or any(
                pattern.search(self._cell(row, column))
                for column in range(table.columnCount())
            )
            table.setRowHidden(row, not matches)
            visible += matches
        total = table.rowCount()
        ui.noticeLabel.setText(
            self.tr("{count} instances").format(count=total)
            if pattern is None
            else self.tr("{visible} of {total} instances").format(
                visible=visible, total=total
            )
        )

    def _cell(self, row: int, column: int) -> str:
        item = self.ui.instancesTable.item(row, column)
        return item.text() if item is not None else ""

    # what is done with an instance

    def _menu(self, position: QPoint) -> None:
        """Right-click on an instance: its details, its logs and, with the
        write mode on, a forward through AWS Systems Manager."""
        table = self.ui.instancesTable
        row = table.rowAt(position.y())
        if row < 0 or self.instances is None:
            return
        table.selectRow(row)
        instance = self.instances[row]
        menu = QMenu(self)
        menu.addAction(self.tr("Details"), partial(self.details, instance))
        menu.addAction(self.tr("Logs"), partial(self.logs, instance))
        if self.ctx.app.write_mode:
            menu.addAction(self.tr("Forward with SSM"), partial(self.forward, instance))
        menu.exec(table.viewport().mapToGlobal(position))

    def _double_clicked(self, row: int, _column: int) -> None:
        if self.instances is not None and 0 <= row < len(self.instances):
            self.details(self.instances[row])

    def details(self, instance: RdsInstance) -> None:
        """Everything the AWS CLI says about an instance, in a Details tab."""
        ui = self.ctx.ui
        if ui is None:
            return
        ui.run_action(
            partial(rds.details, self.ctx.aws),
            partial(ui.show_json, f"RDS: {instance.identifier}"),
            self.ctx.current_context,
            instance.identifier,
            instance.region,
        )

    def logs(self, instance: RdsInstance) -> None:
        """The log files of an instance, to pick one to read."""
        ui = self.ctx.ui
        if ui is None:
            return
        ui.run_action(
            partial(rds.log_files, self.ctx.aws),
            partial(self._choose_log, instance),
            self.ctx.current_context,
            instance.identifier,
            instance.region,
        )

    @staticmethod
    def _log_time(item: RdsLogFile) -> str:
        """When a log file was last written, in the time zone of the
        settings."""
        moment = datetime.datetime.fromtimestamp(item.written / 1000, datetime.UTC)
        return to_zone(moment).strftime("%Y-%m-%d %H:%M")

    def _choose_log(self, instance: RdsInstance, files: list[RdsLogFile]) -> None:
        ui = self.ctx.ui
        if ui is None:
            return
        if not files:
            ui.show_message(
                "information",
                self.tr("Logs"),
                self.tr("{name} has no log files.").format(name=instance.identifier),
            )
            return
        names = [
            f"{item.name}  ({item.size // 1024} KiB, {self._log_time(item)})"
            for item in files
        ]
        chosen, accepted = ui.pick_item(
            self.tr("Logs"), self.tr("Select the log file:"), names
        )
        if accepted:
            self._open_log(instance, files[names.index(chosen)].name)

    def _open_log(self, instance: RdsInstance, name: str) -> None:
        ui = self.ctx.ui
        context = self.ctx.current_context or ""
        if ui is not None:
            ui.open_log(
                instance.identifier,
                name,
                lambda: rds.log(
                    self.ctx.aws, context, instance.identifier, name, instance.region
                ),
            )

    # the forward

    def forward(self, instance: RdsInstance) -> None:
        """The AWS CLI command that forwards a local port to the database
        through an EC2 instance with Systems Manager, to copy or to run here.
        The instance, the region and the profile come filled in."""
        ui = self.ctx.ui
        context = self.ctx.current_context or ""
        if ui is None:
            return
        dialog = QDialog(ui.window)
        dialog.setWindowTitle(self.tr("Forward with SSM"))
        dialog.setMinimumWidth(560)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        intro = self.tr("Forward a local port to {name} through AWS Systems Manager.")
        layout.addWidget(QLabel(intro.format(name=instance.identifier)))
        layout.addWidget(QLabel(self.tr("EC2 instance that reaches the database:")))
        target = QComboBox()
        target.setEditable(True)
        target.setProperty("variant", "filter")
        edit = target.lineEdit()
        if edit is not None:
            edit.setPlaceholderText("i-0123456789abcdef0")
        layout.addWidget(target)
        hint = QLabel(self.tr("Looking for an instance Systems Manager can reach..."))
        hint.setProperty("variant", "muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        row = QHBoxLayout()
        region = QLineEdit(instance.region)
        profile = QLineEdit(instance.profile)
        profile.setPlaceholderText(self.tr("default"))
        for label, field in (
            (self.tr("Region:"), region),
            (self.tr("Profile:"), profile),
        ):
            field.setProperty("variant", "filter")
            column = QVBoxLayout()
            column.addWidget(QLabel(label))
            column.addWidget(field)
            row.addLayout(column)
        layout.addLayout(row)
        layout.addWidget(QLabel(self.tr("Database port:")))
        remote = QSpinBox()
        remote.setProperty("variant", "filter")
        remote.setRange(1, 65535)
        remote.setValue(instance.port or 5432)
        layout.addWidget(remote)
        layout.addWidget(QLabel(self.tr("Local port:")))
        local = QSpinBox()
        local.setProperty("variant", "filter")
        local.setRange(1, 65535)
        local.setValue(min(remote.value() + 10000, 65535))  # clear of a local server
        layout.addWidget(local)
        text = QLabel(
            self.tr(
                "Run this in a terminal and keep it open while you use the port. "
                "It needs the Session Manager plugin of the AWS CLI."
            )
        )
        text.setWordWrap(True)
        layout.addWidget(text)

        def chosen() -> str:
            typed = target.currentText().strip()
            index = target.findText(typed)
            return str(target.itemData(index)) if index >= 0 else typed

        def arguments() -> list[str]:
            return ssm.forward_arguments(
                chosen(),
                instance.endpoint,
                remote.value(),
                local.value(),
                region.text().strip(),
                profile.text().strip(),
            )

        def run_here() -> None:
            if not chosen().startswith(("i-", "mi-")):
                ui.show_message(
                    "warning",
                    self.tr("Forward with SSM"),
                    self.tr(
                        "Type the ID of the EC2 instance, such as i-0123456789abcdef0."
                    ),
                )
                return
            try:
                started = self.ctx.forwards.start_ssm(
                    context,
                    f"RDS {instance.identifier}",
                    arguments(),
                    local.value(),
                    f"{instance.endpoint}:{remote.value()}",
                )
            except (WriteModeOff, ClusterError) as error:
                ui.show_message("warning", self.tr("Forward with SSM"), str(error))
                return
            if started:
                dialog.accept()

        refresh = self._command_views(
            dialog,
            layout,
            lambda: ssm.forward_commands(
                chosen(),
                instance.endpoint,
                remote.value(),
                local.value(),
                region.text().strip(),
                profile.text().strip(),
            ),
            run_here,
        )
        target.editTextChanged.connect(refresh)
        region.textChanged.connect(refresh)
        profile.textChanged.connect(refresh)
        remote.valueChanged.connect(refresh)
        local.valueChanged.connect(refresh)
        ui.run_action(
            partial(ssm.targets, self.ctx.aws),
            partial(self._fill_targets, target, hint),
            context,
            instance.vpc,
            instance.region,
            on_error=hint.setText,
            quiet=True,
        )
        dialog.exec()

    def _command_views(self, dialog, layout, build, run):  # type: ignore[no-untyped-def]
        """Show the commands `build` returns as (shell, command) pairs: a box
        for each, named by its shell when there is more than one, with a Copy
        button, and at the foot Run in KubeScope and Close. Returns the function
        that shows them again after a choice changed."""
        boxes = []
        copies = []
        for shell, _command in build():
            if shell:
                layout.addWidget(QLabel(shell))
            box = QPlainTextEdit()
            box.setReadOnly(True)
            box.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
            box.setFixedHeight(96 if not shell else 64)
            layout.addWidget(box)
            copy = self._button(self.tr("Copy"))
            copy.clicked.connect(
                lambda _checked=False, box=box: QApplication.clipboard().setText(
                    box.toPlainText()
                )
            )
            copies.append(copy)
            boxes.append(box)

        def refresh() -> None:
            for box, (_shell, command) in zip(boxes, build(), strict=True):
                box.setPlainText(command)

        footer = QHBoxLayout()
        footer.addStretch()
        if len(copies) == 1:  # one command: its Copy joins the other buttons
            footer.addWidget(copies[0])
        else:  # a box for each shell: each has its Copy under it
            for box, copy in zip(boxes, copies, strict=True):
                line = QHBoxLayout()
                line.addStretch()
                line.addWidget(copy)
                layout.insertLayout(layout.indexOf(box) + 1, line)
        run_button = self._button(self.tr("Run in KubeScope"))
        run_button.clicked.connect(run)
        footer.addWidget(run_button)
        close = self._button(self.tr("Close"))
        close.clicked.connect(dialog.accept)
        footer.addWidget(close)
        layout.addLayout(footer)
        refresh()
        return refresh

    @staticmethod
    def _button(text: str) -> QPushButton:
        button = QPushButton(text)
        button.setProperty("variant", "secondary")
        button.setMinimumWidth(120)
        return button

    def _fill_targets(
        self, combo: QComboBox, hint: QLabel, found: list[SsmTarget]
    ) -> None:
        """Offer the instances found, the best one first and already chosen
        unless something was typed meanwhile."""
        typed = combo.currentText().strip()
        for one in found:
            label = f"{one.name}  ({one.instance_id})" if one.name else one.instance_id
            combo.addItem(label, one.instance_id)
        if typed:
            combo.setEditText(typed)  # adding the first item replaced what was typed
        elif found:
            combo.setCurrentIndex(0)
        if any(one.same_vpc for one in found):
            hint.setText(
                self.tr(
                    "{count} instances can be reached; the first is in the VPC of "
                    "the database."
                ).format(count=len(found))
            )
        else:
            hint.setText(
                self.tr(
                    "No instance in the VPC of the database can be reached by "
                    "Systems Manager; type the ID of one."
                )
            )
