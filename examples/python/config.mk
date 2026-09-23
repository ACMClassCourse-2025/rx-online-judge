# Demonstration compiler for tests/fixtures/suites only; this is not a full Rx compiler.
BUILD = python3 -m py_compile compiler.py && cp runtime.s {runtime}
SEMANTIC = python3 compiler.py semantic {source}
IR = python3 compiler.py ir {source} {output}
CODEGEN = python3 compiler.py codegen {source} {output}
