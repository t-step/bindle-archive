# Bindle — convenience entrypoints. The scripts in bin/ are the source of
# truth; these targets just save keystrokes.
.PHONY: check test install doctor hooks release new help

help:
	@echo "make check              run hygiene checks (bin/check.sh)"
	@echo "make test               run install.sh + check.sh tests"
	@echo "make install            install default Claude surfaces (bin/install.sh)"
	@echo "make doctor             diagnose an installation, read-only (bin/doctor.sh)"
	@echo "make hooks              enable git hooks (bin/install-hooks.sh)"
	@echo "make new ARGS=\"skill x\"  scaffold a new item (bin/new.sh)"
	@echo "make release BUMP=minor cut a release (bin/release.sh)"

check:
	bin/check.sh

test:
	bin/test-install.sh
	bin/test-check.sh
	bin/test-check-frontmatter.sh
	bin/test-doctor.sh
	bin/test-notes-home.sh
	bin/test-nested-notes-guard.sh
	bin/test-session-context.sh
	bin/test-session-hooks.sh
	bin/test-install-session-hooks.sh

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
