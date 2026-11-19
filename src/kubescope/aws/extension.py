"""What the app calls to run the AWS extension: its page in the side menu."""

from kubescope.sdk import Context
from PySide6.QtCore import QCoreApplication

from kubescope.aws.rds_page import RdsPage


def activate(ctx: Context) -> None:
    ctx.add_page(
        "AWS",
        "RDS",
        QCoreApplication.translate("AwsExtension", "Instances"),
        lambda: RdsPage(ctx),
        subtitle=QCoreApplication.translate(
            "AwsExtension", "Databases of the AWS account of the selected context"
        ),
        visible=lambda: ctx.aws.uses_aws(ctx.current_context),
    )
