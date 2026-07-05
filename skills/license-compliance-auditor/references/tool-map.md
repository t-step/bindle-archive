# Tool map: scanners by ecosystem

Reference for `detect_tools.py` and `inventory_repo.py`: which scanner to try per
ecosystem, what it emits, and what to do when it isn't installed.

**The rule: if a scanner is unavailable, record missing coverage plus an install
hint — never guess a license from vibes, a package name, or a README blurb.** A
missing tool becomes a `coverage` entry with `status: not-checked` (or `partial`
if a weaker fallback was used) and an `install_hint`, never a fabricated finding.

## Repo-wide scanners

| Scanner/command | What it emits | Fallback when absent | Install hint |
| --- | --- | --- | --- |
| `scancode-toolkit` (`scancode`) | Deep file-level license/copyright detection across the whole tree, JSON output | Manual `LICENSE`/`COPYING`/header inspection of top-level and vendored dirs | `pipx install scancode-toolkit` |
| `reuse` (REUSE.software) | REUSE-spec compliance report: files missing SPDX headers/license info | Grep for `SPDX-License-Identifier` headers manually; note as `partial` | `pipx install reuse` |
| `licensee` | GitHub's own license-detection heuristic against the root `LICENSE` file | Read the `LICENSE`/`LICENSE.md`/`COPYING` file directly and note the declared license as unverified-by-tool | `gem install licensee` |
| `fosslight` (FOSSLight Scanner) | OSS license/obligation report, useful cross-check for dependency + source scanning | Rely on ecosystem-specific tools below instead | see `https://github.com/fosslight/fosslight_scanner` |

## JS / TypeScript (npm, pnpm, yarn)

| Scanner/command | What it emits | Fallback when absent | Install hint |
| --- | --- | --- | --- |
| `license-checker` (`license-checker-rseidelsohn`) | Per-dependency SPDX license, repository URL, license file path | Parse `package.json` `dependencies`/`devDependencies` + each `node_modules/<pkg>/package.json` `license` field; treat as declared-not-verified | `npm i -g license-checker-rseidelsohn` |
| Lockfile parsing (`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`) | Resolved version + registry source per package, used when a scanner isn't run | N/A — this *is* the fallback path; note it explicitly as `method` in coverage | none needed, always available if a lockfile exists |

## Python (pip, poetry, uv)

| Scanner/command | What it emits | Fallback when absent | Install hint |
| --- | --- | --- | --- |
| `pip-licenses` | Installed-package license table sourced from package metadata (`importlib.metadata`) | Parse `requirements.txt`/`pyproject.toml`/`Pipfile` for pinned packages, note license as `UNKNOWN` unless a vendored `LICENSE` accompanies the package | `pipx install pip-licenses` |
| `poetry show --tree` / `poetry export` | Dependency tree + versions (license itself still needs `pip-licenses` or metadata) | Read `poetry.lock` `[[package]]` blocks for name/version only | `pipx install poetry` |
| `uv pip list` / `uv export` | Same role as poetry, faster resolver | Read `uv.lock` for name/version only | `pipx install uv` |

## Rust (cargo)

| Scanner/command | What it emits | Fallback when absent | Install hint |
| --- | --- | --- | --- |
| `cargo-license` | Per-crate `license` field from `Cargo.toml`/crates.io metadata | Parse `Cargo.lock` for crate name/version, cross-reference crates.io manually if network access is out of scope; otherwise `UNKNOWN` | `cargo install cargo-license` |

## Go (go modules)

| Scanner/command | What it emits | Fallback when absent | Install hint |
| --- | --- | --- | --- |
| `go-licenses` | Per-module license classification by inspecting the module's own `LICENSE` file | Parse `go.mod`/`go.sum` for module paths/versions; license stays `UNKNOWN` without fetching the module source | `go install github.com/google/go-licenses@latest` |

## PHP (composer)

| Scanner/command | What it emits | Fallback when absent | Install hint |
| --- | --- | --- | --- |
| `composer licenses` | Per-package license from `composer.json`/installed package metadata | Parse `composer.json` `require`/`require-dev` and `composer.lock` `packages[].license` directly | install Composer: `https://getcomposer.org/download/` |

## Ruby (bundler)

| Scanner/command | What it emits | Fallback when absent | Install hint |
| --- | --- | --- | --- |
| `license_finder` (or `bundle-license`) | Per-gem license from gemspec metadata | Parse `Gemfile.lock` for gem name/version; check each gem's vendored `LICENSE`/gemspec if vendored under `vendor/bundle` | `gem install license_finder` |

## Java / Kotlin (Maven, Gradle)

| Scanner/command | What it emits | Fallback when absent | Install hint |
| --- | --- | --- | --- |
| `mvn license:aggregate-add-third-party` (license-maven-plugin) | Third-party license report aggregated from POM `<licenses>` metadata | Parse `pom.xml` `<dependencies>` and each dependency's shipped POM for `<licenses>`, if resolvable locally | add `org.codehaus.mojo:license-maven-plugin` to the POM |
| `gradle licenseReport` (`com.github.jk1.dependency-license-report`) | Same role for Gradle projects, HTML/JSON/CSV report | Parse `build.gradle`/`build.gradle.kts` dependency blocks and the Gradle lockfile if present | add the `com.github.jk1.dependency-license-report` plugin |

## .NET (NuGet)

| Scanner/command | What it emits | Fallback when absent | Install hint |
| --- | --- | --- | --- |
| `nuget-license` (or `dotnet list package --include-transitive` + metadata) | Per-package license expression/URL from `.nuspec` metadata | Parse `.csproj`/`packages.config`/`*.lock.json` for package name/version; license stays `UNKNOWN` without the `.nuspec` | `dotnet tool install --global nuget-license` |

## SBOM emission (optional, when tooling exists)

Where a CycloneDX generator is already installed or trivially available for the
detected ecosystem, note it as an optional coverage enhancement rather than a
requirement — it does not replace license detection, but its `licenses`
component adds a cross-checkable artifact:

- `cyclonedx-npm` (JS/TS), `cyclonedx-py` (Python), `cargo cyclonedx` (Rust),
  `cyclonedx-gomod` (Go), `cyclonedx-maven-plugin` (Java), `CycloneDX.Tool`
  (dotnet CLI, `.NET`).
- If none is installed, do not install one automatically — record it as a
  coverage gap with an install hint, same as any other missing scanner.
