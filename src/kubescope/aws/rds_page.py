"""The page of the RDS instances of the AWS account of the selected cluster."""

import datetime
import re
from collections.abc import Callable
from functools import partial
from typing import Any

from kubescope.sdk import (
    CONTEXT_CHANGED,
    Components,
    Context,
    WriteModeOff,
    translate,
)
from kubescope.sdk.errors import ClusterError, first_line
from kubescope.sdk.models import RdsInstance, RdsLogFile, SsmTarget, natural_key
from kubescope.sdk.timezone import to_zone

from kubescope.aws import rds, ssm


def compile_query(query: str, match_case: bool, regex: bool) -> re.Pattern[str] | None:
    """The pattern of a search, None for an empty one; `re.error` when a
    regular expression does not compile."""
    if not query:
        return None
    return re.compile(query if regex else re.escape(query), 0 if match_case else re.I)


class RdsPage:
    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx
        components = self.components
        self.widget = components.widget(shown=self.shown)
        self.instances: list[RdsInstance] | None = None
        self._sort: tuple[int, bool] | None = None  # the header clicked
        self.loaded_context = ""
        self.region = components.filter_select()
        self.region.setToolTip(translate("RdsPage", "Region"))
        self.search = components.search_box(
            translate("RdsPage", "Search all columns...")
        )
        self.case_button = components.switch_button(
            "Aa", translate("RdsPage", "Match case")
        )
        self.regex_button = components.switch_button(
            ".*", translate("RdsPage", "Regular expression")
        )
        self.notice = components.label(variant="muted", wrap=True)
        self.banner = components.error_banner(
            translate("RdsPage", "Details"),
            translate("RdsPage", "Hide"),
            translate("RdsPage", "Dismiss"),
        )
        self.table = components.data_table(
            [
                translate("RdsPage", "NAME"),
                translate("RdsPage", "ENGINE"),
                translate("RdsPage", "VERSION"),
                translate("RdsPage", "CLASS"),
                translate("RdsPage", "STATUS"),
                translate("RdsPage", "STORAGE"),
                translate("RdsPage", "MULTI-AZ"),
                translate("RdsPage", "REGION"),
                translate("RdsPage", "ACCOUNT"),
                translate("RdsPage", "ENDPOINT"),
            ],
            (300, 100, 80, 120, 100, 90, 90, 100, 150),
        )
        components.page(
            self.widget,
            filters=components.row(
                self.region,
                self.search,
                self.case_button,
                self.regex_button,
                self.notice,
                None,
            ),
            notice=self.banner.frame,
            body=self.table,
        )
        self.search.textChanged.connect(self.filter)
        self.case_button.toggled.connect(self.filter)
        self.regex_button.toggled.connect(self.filter)
        for code in ctx.aws.regions():
            self.region.addItem(code, code)
        self.region.currentIndexChanged.connect(self._region_changed)
        components.on_context_menu(self.table, self._menu)
        self.table.cellDoubleClicked.connect(self._double_clicked)
        self.sorter = components.header_sorter(self.table, self._ordered)
        ctx.events.on(CONTEXT_CHANGED, self._context_changed)

    # what is shown

    @property
    def components(self) -> Components:
        """The elements of the app; a page is only built in a window."""
        ui = self.ctx.ui
        assert ui is not None
        return ui.components

    def shown(self) -> None:
        """The page was opened."""
        context = self.ctx.current_context or ""
        if self.loaded_context != context:  # another context: its region first
            self._sync_region(context)
        if self.instances is None or self.loaded_context != context:
            self.load()

    def _context_changed(self, context: str | None = None, **_rest: Any) -> None:
        self.instances = None  # the instances are those of the context
        if self.widget.isVisible():
            self.shown()

    def _sync_region(self, context: str) -> None:
        """Choose in the region select the region of the context, which is
        where the instances are looked for until another is chosen."""
        combo = self.region
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

    def load(self, _checked: bool = False) -> None:
        """Ask for the instances of the account of the selected context in the
        region chosen, off the UI thread."""
        ui = self.ctx.ui
        context = self.ctx.current_context or ""
        region = self.region.currentData() or ""
        if not context or ui is None:
            self.table.setRowCount(0)
            self.notice.setText(translate("RdsPage", "Select a context."))
            return
        self.banner.dismiss()
        self.notice.setText(translate("RdsPage", "Loading RDS instances..."))
        ui.run_action(
            partial(rds.instances, self.ctx.aws),
            partial(self._loaded, context, region),
            context,
            region,
            on_error=partial(self._failed, context, region),
        )

    def _is_current(self, context: str, region: str) -> bool:
        return context == (self.ctx.current_context or "") and region == (
            self.region.currentData() or ""
        )

    def _failed(self, context: str, region: str, message: str) -> None:
        if not self._is_current(context, region):
            return  # the answer of a context or a region that is no longer chosen
        self.table.setRowCount(0)
        self.notice.setText("")
        self.banner.show_error(
            first_line(message),
            message.strip(),
            (
                translate("RdsPage", "Details"),
                translate("RdsPage", "Hide"),
            ),
        )

    def _loaded(self, context: str, region: str, instances: list[RdsInstance]) -> None:
        if not self._is_current(context, region):
            return
        self.instances = instances
        self.loaded_context = context
        self._draw()

    def _cells(self, item: RdsInstance) -> tuple[str, ...]:
        return (
            item.identifier,
            item.engine,
            item.version,
            item.size,
            item.status,
            f"{item.storage} GiB",
            translate("RdsPage", "Yes")
            if item.multi_az
            else translate("RdsPage", "No"),
            item.region,
            item.account,
            item.endpoint,
        )

    def _ordered(self, column: int, descending: bool) -> None:
        """A click on a header: the instances in that order."""
        self._sort = (column, descending)
        self._draw()

    def _draw(self) -> None:
        """The instances in the table, in the order of the header clicked."""
        instances = self.instances or []
        if self._sort is not None:
            column, descending = self._sort
            instances.sort(
                key=lambda one: natural_key(self._cells(one)[column]),
                reverse=descending,
            )
        table = self.table
        table.setRowCount(len(instances))
        for row, item in enumerate(instances):
            for column, text in enumerate(self._cells(item)):
                cell = self.components.table_item(text)
                if column == 4:  # the status, as a badge
                    self.components.set_badge(cell, text)
                table.setItem(row, column, cell)
        self.filter()

    def filter(self, *_args: object) -> None:
        """Show the instances that have what the search looks for in some
        column, and count them."""
        self.search.setToolTip("")
        pattern = None
        text = self.search.text()
        try:
            pattern = compile_query(
                text if self.regex_button.isChecked() else text.strip(),
                self.case_button.isChecked(),
                self.regex_button.isChecked(),
            )
        except re.error as error:  # every row stays until it compiles
            self.search.setToolTip(str(error))
        table = self.table
        visible = 0
        for row in range(table.rowCount()):
            matches = pattern is None or any(
                pattern.search(self._cell(row, column))
                for column in range(table.columnCount())
            )
            table.setRowHidden(row, not matches)
            visible += matches
        total = table.rowCount()
        self.notice.setText(
            translate("RdsPage", "{count} instances").format(count=total)
            if pattern is None
            else translate("RdsPage", "{visible} of {total} instances").format(
                visible=visible, total=total
            )
        )

    def _cell(self, row: int, column: int) -> str:
        item = self.table.item(row, column)
        return item.text() if item is not None else ""

    # what is done with an instance

    def _menu(self, x: int, y: int) -> None:
        """Right-click on an instance: its details, its logs and, with the
        write mode on, a forward through AWS Systems Manager."""
        table = self.table
        row = table.rowAt(y)
        if row < 0 or self.instances is None:
            return
        table.selectRow(row)
        instance = self.instances[row]
        menu = self.components.menu(self.widget)
        menu.addAction(
            translate("RdsPage", "Details"),
            partial(self.details, instance),
        )
        menu.addAction(translate("RdsPage", "Logs"), partial(self.logs, instance))
        if self.ctx.app.write_mode:
            menu.addAction(
                translate("RdsPage", "Forward with SSM"),
                partial(self.forward, instance),
            )
        self.components.show_menu(menu, table, x, y)

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
    def _log_moment(item: RdsLogFile) -> datetime.datetime:
        """When a log file was last written, in the time zone of the
        settings."""
        moment = datetime.datetime.fromtimestamp(item.written / 1000, datetime.UTC)
        return to_zone(moment)

    @classmethod
    def _log_time(cls, item: RdsLogFile) -> str:
        return cls._log_moment(item).strftime("%Y-%m-%d %H:%M")

    def _choose_log(self, instance: RdsInstance, files: list[RdsLogFile]) -> None:
        ui = self.ctx.ui
        if ui is None:
            return
        if not files:
            ui.show_message(
                "information",
                translate("RdsPage", "Logs"),
                translate("RdsPage", "{name} has no log files.").format(
                    name=instance.identifier
                ),
            )
            return
        index, accepted = ui.pick_row(
            translate("RdsPage", "Logs"),
            translate("RdsPage", "Select the log file:"),
            [
                translate("RdsPage", "File"),
                translate("RdsPage", "Size"),
                translate("RdsPage", "Written"),
            ],
            [
                [item.name, f"{item.size // 1024} KiB", self._log_time(item)]
                for item in files
            ],
            [self._log_moment(item) for item in files],
        )
        if accepted:
            self._open_log(instance, files[index].name)

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

        The instance, the region and the profile come filled in.
        """
        ui = self.ctx.ui
        context = self.ctx.current_context or ""
        if ui is None:
            return
        components = self.components
        intro = translate(
            "RdsPage", "Forward a local port to {name} through AWS Systems Manager."
        )
        body: list[Any] = [
            components.label(intro.format(name=instance.identifier)),
            components.label(
                translate("RdsPage", "EC2 instance that reaches the database:")
            ),
        ]
        target = components.filter_select()
        target.setEditable(True)
        edit = target.lineEdit()
        if edit is not None:
            edit.setPlaceholderText("i-0123456789abcdef0")
        hint = components.label(
            translate(
                "RdsPage", "Looking for an instance Systems Manager can reach..."
            ),
            "muted",
            wrap=True,
        )
        region = components.text_field()
        region.setText(instance.region)
        profile = components.text_field(translate("RdsPage", "default"))
        profile.setText(instance.profile)
        remote = components.number_field(1, 65535, instance.port or 5432)
        local = components.number_field(  # clear of a local server
            1, 65535, min(remote.value() + 10000, 65535)
        )
        body += [
            target,
            hint,
            components.row(
                components.column(
                    components.label(translate("RdsPage", "Region:")),
                    region,
                    spacing=4,
                ),
                components.column(
                    components.label(translate("RdsPage", "Profile:")),
                    profile,
                    spacing=4,
                ),
            ),
            components.label(translate("RdsPage", "Database port:")),
            remote,
            components.label(translate("RdsPage", "Local port:")),
            local,
            components.label(
                translate(
                    "RdsPage",
                    "Run this in a terminal and keep it open while you use the port. "
                    "It needs the Session Manager plugin of the AWS CLI.",
                ),
                wrap=True,
            ),
        ]

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
                    translate("RdsPage", "Forward with SSM"),
                    translate(
                        "RdsPage",
                        "Type the ID of the EC2 instance, such as i-0123456789abcdef0.",
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
                ui.show_message(
                    "warning",
                    translate("RdsPage", "Forward with SSM"),
                    str(error),
                )
                return
            if started:
                dialog.accept()

        views, buttons, close, refresh = self._command_views(
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
        dialog = components.dialog(
            ui.window,
            translate("RdsPage", "Forward with SSM"),
            components.column(*body, *views),
            buttons,
            width=560,
        )
        close.clicked.connect(dialog.accept)
        refresh()
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

    def _command_views(self, build, run):  # type: ignore[no-untyped-def]
        """Show the commands `build` returns as (shell, command) pairs: a box
        for each, named by its shell when there is more than one, with a Copy
        button, and at the foot Run in KubeScope and Close.

        Returns what goes in the body of the dialog, its buttons, the
        Close button and the function that shows the commands again
        after a choice changed.
        """
        components = self.components
        views: list[Any] = []
        boxes = []
        copies = []
        for shell, _command in build():
            box = components.command_box(height=96 if not shell else 64)
            copy = self._button(
                translate("RdsPage", "Copy"),
                lambda box=box: self.components.copy_text(box.toPlainText()),
            )
            if shell:  # a box for each shell: each has its Copy under it
                views += [components.label(shell), box, components.row(None, copy)]
            else:
                views.append(box)
            copies.append(copy)
            boxes.append(box)

        def refresh() -> None:
            for box, (_shell, command) in zip(boxes, build(), strict=True):
                box.setPlainText(command)

        run_button = self._button(translate("RdsPage", "Run in KubeScope"), run)
        close = self._button(translate("RdsPage", "Close"))
        # one command: its Copy joins the other buttons
        buttons = [copies[0]] if len(copies) == 1 else []
        return views, [*buttons, run_button, close], close, refresh

    def _button(self, text: str, on_click: Callable[[], None] | None = None) -> Any:
        button = self.components.button(text, on_click=on_click)
        button.setMinimumWidth(120)
        return button

    def _fill_targets(self, combo: Any, hint: Any, found: list[SsmTarget]) -> None:
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
                translate(
                    "RdsPage",
                    "{count} instances can be reached; the first is in the VPC of "
                    "the database.",
                ).format(count=len(found))
            )
        else:
            hint.setText(
                translate(
                    "RdsPage",
                    "No instance in the VPC of the database can be reached by "
                    "Systems Manager; type the ID of one.",
                )
            )
