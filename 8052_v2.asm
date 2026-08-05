; pines:
;   Motor X : P1.0 a P1.3
;   Motor Y : P2.0 a P2.3
;   Motor Z : P2.4 a P2.7
;   LED     : P3.5, parpadea con cada trama valida
;   UART    : P3.0 RXD / P3.1 TXD

BAUD_TIMER EQU 0FDh          ; 9600 baud @ 11.0592 MHz, SMOD=0

; protocolo
HEADER_B  EQU 0AAh
ACK_B     EQU 06h
NACK_B    EQU 15h

C_XP      EQU 01h
C_XN      EQU 02h
C_YP      EQU 03h
C_YN      EQU 04h
C_XY      EQU 07h
C_LINE    EQU 08h
C_ZP      EQU 0Ah
C_ZN      EQU 0Bh             
C_PU      EQU 10h
C_PD      EQU 11h
C_SPD     EQU 12h
C_OFF     EQU 13h
C_PNG     EQU 20h
C_STAT    EQU 21h
C_PENN    EQU 22h
C_SPDZ    EQU 23h
C_ZOFF    EQU 24h
C_ZSET    EQU 25h
C_ZDIR    EQU 26h

FASE_X    EQU 30h
FASE_Y    EQU 31h
FASE_Z    EQU 32h
VEL       EQU 33h             ; ms entre pasos, ejes X e Y
PEN_N     EQU 35h             
Z_POS     EQU 36h             ; 0 = pluma arriba
VEL_Z     EQU 37h             
Z_DIR     EQU 38h             

RX_HDR    EQU 40h
RX_CMD    EQU 41h
RX_PAY    EQU 42h
RX_CHK    EQU 43h
RX_PAY2   EQU 44h             
RX_PAY3   EQU 45h             

X_IS_MAJ  BIT 00h
X_NEG     BIT 01h
Y_NEG     BIT 02h

LED_PIN   BIT P3.5

            ORG  0000h
            LJMP INIT

            ORG  0003h
            RETI
            ORG  000Bh
            RETI
            ORG  0013h
            RETI
            ORG  001Bh
            RETI
            ORG  0023h
            RETI
            ORG  0030h
INIT_UART:
      MOV SCON, #50h
      MOV TH1, #BAUD_TIMER
      MOV TL1, #BAUD_TIMER
      SETB TR1
      CLR TI
      CLR RI
      RET

INIT:
      MOV TMOD, #21h          ; T1 modo 
      MOV PCON, #00h          ; SMOD=0 
      MOV SP,   #4Fh
      MOV FASE_X, #00h
      MOV FASE_Y, #00h
      MOV FASE_Z, #00h
      MOV VEL,    #05h      
      MOV VEL_Z,  #08h      
      MOV PEN_N,  #100       
      MOV Z_POS,  #00h        
      MOV Z_DIR,  #00h        
      MOV P1, #00h
      MOV P2, #00h

      ; fase 0 en los tres motores para que arranquen enclavados
      LCALL WRITE_X
      LCALL WRITE_Y
      LCALL WRITE_Z

      LCALL INIT_UART
      LCALL LED_BLINK_3X
      MOV A, #'O'
      LCALL UART_SEND
      MOV A, #'K'
      LCALL UART_SEND

;   estandar : [AA][CMD][PAY][CHK]          = 4 bytes
;   extendida: [AA][08][DX][DY][FLAGS][CHK] = 6 bytes

MAIN:
      LCALL UART_RECV         ; bloqueo la aa
      CJNE A, #HEADER_B, MAIN ; no es ss
      MOV RX_HDR, A

      LCALL UART_RECV_TO
      JNC MN_C1
      LJMP MAIN               
MN_C1:
      MOV RX_CMD, A
      CJNE A, #C_LINE, MAIN_STD
      LJMP RECV_EXT

MAIN_STD:
      LCALL UART_RECV_TO
      JNC MN_C2
      LJMP MAIN
MN_C2:
      MOV RX_PAY, A

      LCALL UART_RECV_TO
      JNC MN_C3
      LJMP MAIN
MN_C3:
      MOV RX_CHK, A

      ; validar checksum
      MOV A, RX_HDR
      XRL A, RX_CMD
      XRL A, RX_PAY
      XRL A, RX_CHK
      JZ CHK_OK
      LJMP SEND_NACK
CHK_OK:
      CPL LED_PIN           

      MOV A, RX_CMD

      CJNE A, #C_XP, D02
      LJMP CMD_XP
D02:  CJNE A, #C_XN, D03
      LJMP CMD_XN
D03:  CJNE A, #C_YP, D04
      LJMP CMD_YP
D04:  CJNE A, #C_YN, D05
      LJMP CMD_YN
D05:  CJNE A, #C_ZP, D06
      LJMP CMD_ZP
D06:  CJNE A, #C_ZN, D07
      LJMP CMD_ZN
D07:  CJNE A, #C_XY, D08
      LJMP CMD_SXY
D08:  CJNE A, #C_PU, D09
      LJMP CMD_PU
D09:  CJNE A, #C_PD, D10
      LJMP CMD_PD
D10:  CJNE A, #C_SPD, D11
      LJMP CMD_SPD
D11:  CJNE A, #C_SPDZ, D12
      LJMP CMD_SPDZ
D12:  CJNE A, #C_PENN, D13
      LJMP CMD_PENN
D13:  CJNE A, #C_ZSET, D14
      LJMP CMD_ZSET
D14:  CJNE A, #C_ZOFF, D15
      LJMP CMD_ZOFF
D15:  CJNE A, #C_OFF, D16
      LJMP CMD_OFF
D16:  CJNE A, #C_STAT, D17
      LJMP CMD_STAT
D17:  CJNE A, #C_PNG, D18
      LJMP CMD_PNG
D18:  CJNE A, #C_ZDIR, D_UK
      LJMP CMD_ZDIR
D_UK:
      LJMP SEND_NACK          ; si el comando nose entiende

; trama extendida
RECV_EXT:
      LCALL UART_RECV_TO
      JNC RX_E1
      LJMP MAIN
RX_E1:
      MOV RX_PAY, A            ; DX

      LCALL UART_RECV_TO
      JNC RX_E2
      LJMP MAIN
RX_E2:
      MOV RX_PAY2, A           ; DY

      LCALL UART_RECV_TO
      JNC RX_E3
      LJMP MAIN
RX_E3:
      MOV RX_PAY3, A           ; flags de signo

      LCALL UART_RECV_TO
      JNC RX_E4
      LJMP MAIN
RX_E4:
      MOV RX_CHK, A            ; CHK

      MOV A, RX_HDR
      XRL A, RX_CMD
      XRL A, RX_PAY
      XRL A, RX_PAY2
      XRL A, RX_PAY3
      XRL A, RX_CHK
      JZ EXT_OK
      LJMP SEND_NACK
EXT_OK:
      CPL LED_PIN
      LJMP CMD_LINE

CMD_XP:
      MOV A, RX_PAY
      JNZ XP_GO
      LJMP SEND_ACK
XP_GO:
      MOV R4, A
XP_L: LCALL STEP_X_CW
      LCALL DELAY_STEP
      DJNZ R4, XP_L
      LJMP SEND_ACK
CMD_XN:
      MOV A, RX_PAY
      JNZ XN_GO
      LJMP SEND_ACK
XN_GO:
      MOV R4, A
XN_L: LCALL STEP_X_CCW
      LCALL DELAY_STEP
      DJNZ R4, XN_L
      LJMP SEND_ACK
CMD_YP:
      MOV A, RX_PAY
      JNZ YP_GO
      LJMP SEND_ACK
YP_GO:
      MOV R4, A
YP_L: LCALL STEP_Y_CW
      LCALL DELAY_STEP
      DJNZ R4, YP_L
      LJMP SEND_ACK
CMD_YN:
      MOV A, RX_PAY
      JNZ YN_GO
      LJMP SEND_ACK
YN_GO:
      MOV R4, A
YN_L: LCALL STEP_Y_CCW
      LCALL DELAY_STEP
      DJNZ R4, YN_L
      LJMP SEND_ACK


CMD_ZP:
      MOV A, RX_PAY
      JNZ ZP_GO
      LJMP SEND_ACK
ZP_GO:
      MOV R4, A
ZP_L: LCALL STEP_Z_UP
      LCALL DELAY_Z
      MOV A, Z_POS
      JZ ZP_SAT               ; ya esta en 0, no bajar mas el contador
      DEC Z_POS
ZP_SAT:
      DJNZ R4, ZP_L
      LJMP SEND_ACK
CMD_ZN:
      MOV A, RX_PAY
      JNZ ZN_GO
      LJMP SEND_ACK
ZN_GO:
      MOV R4, A
ZN_L: LCALL STEP_Z_DN
      LCALL DELAY_Z
      MOV A, Z_POS
      CJNE A, #0FFh, ZN_INC
      SJMP ZN_SAT             
ZN_INC:
      INC Z_POS
ZN_SAT:
      DJNZ R4, ZN_L
      LJMP SEND_ACK


CMD_PU:
      MOV A, Z_POS
      JNZ PU_GO
      LJMP SEND_ACK         
PU_GO:
      MOV R4, A           
PU_L: LCALL STEP_Z_UP
      LCALL DELAY_Z
      DJNZ R4, PU_L
      MOV Z_POS, #00h
      LJMP SEND_ACK
CMD_PD:
      MOV A, PEN_N
      CLR C
      SUBB A, Z_POS          
      JZ PD_OK                
      JC PD_UP                
PD_L: LCALL STEP_Z_DN
      LCALL DELAY_Z
      DJNZ R4, PD_L
      SJMP PD_OK
PD_UP:
      MOV A, Z_POS
      CLR C
      SUBB A, PEN_N         
      MOV R4, A
PD_UL:
      LCALL STEP_Z_UP
      LCALL DELAY_Z
      DJNZ R4, PD_UL
PD_OK:
      MOV Z_POS, PEN_N
      LJMP SEND_ACK


CMD_SXY:
      MOV A, RX_PAY
      JNB ACC.1, SXY_NX
      JB  ACC.0, SXY_XN
      LCALL STEP_X_CW
      SJMP SXY_NX
SXY_XN:
      LCALL STEP_X_CCW
SXY_NX:
      MOV A, RX_PAY
      JNB ACC.3, SXY_NY
      JB  ACC.2, SXY_YN
      LCALL STEP_Y_CW
      SJMP SXY_NY
SXY_YN:
      LCALL STEP_Y_CCW
SXY_NY:
      LCALL DELAY_STEP
      LJMP SEND_ACK


CMD_LINE:
      MOV A, RX_PAY3
      MOV C, ACC.0
      MOV X_NEG, C
      MOV C, ACC.1
      MOV Y_NEG, C

      MOV A, RX_PAY
      ORL A, RX_PAY2
      JNZ LINE_NZ
      LJMP SEND_ACK
LINE_NZ:
      MOV A, RX_PAY
      CLR C
      SUBB A, RX_PAY2
      JNC LN_X_MAJ

      CLR X_IS_MAJ            
      MOV R4, RX_PAY2
      MOV R5, RX_PAY
      MOV R3, RX_PAY2
      SJMP LN_SETUP
LN_X_MAJ:
      SETB X_IS_MAJ           
      MOV R4, RX_PAY
      MOV R5, RX_PAY2
      MOV R3, RX_PAY
LN_SETUP:
      MOV A, R4
      CLR C
      RRC A                  
      MOV R2, A
      MOV A, R5
      JZ LN_PURE              

LN_LOOP:
      MOV A, R2
      ADD A, R5               ;
      JC LN_CARRY

      MOV R2, A
      CLR C
      SUBB A, R4
      JC LN_NO_MN             
      MOV R2, A
      SJMP LN_DO_MN
LN_CARRY:
      CLR C
      SUBB A, R4              
      MOV R2, A
LN_DO_MN:
      JB X_IS_MAJ, LN_MN_Y
      JB X_NEG, LN_MN_XN
      LCALL STEP_X_CW
      SJMP LN_NO_MN
LN_MN_XN:
      LCALL STEP_X_CCW
      SJMP LN_NO_MN
LN_MN_Y:
      JB Y_NEG, LN_MN_YN
      LCALL STEP_Y_CW
      SJMP LN_NO_MN
LN_MN_YN:
      LCALL STEP_Y_CCW
LN_NO_MN:
      JB X_IS_MAJ, LN_MJ_X
      JB Y_NEG, LN_MJ_YN
      LCALL STEP_Y_CW
      SJMP LN_DLY
LN_MJ_YN:
      LCALL STEP_Y_CCW
      SJMP LN_DLY
LN_MJ_X:
      JB X_NEG, LN_MJ_XN
      LCALL STEP_X_CW
      SJMP LN_DLY
LN_MJ_XN:
      LCALL STEP_X_CCW
LN_DLY:
      LCALL DELAY_STEP
      DJNZ R3, LN_LOOP
      LJMP SEND_ACK
LN_PURE:
      JB X_IS_MAJ, LN_PU_X
      JB Y_NEG, LN_PU_YN
LN_PU_YP:
      LCALL STEP_Y_CW
      LCALL DELAY_STEP
      DJNZ R3, LN_PU_YP
      LJMP SEND_ACK
LN_PU_YN:
      LCALL STEP_Y_CCW
      LCALL DELAY_STEP
      DJNZ R3, LN_PU_YN
      LJMP SEND_ACK
LN_PU_X:
      JB X_NEG, LN_PU_XN
LN_PU_XP:
      LCALL STEP_X_CW
      LCALL DELAY_STEP
      DJNZ R3, LN_PU_XP
      LJMP SEND_ACK
LN_PU_XN:
      LCALL STEP_X_CCW
      LCALL DELAY_STEP
      DJNZ R3, LN_PU_XN
      LJMP SEND_ACK

CMD_SPD:                      ; velocidad XY
      MOV A, RX_PAY
      CJNE A, #02h, SPD_C
SPD_C:
      JNC SPD_OK
      MOV A, #02h
SPD_OK:
      MOV VEL, A
      LJMP SEND_ACK
CMD_SPDZ:                     ; velocidad Z,
      MOV A, RX_PAY
      CJNE A, #04h, SPZ_C
SPZ_C:
      JNC SPZ_OK
      MOV A, #04h
SPZ_OK:
      MOV VEL_Z, A
      LJMP SEND_ACK
CMD_PENN:
      MOV A, RX_PAY
      JNZ PN_OK
      LJMP SEND_ACK           
PN_OK:
      MOV PEN_N, A
      LJMP SEND_ACK
CMD_ZSET:                     ;
      MOV Z_POS, #00h
      LJMP SEND_ACK
CMD_ZDIR:                     ;
      MOV A, RX_PAY
      JZ ZDR_NORM
      MOV Z_DIR, #01h
      LJMP SEND_ACK
ZDR_NORM:
      MOV Z_DIR, #00h
      LJMP SEND_ACK
CMD_OFF:                      
      ANL P1, #0F0h          
      ANL P2, #0F0h           
      LJMP SEND_ACK
CMD_ZOFF:                     ; apaga bobinas de Zr
      ANL P2, #0Fh            
      LJMP SEND_ACK
CMD_PNG:
      LJMP SEND_ACK
CMD_STAT:                     ;
      MOV A, #ACK_B
      LCALL UART_SEND
      MOV A, Z_POS
      LCALL UART_SEND
      MOV A, PEN_N
      LCALL UART_SEND
      MOV A, VEL
      LCALL UART_SEND
      MOV A, VEL_Z
      LCALL UART_SEND
      MOV A, Z_DIR
      LCALL UART_SEND
      LJMP MAIN

SEND_ACK:
      MOV A, #ACK_B
      LCALL UART_SEND
      LJMP MAIN

SEND_NACK:
      MOV A, #NACK_B
      LCALL UART_SEND
      LJMP MAIN

STEP_X_CW:
      INC FASE_X
      MOV A, FASE_X
      CJNE A, #08h, WXC
      MOV FASE_X, #00h
WXC:  LCALL WRITE_X
      RET
STEP_X_CCW:
      DEC FASE_X
      MOV A, FASE_X
      CJNE A, #0FFh, WXCC
      MOV FASE_X, #07h
WXCC: LCALL WRITE_X
      RET
STEP_Y_CW:
      INC FASE_Y
      MOV A, FASE_Y
      CJNE A, #08h, WYC
      MOV FASE_Y, #00h
WYC:  LCALL WRITE_Y
      RET
STEP_Y_CCW:
      DEC FASE_Y
      MOV A, FASE_Y
      CJNE A, #0FFh, WYCC
      MOV FASE_Y, #07h
WYCC: LCALL WRITE_Y
      RET
STEP_Z_CW:
      INC FASE_Z
      MOV A, FASE_Z
      CJNE A, #08h, WZC
      MOV FASE_Z, #00h
WZC:  LCALL WRITE_Z
      RET
STEP_Z_CCW:
      DEC FASE_Z
      MOV A, FASE_Z
      CJNE A, #0FFh, WZCC
      MOV FASE_Z, #07h
WZCC: LCALL WRITE_Z
      RET


STEP_Z_UP:                    
      MOV A, Z_DIR
      JNZ SZU_INV
      LJMP STEP_Z_CW
SZU_INV:
      LJMP STEP_Z_CCW
STEP_Z_DN:                   
      MOV A, Z_DIR
      JNZ SZD_INV
      LJMP STEP_Z_CCW
SZD_INV:
      LJMP STEP_Z_CW

WRITE_X:
      MOV A, FASE_X
      MOV DPTR, #HALF_STEP
      MOVC A, @A+DPTR
      ANL P1, #0F0h
      ORL P1, A
      RET
WRITE_Y:
      MOV A, FASE_Y
      MOV DPTR, #HALF_STEP
      MOVC A, @A+DPTR
      ANL P2, #0F0h
      ORL P2, A
      RET
WRITE_Z:
      MOV A, FASE_Z
      MOV DPTR, #HALF_STEP
      MOVC A, @A+DPTR
      SWAP A
      ANL P2, #0Fh
      ORL P2, A
      RET

; secuencia de medio paso half table
HALF_STEP:
      DB 01h    ; A
      DB 03h    ; A+B
      DB 02h    ; B
      DB 06h    ; B+C
      DB 04h    ; C
      DB 0Ch    ; C+D
      DB 08h    ; D
      DB 09h    ; D+A

UART_SEND:
      CLR TI
      MOV SBUF, A
WT_TX:
      JNB TI, WT_TX
      CLR TI
      RET
UART_RECV:                    ; bloqueante, solo para esperar la cabecera
      JNB RI, UART_RECV
      CLR RI
      MOV A, SBUF
      RET

UART_RECV_TO:
      PUSH 06
      PUSH 07
      MOV R7, #200
URT_O:
      MOV R6, #230            
URT_I:
      JB RI, URT_GOT
      DJNZ R6, URT_I
      DJNZ R7, URT_O
      POP 07
      POP 06
      SETB C                  
      RET
URT_GOT:
      CLR RI
      MOV A, SBUF
      POP 07
      POP 06
      CLR C
      RET

; viva el polling siuuu
DELAY_STEP:                
      PUSH 05
      MOV R5, VEL
DS_L: MOV TH0, #0FCh
      MOV TL0, #66h
      SETB TR0
DS_W: JNB TF0, DS_W
      CLR TF0
      CLR TR0
      DJNZ R5, DS_L
      POP 05
      RET
DELAY_Z:                     
      PUSH 05
      MOV R5, VEL_Z
DZ_L: MOV TH0, #0FCh
      MOV TL0, #66h
      SETB TR0
DZ_W: JNB TF0, DZ_W
      CLR TF0
      CLR TR0
      DJNZ R5, DZ_L
      POP 05
      RET

LED_BLINK_3X:
      MOV R7, #06h
BLK:  CPL LED_PIN
      LCALL DELAY_100MS
      DJNZ R7, BLK
      CLR LED_PIN
      RET
DELAY_100MS:
      PUSH 06
      PUSH 05
      MOV R6, #250
M1:   MOV R5, #200
M2:   DJNZ R5, M2
      DJNZ R6, M1
      POP 05
      POP 06
      RET

      END
