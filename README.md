# KubeScope AWS

[![CI](https://github.com/dcotecnologia/kubescope-aws/actions/workflows/ci.yml/badge.svg)](https://github.com/dcotecnologia/kubescope-aws/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fdcotecnologia%2Fkubescope-aws%2Fbadges%2Fcoverage.json)](https://github.com/dcotecnologia/kubescope-aws/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/dcotecnologia/kubescope-aws)](https://github.com/dcotecnologia/kubescope-aws/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.15](https://img.shields.io/badge/python-3.15-3776AB.svg?logo=python&logoColor=white)](pyproject.toml)
[![Qt for Python](https://img.shields.io/badge/Qt-PySide6-41CD52.svg?logo=qt&logoColor=white)](https://doc.qt.io/qtforpython-6/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-D7FF64.svg?logo=ruff&logoColor=black)](https://docs.astral.sh/ruff/)
[![KubeScope extension](https://img.shields.io/badge/KubeScope-extension-326CE5.svg?logo=kubernetes&logoColor=white)](https://github.com/dcotecnologia/kubescope)
[![AWS](https://img.shields.io/badge/AWS-RDS-FF9900.svg?logo=amazonwebservices&logoColor=white)](https://aws.amazon.com/rds/)

AWS for [KubeScope](https://github.com/dcotecnologia/kubescope): look at the **RDS** databases of the AWS
account of the selected cluster, in any region, with their details and logs, and open a port forward to a
database through AWS Systems Manager.

It is an **extension** written against the [KubeScope SDK](https://github.com/dcotecnologia/kubescope-sdk)
and nothing else of the app. KubeScope recommends it in **Settings → Extensions**; it is not installed until
you press **Install**, and you can uninstall it at any time.

## What it does

- **Lists the instances** of the account of the cluster context: name, engine, version, class, status,
  storage, Multi-AZ, region, account and endpoint, with the status drawn as a badge.
- **Any region.** It starts in the region of the context, and a select changes it.
- **Searches** every column, with *match case* and *regular expression* switches.
- **Details.** Double-click an instance, or right-click → **Details**, for everything the AWS CLI says about
  it, in a Details tab.
- **Logs.** Right-click → **Logs** to pick a log file and read the end of it in a Logs tab, with a refresh
  button.
- **Port forward.** With the write mode on, right-click → **Forward with SSM** shows the
  `aws ssm start-session` command that forwards a local port to the database through an EC2 instance that
  Systems Manager can reach, ready to copy, or to run from KubeScope. The instance, region and profile come
  filled in, and the instances in the VPC of the database come first.

The page appears as **AWS → RDS → Instances** in the side menu while AWS is in use: an AWS account plugged in
under **Settings → Integrations**, an AWS SSO profile, or an EKS cluster selected. Its refresh button is the
one of the header of the window.

## Requirements

- KubeScope 1.12 or newer (the extension API `0`).
- The [AWS CLI](https://docs.aws.amazon.com/cli/) installed, and for the forward its
  [Session Manager plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html).
- An account that is allowed to `rds:Describe*`, and for the forward `ssm:StartSession`.

## Install

In KubeScope open **Settings → Extensions** and either:

- press **Install** on the **AWS** card, or
- **Install from GitHub...** and type `dcotecnologia/kubescope-aws`, or
- **Install from a folder...** and pick the `kubescope-extension.toml` of a clone of this repository.

A dialog shows where it comes from, its permissions and the sha256 of its content before anything of it runs.

## Permissions

| Permission | Why |
| ---------- | --- |
| `aws.read` | Read RDS, EC2, EKS and Systems Manager with the profile or keys of the context. It **cannot change anything**: the app refuses every verb that is not a read, and every option that would move the request to another account, region or server |
| `forward` | Start the port forward to a database. The app checks that it is the Systems Manager session it builds, and only in the write mode |
| `ui.page` | Add its page to the side menu |
| `ui.window` | Show details and logs in tabs, messages and the select of a log file |

The keys of your account never reach the extension: it asks the app to run the AWS CLI.

## Develop

```text
workspace/
├── kubescope/        # the app
├── kubescope-sdk/    # the SDK
└── kubescope-aws/    # this project
```

```bash
make setup                          # dependencies and the pre-commit hook
make test FILE=tests/test_page.py   # one test file; `make test` runs them all
make lint typecheck
make i18n                           # keep languages/ in step with the texts of the code
```

To see your changes in the app as you make them, tick **Development mode** in **Settings → Extensions** and
install this folder: the app runs it in place and reloads it when a file changes.

A test (`tests/test_independence.py`) keeps its imports to `kubescope.sdk` and itself; another
(`tests/test_in_the_app.py`) runs it in the real window of the app, which is a development dependency only.

### Layout

| Path | What it is |
| ---- | ---------- |
| `kubescope-extension.toml` | The manifest the app reads before installing |
| `src/kubescope/aws/extension.py` | `activate(ctx)`: the page in the side menu |
| `src/kubescope/aws/rds.py`, `ssm.py` | What is read of RDS, and the Systems Manager forward |
| `src/kubescope/aws/rds_page.py` | The page: table, search, region, banner, menu and the forward dialog |
| `src/kubescope/aws/badge.py` | The status drawn as a badge |
| `languages/` | The translations of its texts, one file per language; they join the app's while it runs |
| `tests/` | The tests |

## License

MIT. See [LICENSE](LICENSE).
