# Copyright 2026 The Apache Software Foundation
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
HELP_TARGETS = $(MAKEFILE_LIST)
HELP_PUBLIC_CHECK_TARGETS := lint typecheck test check

.PHONY: help lint typecheck test check

help: ## Show curated Make targets for buildish-release-tooling.
	@desc_for() { awk -v target="$$1" 'BEGIN {FS = ":.*## "} $$1 == target {print $$2; exit}' $(HELP_TARGETS); }; \
	print_section() { title="$$1"; shift; printf "\n%s\n" "$$title"; for target in "$$@"; do printf "  %-20s %s\n" "$$target" "$$(desc_for "$$target")"; done; }; \
	printf "Available targets:\n"; \
	print_section "Checks:" $(HELP_PUBLIC_CHECK_TARGETS)

lint: ## Run Ruff checks for the Python sources and tests.
	$(UV_RUN) ruff check src tests

typecheck: ## Run Mypy across the repository.
	$(UV_RUN) python -m mypy

rat: ## Run Apache RAT license checks.
	tools/rat/rat-check.sh

test: ## Run the Python unit and integration test suite.
	$(UV_RUN) python -m unittest discover -s tests -p 'test_*.py' -v

check: lint typecheck test rat ## Run lint, type checks, and tests.
