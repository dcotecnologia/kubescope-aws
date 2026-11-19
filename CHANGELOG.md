# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- The tests check the coverage, which stays at 100% as in KubeScope, and the pipeline publishes the badge
- A pipeline that lints, type-checks and tests on every pull request, and a release pipeline for the tags `v*` that also prints the hash KubeScope pins
- A professional README, a Makefile, and the contributing and security guides

## [1.0.1] - 2026-11-19

### Fixed

- The refresh button looked unlike the other pages: it is now the one of the header of the window, and the page no longer draws its own

## [1.0.0] - 2026-11-19

### Added

- The RDS instances of the AWS account of the selected cluster, in any region, with search, details, logs and the port forward through Systems Manager, as an extension written against the KubeScope SDK only

[Unreleased]: https://github.com/dcotecnologia/kubescope-aws/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/dcotecnologia/kubescope-aws/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/dcotecnologia/kubescope-aws/releases/tag/v1.0.0
