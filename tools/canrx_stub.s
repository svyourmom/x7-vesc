.syntax unified
.thumb
.text
.global stub
stub:
    ldr   r0, =0x20008208      @ ring mutex
    bl    lock
    ldr   r3, =0x2000a0bc      @ &write_index
    ldr   r1, [r3]             @ idx
    ldr   r0, =0x2000a0c0      @ ring base
    movs  r2, #20
    mla   r0, r1, r2, r0       @ entry = ring + idx*20
    adds  r1, r1, #1
    cmp   r1, #100
    bne   1f
    movs  r1, #0
1:  str   r1, [r3]             @ *write_index = (idx+1)%100
    movs  r2, #0
    str   r2, [r0, #0]         @ word0 = 0
    movs  r2, #0x28
    str   r2, [r0, #4]         @ word1 = IDE|DLC8
    ldrb  r1, [r6, #1]         @ eid BE from packet[1..4]
    ldrb  r2, [r6, #2]
    orr   r1, r2, r1, lsl #8
    ldrb  r2, [r6, #3]
    orr   r1, r2, r1, lsl #8
    ldrb  r2, [r6, #4]
    orr   r1, r2, r1, lsl #8
    str   r1, [r0, #8]         @ word2 = eid
    movs  r1, #0
2:  adds  r3, r6, r1
    ldrb  r2, [r3, #5]         @ packet[5+i]
    adds  r3, r0, r1
    strb  r2, [r3, #12]        @ entry[12+i]
    adds  r1, r1, #1
    cmp   r1, #8
    bne   2b
    ldr   r0, =0x20008208
    bl    unlock
    ldr   r0, =0x20009dc0
    ldr   r0, [r0]
    movs  r1, #1
    bl    signal
    b.w   exit
    .ltorg
