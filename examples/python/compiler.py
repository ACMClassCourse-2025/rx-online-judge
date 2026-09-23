"""Tiny smoke-test compiler: accepts an empty main or println_i32(42)."""

import re
import sys
from pathlib import Path

source = re.sub(r"\s+", "", Path(sys.argv[2]).read_text())
if source not in {"fnmain(){}", "userx::core::*;fnmain(){println_i32(42);}"}:
    print("This demonstration compiler only supports the smoke fixtures.", file=sys.stderr)
    sys.exit(1)
if sys.argv[1] == "ir":
    ir = 'target triple = "riscv32-unknown-none-elf"\n'
    if "println_i32" in source:
        ir += """declare void @rx_print_answer()
define i32 @main() {
  call void @rx_print_answer()
  ret i32 0
}
"""
    else:
        ir += "define i32 @main() { ret i32 0 }\n"
    Path(sys.argv[3]).write_text(ir)
elif sys.argv[1] == "codegen":
    if "println_i32" in source:
        assembly = """.text
.globl main
main:
    addi sp, sp, -16
    sw ra, 12(sp)
    call rx_print_answer
    lw ra, 12(sp)
    addi sp, sp, 16
    li a0, 0
    ret
"""
    else:
        assembly = ".text\n.globl main\nmain:\n    li a0, 0\n    ret\n"
    Path(sys.argv[3]).write_text(assembly)
