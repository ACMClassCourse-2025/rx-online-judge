# Adapt these flags to your own compiler's interface.
BUILD = g++ -std=c++23 -O2 -o compiler main.cpp && cp runtime.s {runtime}
SEMANTIC = ./compiler semantic {source}
IR = ./compiler ir {source} {output}
CODEGEN = ./compiler codegen {source} {output}
