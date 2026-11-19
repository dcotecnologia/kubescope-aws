import pytest
from kubescope.sdk.errors import ClusterError

from kubescope.aws import rds, ssm
from tests.conftest import DATABASE


def test_the_instances_of_the_account_in_a_region_are_read(ctx) -> None:
    ctx.aws.answers[("rds", "describe-db-instances")] = {
        "DBInstances": [
            {**DATABASE, "DBInstanceIdentifier": "zeta"},
            DATABASE,
            "not an instance",
            {"DBInstanceIdentifier": "bare"},
        ]
    }

    found = rds.instances(ctx.aws, "ctx", "sa-east-1")

    assert [one.identifier for one in found] == ["bare", "orders", "zeta"]
    orders = found[1]
    assert (orders.engine, orders.version, orders.size) == (
        "postgres",
        "15.4",
        "db.t3.micro",
    )
    assert (orders.storage, orders.multi_az, orders.port) == (20, True, 5432)
    assert (orders.endpoint, orders.vpc) == ("orders.example.com", "vpc-1")
    assert (orders.account, orders.profile, orders.region) == (
        "123456789012",
        "work",
        "sa-east-1",
    )
    assert found[0].endpoint == "" and found[0].storage == 0 and not found[0].multi_az
    assert ctx.aws.asked == [("ctx", ["rds", "describe-db-instances"], "sa-east-1")]


def test_without_a_region_the_one_of_the_context_is_used(ctx) -> None:
    ctx.aws.answers[("rds", "describe-db-instances")] = {"DBInstances": [DATABASE]}

    assert rds.instances(ctx.aws, "ctx")[0].region == "us-east-1"


def test_the_details_are_what_the_cli_says_about_one_instance(ctx) -> None:
    ctx.aws.answers[("rds", "describe-db-instances")] = {"DBInstances": [DATABASE]}

    assert rds.details(ctx.aws, "ctx", "orders", "us-east-1") == DATABASE
    assert ctx.aws.asked[0][1][-2:] == ["--db-instance-identifier", "orders"]


def test_an_instance_that_is_not_there_is_not_found(ctx) -> None:
    with pytest.raises(ClusterError, match="was not found"):
        rds.details(ctx.aws, "ctx", "ghost")


def test_the_log_files_come_with_the_last_written_first(ctx) -> None:
    ctx.aws.answers[("rds", "describe-db-log-files")] = {
        "DescribeDBLogFiles": [
            {"LogFileName": "old.log", "Size": 10, "LastWritten": 1},
            {"LogFileName": "new.log", "Size": 20, "LastWritten": 5},
            {"Size": 1},
            "x",
            {"LogFileName": "odd.log", "Size": "big", "LastWritten": None},
        ]
    }

    files = rds.log_files(ctx.aws, "ctx", "orders")

    assert [one.name for one in files] == ["new.log", "old.log", "odd.log"]
    assert files[2].size == 0 and files[2].written == 0


def test_a_log_is_the_end_of_the_file(ctx) -> None:
    ctx.aws.answers[("rds", "download-db-log-file-portion")] = {"LogFileData": "line\n"}

    assert rds.log(ctx.aws, "ctx", "orders", "error.log", "us-east-1") == "line\n"
    command = ctx.aws.asked[0][1]
    assert command[command.index("--number-of-lines") + 1] == str(rds.LOG_LINES)
    assert ctx.aws.asked[0][1][0:2] == ["rds", "download-db-log-file-portion"]
    assert rds.log(ctx.aws, "ctx", "orders", "x") == "line\n"
    ctx.aws.answers[("rds", "download-db-log-file-portion")] = {}
    assert rds.log(ctx.aws, "ctx", "orders", "x") == ""


def test_the_instances_a_forward_can_go_through_come_with_the_same_vpc_first(
    ctx,
) -> None:
    ctx.aws.answers[("ssm", "describe-instance-information")] = {
        "InstanceInformationList": [
            {"InstanceId": "i-aaa", "PingStatus": "Online"},
            {"InstanceId": "i-bbb", "PingStatus": "Online"},
            {"InstanceId": "i-off", "PingStatus": "ConnectionLost"},
            {"InstanceId": "mi-hybrid", "PingStatus": "Online"},
        ]
    }
    ctx.aws.answers[("ec2", "describe-instances")] = {
        "Reservations": [
            {
                "Instances": [
                    {"InstanceId": "i-aaa", "VpcId": "vpc-2", "Tags": []},
                    {
                        "InstanceId": "i-bbb",
                        "VpcId": "vpc-1",
                        "Tags": [{"Key": "Name", "Value": "bastion"}],
                    },
                ]
            }
        ]
    }

    found = ssm.targets(ctx.aws, "ctx", "vpc-1", "us-east-1")

    assert [(one.instance_id, one.name, one.same_vpc) for one in found] == [
        ("i-bbb", "bastion", True),
        ("i-aaa", "", False),
    ]
    assert ctx.aws.asked[1][1] == [
        "ec2",
        "describe-instances",
        "--instance-ids",
        "i-aaa",
        "i-bbb",
    ]


def test_without_an_instance_that_is_online_nothing_more_is_asked(ctx) -> None:
    ctx.aws.answers[("ssm", "describe-instance-information")] = {}

    assert ssm.targets(ctx.aws, "ctx", "vpc-1") == []
    assert len(ctx.aws.asked) == 1


def test_the_forward_command_names_the_instance_the_database_and_the_ports() -> None:
    command = ssm.forward_arguments(
        "i-0abc", "db.example.com", 5432, 15432, "us-east-1", "work"
    )

    assert command[:6] == [
        "aws",
        "ssm",
        "start-session",
        "--target",
        "i-0abc",
        "--document-name",
    ]
    assert "AWS-StartPortForwardingSessionToRemoteHost" in command
    assert '"portNumber":["5432"]' in command[command.index("--parameters") + 1]
    assert command[-2:] == ["--profile", "work"]
    assert "--profile" not in ssm.forward_arguments("i-1", "h", 1, 2, "r")
    assert "<EC2-INSTANCE-ID>" in ssm.forward_arguments("", "h", 1, 2, "r")


def test_the_command_is_quoted_for_the_shell_of_the_system(monkeypatch) -> None:
    monkeypatch.setattr(ssm.sys, "platform", "linux")
    [(shell, command)] = ssm.forward_commands("i-1", "h", 3306, 13306, "sa-east-1")

    assert shell == "" and command.startswith("aws ssm start-session --target i-1")

    monkeypatch.setattr(ssm.sys, "platform", "win32")
    shells = dict(ssm.forward_commands("i-1", "h", 3306, 13306, "sa-east-1", "my work"))

    assert set(shells) == {"PowerShell", "cmd"}
    assert "'my work'" in shells["PowerShell"]
