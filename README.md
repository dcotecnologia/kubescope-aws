# KubeScope AWS

AWS for [KubeScope](https://github.com/dcotecnologia/kubescope): the **RDS** databases of the AWS account
of the selected cluster, in any region, with their details and logs, and a port forward to a database
through AWS Systems Manager (only in the write mode).

It is an **extension**: in **Settings → Extensions** you can install it from this repository, and
uninstall it. It appears as **AWS → RDS → Instances** in the side menu while AWS is in use (an AWS account
plugged in, an SSO profile, or an EKS cluster selected).

It depends on the [KubeScope SDK](https://github.com/dcotecnologia/kubescope-sdk) and on Qt, and on
nothing else of KubeScope; a test keeps its imports to `kubescope.sdk` and itself.

## Permissions

| Permission | Why |
| ---------- | --- |
| `aws.read` | Read RDS, EC2, EKS and Systems Manager with the profile or keys of the context. It cannot change anything: the app refuses every verb that is not a read |
| `forward` | Start the port forward to a database (the app checks it is the Systems Manager session it builds, and only in the write mode) |
| `ui.page` | Add its page to the side menu |
| `ui.window` | Show details and logs in tabs, messages and the select of a log file |

## Install

In KubeScope, open **Settings → Extensions → Install from GitHub...** and type
`dcotecnologia/kubescope-aws`, or **Install from a folder...** and pick the `kubescope-extension.toml`
of a clone of this repository.

## Develop

```text
workspace/
├── kubescope/        # the app
├── kubescope-sdk/    # the SDK
└── kubescope-aws/    # this project
```

```bash
uv sync
uv run pytest tests/test_x.py
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run python tools/i18n.py   # keep languages/ in step with the texts of the code
```

To see your changes in the app as you make them, tick **Development mode** in **Settings → Extensions**
and install this folder: the app runs it in place and reloads it when a file changes.

## Layout

| Path | What it is |
| ---- | ---------- |
| `kubescope-extension.toml` | The manifest the app reads before installing |
| `src/kubescope/aws/` | The code: `rds.py` and `ssm.py` read, `rds_page.py` is the page |
| `languages/` | The translations of its texts, one file per language; they join the app's while it runs |
| `tests/` | The tests |
