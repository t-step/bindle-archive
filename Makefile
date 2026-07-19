# Bindle — convenience entrypoints. The scripts in bin/ are the source of
# truth; these targets just save keystrokes.
.PHONY: check test install doctor hooks release new manifest docs help

help:
	@echo "make check              run hygiene checks (bin/check.sh)"
	@echo "make test               run install.sh + check.sh tests"
	@echo "make install            install default Claude surfaces (bin/install.sh)"
	@echo "make doctor             diagnose an installation, read-only (bin/doctor.sh)"
	@echo "make hooks              enable git hooks (bin/install-hooks.sh)"
	@echo "make new ARGS=\"skill x\"  scaffold a new item (bin/new.sh)"
	@echo "make release BUMP=minor cut a release (bin/release.sh)"
	@echo "make manifest           regenerate install-manifest.tsv from capabilities.json"
	@echo "make docs               regenerate README/provider-interop generated tables"

check:
	bin/check.sh

# Suites are discovered, not listed: any tracked bin/test-*.sh runs. Adding a
# suite to this list by hand is what let eleven of them drift out of the commit
# gate (#256, #257).
test:
	bin/run-test-suites.sh

install:
	bin/install.sh

doctor:
	bin/doctor.sh

hooks:
	bin/install-hooks.sh

new:
	bin/new.sh $(ARGS)

release:
	bin/release.sh $(BUMP)

manifest:
	python3 bin/check-inventory.py --emit-manifest
	@echo "wrote install-manifest.tsv"

docs:
	python3 bin/check-inventory.py --emit-docs
