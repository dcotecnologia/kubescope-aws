"""What is read of Amazon RDS, through the AWS account of a cluster context."""

from typing import Any

from kubescope.sdk import AwsAccess
from kubescope.sdk.errors import ClusterError
from kubescope.sdk.models import RdsInstance, RdsLogFile

LOG_LINES = 1000  # what is read of the end of a log file


def instances(aws: AwsAccess, context: str, region: str = "") -> list[RdsInstance]:
    """The RDS instances of the account of an EKS context in a region (the one
    of the context unless another is given)."""
    scope = aws.scope(context)
    region = region or scope.region
    document = aws.run(context, ["rds", "describe-db-instances"], region)
    found = []
    for item in document.get("DBInstances") or []:
        if not isinstance(item, dict):
            continue
        endpoint = item.get("Endpoint")
        port = endpoint.get("Port") if isinstance(endpoint, dict) else None
        storage = item.get("AllocatedStorage")
        group = item.get("DBSubnetGroup")
        found.append(
            RdsInstance(
                scope.account,
                region,
                str(item.get("DBInstanceIdentifier", "")),
                str(item.get("Engine", "")),
                str(item.get("EngineVersion", "")),
                str(item.get("DBInstanceClass", "")),
                str(item.get("DBInstanceStatus", "")),
                storage if isinstance(storage, int) else 0,
                item.get("MultiAZ") is True,
                str(endpoint.get("Address") or "")
                if isinstance(endpoint, dict)
                else "",
                port if isinstance(port, int) else 0,
                scope.profile,
                str(group.get("VpcId") or "") if isinstance(group, dict) else "",
            )
        )
    return sorted(found, key=lambda row: row.identifier)


def details(
    aws: AwsAccess, context: str, identifier: str, region: str = ""
) -> dict[str, Any]:
    """Everything `aws rds describe-db-instances` says about one instance."""
    document = aws.run(
        context,
        ["rds", "describe-db-instances", "--db-instance-identifier", identifier],
        region,
    )
    items = [
        item for item in document.get("DBInstances") or [] if isinstance(item, dict)
    ]
    if not items:
        raise ClusterError(f"RDS instance {identifier} was not found")
    return items[0]


def log_files(
    aws: AwsAccess, context: str, identifier: str, region: str = ""
) -> list[RdsLogFile]:
    """The log files of an instance, the one written last first."""
    document = aws.run(
        context,
        ["rds", "describe-db-log-files", "--db-instance-identifier", identifier],
        region,
    )
    files = []
    for item in document.get("DescribeDBLogFiles") or []:
        if not (isinstance(item, dict) and item.get("LogFileName")):
            continue
        size, written = item.get("Size"), item.get("LastWritten")
        files.append(
            RdsLogFile(
                str(item["LogFileName"]),
                size if isinstance(size, int) else 0,
                written if isinstance(written, int) else 0,
            )
        )
    return sorted(files, key=lambda row: (-row.written, row.name))


def log(
    aws: AwsAccess, context: str, identifier: str, name: str, region: str = ""
) -> str:
    """The last lines of a log file of an instance."""
    document = aws.run(
        context,
        [
            "rds",
            "download-db-log-file-portion",
            "--db-instance-identifier",
            identifier,
            "--log-file-name",
            name,
            "--number-of-lines",
            str(LOG_LINES),
            "--no-paginate",
        ],
        region,
    )
    return str(document.get("LogFileData") or "")
