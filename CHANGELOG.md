# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Migration of old polls no longer discards events due to date collisions on `0001-01-01`.
  The real event date is now recovered from the poll question text (`When: YYYY-MM-DD HH:MM`).
  For the rare case where parsing fails, duplicate events receive unique surrogate keys so
  all poll statistics are preserved.

### Changed
- Docker images now include OCI metadata labels: `version`, `revision`, `created`, `source`, `title`
  - Release images: `version` is the clean semver (e.g. `1.0.2`)
  - Edge/PR images: `version` includes the short commit SHA (e.g. `1.0.2-abc1234`)
- Removed redundant `nightly` Docker tag; `edge` is the single rolling non-release tag
