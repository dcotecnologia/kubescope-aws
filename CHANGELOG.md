# Changelog

All notable changes to this project will be documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.3.0] - 2026-11-25

### Changed

- The manifest says the newest KubeScope the extension works with (`max_app`, 3.0.0), so a KubeScope newer than that neither installs nor offers it, and keeps the version made for it by @danilogco
- The log files of an instance are picked in a table (file, size and when it was written) that narrows as you type and by a range of dates, instead of a select (needs KubeScope 2.10 and the SDK 1.13, with `Ui.pick_row`) by @danilogco

## [1.2.0] - 2026-11-25

### Changed

- The extension imports nothing from `PySide6`, in its code or in its tests: its page is a plain object that holds its widget, and every widget, timer, icon, text and test helper comes from the SDK (`ctx.ui.components`, `translate`) by @danilogco
- The page is built with the elements of the app, through `ctx.ui.components` (SDK 1.12 and KubeScope 2.9): its table, the sorting by a click on a header, the badges, the buttons, the search box and the selects and fields, so it has no copy of them by @danilogco

## [1.1.0] - 2026-11-25

### Added

- A click on the header of the instances sorts them, and a second one reverses it, by what the cells mean (the storage as a number), as the lists of the app do; it needs the SDK 1.8 by @danilogco

### Changed

- The badges of the table are as wide as their column, so they line up, and a text that does not fit is cut with an ellipsis by @danilogco

## [1.0.2] - 2026-11-20

### Fixed

- Update the locked dependencies and the pre-commit hooks by @danilogco

## [1.0.1] - 2026-11-19

### Fixed

- Fix the name of the extension to be more friendly and clear by @danilogco

## [1.0.0] - 2026-11-19

### Added

- The RDS instances of the AWS account of the selected cluster, in any region, with search, details, logs and the port forward through Systems Manager, as an extension written against the KubeScope SDK only by @danilogco

[Unreleased]: https://github.com/dcotecnologia/kubescope-aws/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/dcotecnologia/kubescope-aws/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/dcotecnologia/kubescope-aws/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/dcotecnologia/kubescope-aws/compare/v1.0.2...v1.1.0
[1.0.2]: https://github.com/dcotecnologia/kubescope-aws/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/dcotecnologia/kubescope-aws/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/dcotecnologia/kubescope-aws/releases/tag/v1.0.0
