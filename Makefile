# claude-kit — convenience entrypoints. The scripts in bin/ are the source of
# truth; these targets just save keystrokes.
.PHONY: check test install hooks release new help

help:
	@echo "make check              run hygiene checks (bin/check.sh)"
	@echo "make test               run install.sh tests (bin/test-install.sh)"
	@echo "make install            link items into ~/.claude (bin/install.sh)"
	@echo "make hooks              enable git hooks (bin/install-hooks.sh)"
	@echo "make new ARGS=\"skill x\"  scaffold a new item (bin/new.sh)"
	@echo "make release BUMP=minor cut a release (bin/release.sh)"

check:
	bin/check.sh

test:
	bin/test-install.sh

install:
	bin/install.sh

hooks:
	bin/install-hooks.sh

new:
	bin/new.sh $(ARGS)

release:
	bin/release.sh $(BUMP)
