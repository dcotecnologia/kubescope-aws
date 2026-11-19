"""AWS for KubeScope: the RDS databases of the account of the selected cluster."""

from kubescope.sdk import Context


def activate(ctx: Context) -> None:
    """What the app calls to run the extension."""
    from kubescope.aws import extension

    extension.activate(ctx)
