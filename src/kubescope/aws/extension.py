"""What the app calls to run the AWS extension: its page in the side menu."""

from typing import Any

from kubescope.sdk import Context, translate

from kubescope.aws.rds_page import RdsPage


def activate(ctx: Context) -> None:
    pages: list[RdsPage] = []  # the one the window built, once it is opened

    def build() -> Any:
        pages[:] = [RdsPage(ctx)]
        return pages[0].widget

    ctx.add_page(
        "AWS",
        "RDS",
        translate("AwsExtension", "Instances"),
        build,
        subtitle=translate(
            "AwsExtension", "Databases of the AWS account of the selected context"
        ),
        visible=lambda: ctx.aws.uses_aws(ctx.current_context),
        refresh=lambda: pages[0].load() if pages else None,
    )
