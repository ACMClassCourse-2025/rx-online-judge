.text
.globl rx_print_answer
rx_print_answer:
    addi sp, sp, -16
    sw ra, 12(sp)
    la a0, rx_message
    call puts
    lw ra, 12(sp)
    addi sp, sp, 16
    ret
.data
rx_message:
    .asciz "42"
