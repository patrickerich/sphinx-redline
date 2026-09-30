SHELL := /usr/bin/env bash

.DEFAULT_GOAL := help

# `source ./sourceme.sh` first to create .venv. Sphinx is always run from the
# project venv so the build uses the versions pinned in requirements.txt, not
# whatever the host (or another active venv) provides.
VENV_PY         := $(CURDIR)/.venv/bin/python
SPHINXBUILD     ?= $(VENV_PY) -m sphinx
SPHINXOPTS      ?= -W --keep-going
DOCS_SOURCE_DIR := $(CURDIR)/docs/source
DOCS_BUILD_DIR  := $(CURDIR)/docs/build
DOCS_PORT       ?= 8000

define VENV_CHECK
@test -x "$(VENV_PY)" || { echo "Error: venv not found. Run: source ./sourceme.sh"; exit 1; }
endef

help: ## list the available targets
	@grep -hE '^[a-zA-Z_%-]+:.*## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*## "} {printf "  %-14s %s\n", $$1, $$2}'

test: ## run the pytest suite
	$(VENV_CHECK)
	@$(VENV_PY) -m pytest

docs: ## build the Sphinx documentation into docs/build/html
	$(VENV_CHECK)
	@$(SPHINXBUILD) -M html "$(DOCS_SOURCE_DIR)" "$(DOCS_BUILD_DIR)" $(SPHINXOPTS)

# Serves exactly what a deploy would publish -- no live-reload injection.
docs-serve: docs ## build the docs and serve them on http://localhost:DOCS_PORT
	@echo "Serving docs at http://localhost:$(DOCS_PORT)/  (Ctrl-C to stop)"
	@$(VENV_PY) -m http.server $(DOCS_PORT) --directory "$(DOCS_BUILD_DIR)/html"

# Authoring loop. No -W here: a half-finished edit should not kill the server.
docs-preview: ## rebuild-on-save docs server with live browser reload
	$(VENV_CHECK)
	@$(VENV_PY) -m sphinx_autobuild --port $(DOCS_PORT) --open-browser \
	   --ignore '$(DOCS_BUILD_DIR)/*' "$(DOCS_SOURCE_DIR)" "$(DOCS_BUILD_DIR)/html"

docs-clean: ## remove the documentation build (docs/build)
	rm -rf "$(DOCS_BUILD_DIR)"

# Any other Sphinx builder, e.g. docs-linkcheck, docs-latexpdf, docs-dirhtml.
# A pattern rule, so it cannot be .PHONY (make skips pattern search for those).
docs-%: ## run Sphinx builder <builder> as docs-<builder>, e.g. docs-linkcheck
	$(VENV_CHECK)
	@$(SPHINXBUILD) -M $* "$(DOCS_SOURCE_DIR)" "$(DOCS_BUILD_DIR)" $(SPHINXOPTS)

.PHONY: help test docs docs-serve docs-preview docs-clean
