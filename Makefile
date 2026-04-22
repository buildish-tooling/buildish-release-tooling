# Copyright 2026 The Buildish Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

UV_RUN = uv run --frozen --group dev
PYTEST_WORKERS ?= 4
RELEASE_LEGAL_OUT_DIR ?= dist-release-legal/preliminary
RELEASE_LEGAL_DETAILS_OUT_DIR ?= dist/release-legal-preliminary
HELP_TARGETS = $(MAKEFILE_LIST)
HELP_PUBLIC_CHECK_TARGETS := lint typecheck test rat release-legal-preliminary-check check schemas
HELP_PUBLIC_RELEASE_TARGETS := release-legal-preliminary

.PHONY: help lint typecheck test rat release-legal-preliminary-check check schemas release-legal-preliminary

help: ## Show curated Make targets for buildish-release-tooling.
	@desc_for() { awk -v target="$$1" 'BEGIN {FS = ":.*## "} $$1 == target {print $$2; exit}' $(HELP_TARGETS); }; \
	print_section() { title="$$1"; shift; printf "\n%s\n" "$$title"; for target in "$$@"; do printf "  %-20s %s\n" "$$target" "$$(desc_for "$$target")"; done; }; \
	printf "Available targets:\n"; \
	print_section "Checks:" $(HELP_PUBLIC_CHECK_TARGETS); \
	print_section "Release helpers:" $(HELP_PUBLIC_RELEASE_TARGETS)

lint: ## Run Ruff checks for the Python sources and tests.
	$(UV_RUN) ruff check src tests

typecheck: ## Run Mypy across the repository.
	$(UV_RUN) python -m mypy

rat: ## Run Apache RAT license checks.
	tools/rat/rat-check.sh

release-legal-preliminary-check: ## Verify the checked-in preliminary release-legal artifacts are up to date.
	@tmp_dir="$$(mktemp -d)"; \
	trap 'rm -rf "$$tmp_dir"' EXIT; \
	$(UV_RUN) python3 -m buildish_release_tooling.legal.release_legal --output-dir "$$tmp_dir/tracked" --details-output-dir "$$tmp_dir/details" >/dev/null; \
	if [ ! -d "$(RELEASE_LEGAL_OUT_DIR)" ]; then \
		echo "Missing checked-in preliminary release-legal artifacts under $(RELEASE_LEGAL_OUT_DIR)." >&2; \
		echo "Run 'make release-legal-preliminary' and commit the results." >&2; \
		exit 1; \
	fi; \
	diff -ru "$(RELEASE_LEGAL_OUT_DIR)" "$$tmp_dir/tracked"

test: ## Run the Python unit and integration test suite.
	$(UV_RUN) python -m pytest tests -n $(PYTEST_WORKERS) -q

check: lint typecheck test rat release-legal-preliminary-check ## Run lint, type checks, tests, RAT, and legal-artifact verification.

schemas: ## Regenerate checked-in JSON Schema files and the Markdown model reference.
	$(UV_RUN) python -m buildish_release_tooling.docs.schema_export --output-dir site/pages/schemas

release-legal-preliminary: ## Generate preliminary wheel legal drafts from the runtime dependency set.
	$(UV_RUN) python3 -m buildish_release_tooling.legal.release_legal --output-dir $(RELEASE_LEGAL_OUT_DIR) --details-output-dir $(RELEASE_LEGAL_DETAILS_OUT_DIR)
