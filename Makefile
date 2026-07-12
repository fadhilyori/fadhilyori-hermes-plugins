PLUGINS := $(wildcard */plugin.yaml)
PLUGIN_DIRS := $(dir $(PLUGINS))

.PHONY: help test test-all list clean

help:
	@echo "Available targets:"
	@echo "  make test PLUGIN=<name>         - Run tests for a single plugin"
	@echo "  make test-all                   - Run tests for all plugins"
	@echo "  make list                       - List available plugins"
	@echo "  make clean                      - Remove test artifacts (__pycache__, *.db)"

list:
	@echo "Available plugins:"
	@$(foreach d,$(PLUGIN_DIRS),echo "  - $(d)";)

test:
ifndef PLUGIN
	$(error PLUGIN is required. Usage: make test PLUGIN=time_awareness)
endif
	uv run python3 -m $(PLUGIN).test -v

test-all:
	@status=0; \
	for d in $(PLUGIN_DIRS); do \
		plugin=$${d%/}; \
		echo "==> Testing $$plugin"; \
		uv run python3 -m $$plugin.test -v || status=1; \
		echo; \
	done; \
	exit $$status

clean:
	@find $(PLUGIN_DIRS) -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find $(PLUGIN_DIRS) -type f \( -name "*.db" -o -name "*.db-wal" -o -name "*.db-shm" \) -delete 2>/dev/null || true
	@echo "Cleaned."
