PYTHON := python3
include /workspace/config.mk
export RX_OJ_BUILD = $(BUILD)
export RX_OJ_SEMANTIC = $(SEMANTIC)
export RX_OJ_CODEGEN = $(CODEGEN)

.PHONY: rx-oj-commands
rx-oj-commands:
	@/usr/bin/python3 -c 'import json,os; print(json.dumps({k: os.environ.get("RX_OJ_" + k.upper(), "") for k in ("build", "semantic", "codegen")}))'
