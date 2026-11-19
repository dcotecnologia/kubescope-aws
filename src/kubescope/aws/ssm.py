"""A port forward to a database through an EC2 instance with AWS Systems
Manager: the instances that can be used and the command that forwards."""

import json
import re
import shlex
import subprocess
import sys

from kubescope.sdk import AwsAccess
from kubescope.sdk.models import SsmTarget

_POWERSHELL_SAFE = re.compile(r"[A-Za-z0-9_./:=@%+,-]+")


def targets(
    aws: AwsAccess, context: str, vpc: str, region: str = ""
) -> list[SsmTarget]:
    """The EC2 instances of the account that Systems Manager can reach, the
    ones in the `vpc` of a database first: the ones a port can be forwarded
    through."""
    information = aws.run(context, ["ssm", "describe-instance-information"], region)
    online = [
        str(item["InstanceId"])
        for item in information.get("InstanceInformationList") or []
        if isinstance(item, dict)
        and item.get("PingStatus") == "Online"
        and str(item.get("InstanceId", "")).startswith("i-")  # not a hybrid server
    ]
    if not online:
        return []
    reservations = aws.run(
        context, ["ec2", "describe-instances", "--instance-ids", *online], region
    ).get("Reservations")
    found = []
    for reservation in reservations or []:
        for item in (reservation or {}).get("Instances") or []:
            tags = {
                tag.get("Key"): tag.get("Value")
                for tag in item.get("Tags") or []
                if isinstance(tag, dict)
            }
            where = str(item.get("VpcId") or "")
            found.append(
                SsmTarget(
                    str(item.get("InstanceId", "")),
                    str(tags.get("Name") or ""),
                    where,
                    bool(vpc) and where == vpc,
                )
            )
    return sorted(found, key=lambda row: (not row.same_vpc, row.name, row.instance_id))


def forward_arguments(
    instance: str,
    host: str,
    remote: int,
    local: int,
    region: str,
    profile: str = "",
) -> list[str]:
    """The AWS CLI command that forwards a local port to a database (`host`,
    `remote`) through an EC2 instance with AWS Systems Manager."""
    parameters = json.dumps(
        {"host": [host], "portNumber": [str(remote)], "localPortNumber": [str(local)]},
        separators=(",", ":"),
    )
    return [
        "aws",
        "ssm",
        "start-session",
        "--target",
        instance or "<EC2-INSTANCE-ID>",
        "--document-name",
        "AWS-StartPortForwardingSessionToRemoteHost",
        "--parameters",
        parameters,
        "--region",
        region,
        *(["--profile", profile] if profile else []),
    ]


def _powershell_quote(argument: str) -> str:
    if _POWERSHELL_SAFE.fullmatch(argument):
        return argument
    return "'" + argument.replace("'", "''") + "'"


def forward_commands(
    instance: str,
    host: str,
    remote: int,
    local: int,
    region: str,
    profile: str = "",
) -> list[tuple[str, str]]:
    """The complete command, for the person to run in their own terminal, as
    (shell, command) pairs: one for a POSIX shell, and on Windows one for
    PowerShell and one for cmd."""
    arguments = forward_arguments(instance, host, remote, local, region, profile)
    if sys.platform != "win32":
        return [("", shlex.join(arguments))]
    powershell = " ".join(_powershell_quote(argument) for argument in arguments)
    return [("PowerShell", powershell), ("cmd", subprocess.list2cmdline(arguments))]
