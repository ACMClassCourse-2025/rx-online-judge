# Demonstration compiler for tests/fixtures/suites only; this is not a full Rx compiler.
BUILD = python3 -m py_compile compiler.py
SEMANTIC = python3 compiler.py semantic {source}
CODEGEN = python3 compiler.py codegen {source} {output}
