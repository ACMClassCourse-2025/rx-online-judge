# Adapt these flags to your own compiler's interface.
BUILD = g++ -std=c++23 -O2 -o compiler main.cpp
SEMANTIC = ./compiler semantic {source}
CODEGEN = ./compiler codegen {source} {output}
