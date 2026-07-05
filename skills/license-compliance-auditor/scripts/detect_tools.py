#!/usr/bin/env python3
"""Detect available license/dependency scanners. Never installs anything."""
import json
import shutil
import sys

TOOLS = {
    "scancode": "pipx install scancode-toolkit",
    "reuse": "pipx install reuse",
    "licensee": "gem install licensee",
    "license-checker": "npm i -g license-checker-rseidelsohn",
    "pip-licenses": "pipx install pip-licenses",
    "cargo-license": "cargo install cargo-license",
    "go-licenses": "go install github.com/google/go-licenses@latest",
    "cyclonedx": "see https://cyclonedx.org/tool-center/",
}
PACKAGE_MANAGERS = [
    "npm", "pnpm", "yarn", "pip", "pip3", "poetry", "uv", "cargo", "go",
    "composer", "bundle", "mvn", "gradle", "dotnet",
]


def detect(tools=TOOLS, managers=PACKAGE_MANAGERS, which=shutil.which):
    return {
        "tools": {
            name: {"available": which(name) is not None, "install_hint": hint}
            for name, hint in tools.items()
        },
        "package_managers": {name: which(name) is not None for name in managers},
    }


def main(argv=None):
    print(json.dumps(detect(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
