"""Judge-owned LLVM IR lowering contract. Commands run only in the Clang sandbox."""

import re


def clang_command(source="/case/program.ll", output="/output/program.s"):
    return [
        "clang-22",
        "-S",
        "-x",
        "ir",
        source,
        "-o",
        output,
        "--target=riscv32-unknown-none-elf",
        "-march=rv32im",
        "-mabi=ilp32",
        "-O0",
        "-mllvm",
        "-riscv-no-aliases",
    ]


def strip_debug(assembly: bytes) -> bytes:
    # LTO IR can carry imported DWARF; REIMU does not accept its data directives.
    result = []
    debug_section = False
    for line in assembly.splitlines(keepends=True):
        section = re.match(rb'\s*\.section\s+"?([^",\s]+)', line)
        if section:
            debug_section = section[1].startswith(b".debug_")
        elif re.match(rb"\s*\.(text|data|sdata|rodata|bss|sbss)\b", line):
            debug_section = False
        if not debug_section:
            result.append(line)
    return b"".join(result)
