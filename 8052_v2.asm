/;=======================================================================
; CNC PLOTTER FIRMWARE — AT89S52 @ 11.0592 MHz — v2 (CORREGIDO)
;
; CAMBIOS RESPECTO A LA v1 (cada uno arregla un bug documentado):
;
;  [SW-1] La pluma ya NO usa un flag booleano PEN_ST como guarda.
;         Ahora hay Z_POS = posicion absoluta del eje Z en pasos desde
;         el cero de pluma. PEN_UP va a Z_POS=0, PEN_DOWN va a
;         Z_POS=PEN_N. Son IDEMPOTENTES y AUTOCORRECTIVOS: repetirlos
;         es inofensivo y siempre acaban en la posicion correcta.
;         Esto elimina el "responde ACK pero no mueve nada".
;
;  [SW-2] VEL_Z separada de VEL. El eje Z ya NO depende de la velocidad
;         que dejo puesta el ultimo movimiento XY. El PC ya no necesita
;         mandar SET_SPEED antes de cada comando Z.
;
;  [SW-7] UART_RECV_TO: timeout de ~200 ms entre bytes de una trama.
;         Si se pierde un byte, la trama se descarta y el micro
;         resincroniza buscando 0xAA. Antes se quedaba colgado para
;         siempre y todo lo que venia detras se interpretaba desalineado.
;
;  [SW-8] C_ZP y C_ZN movidos a 0x0A / 0x0B. Antes C_ZN valia 0x06,
;         el mismo valor que ACK_B.
;
;  [SW-5] C_PENN: el PC ya puede fijar la profundidad de pluma.
;         Antes PEN_N estaba hardcodeado a 100 y el ajuste de la UI
;         no llegaba nunca al micro.
;
;  [SW-9] CMD_OFF ya NO apaga las bobinas del eje Z (antes hacia
;         MOV P2,#00h y la pluma se caia por gravedad). Para apagar Z
;         hay un comando explicito C_ZOFF.
;
;  NUEVO   C_STAT: el PC puede LEER el estado real del micro y
;          resincronizarse sin reiniciar nada.
;  NUEVO   C_ZSET: define la posicion actual de Z como cero de pluma.
;
;  [SW-30] C_ZDIR: sentido fisico del eje Z configurable. Segun como
;          quede montado el porta-pluma, el mismo sentido de giro puede
;          SUBIR o BAJAR la pluma. Z_DIR invierte el giro SIN tocar la
;          semantica de Z_POS (0 = arriba, PEN_N = abajo, siempre), asi
;          que C_PU/C_PD siguen siendo absolutos e idempotentes y el
;          flujo de calibracion es identico en los dos montajes.
;

; MAPA DE PINES (sin cambios)
;   Motor X : P1.0-P1.3
;   Motor Y : P2.0-P2.3
;   Motor Z : P2.4-P2.7
;   LED     : P3.5   (se invierte con cada trama valida — util para depurar)
;   UART    : P3.0 RXD / P3.1 TXD
;=======================================================================

BAUD_TIMER EQU 0FDh          ; 9600 baud @ 11.0592 MHz (SMOD=0)

; --- protocolo ---
HEADER_B  EQU 0AAh
ACK_B     EQU 06h
NACK_B    EQU 15h

; --- comandos (ninguno colisiona con HEADER_B / ACK_B / NACK_B) ---
C_XP      EQU 01h
C_XN      EQU 02h
C_YP      EQU 03h
C_YN      EQU 04h
C_XY      EQU 07h
C_LINE    EQU 08h
C_ZP      EQU 0Ah             ; << CAMBIADO (era 05h)
C_ZN      EQU 0Bh             ; << CAMBIADO (era 06h = ACK_B)
C_PU      EQU 10h
C_PD      EQU 11h
C_SPD     EQU 12h
C_OFF     EQU 13h
C_PNG     EQU 20h
C_STAT    EQU 21h             ; << NUEVO: leer estado
C_PENN    EQU 22h             ; << NUEVO: fijar profundidad de pluma
C_SPDZ    EQU 23h             ; << NUEVO: fijar velocidad de Z
C_ZOFF    EQU 24h             ; << NUEVO: apagar solo bobinas Z
C_ZSET    EQU 25h             ; << NUEVO: definir cero de pluma aqui
C_ZDIR    EQU 26h             ; << NUEVO: sentido fisico del eje Z

; --- variables RAM ---
FASE_X    EQU 30h
FASE_Y    EQU 31h
FASE_Z    EQU 32h
VEL       EQU 33h             ; ms entre pasos, ejes X e Y
                              ; 34h libre (era PEN_ST en la v1)
PEN_N     EQU 35h             ; profundidad de pluma en pasos
Z_POS     EQU 36h             ; << NUEVO: posicion Z absoluta (0 = pluma arriba)
VEL_Z     EQU 37h             ; << NUEVO: ms entre pasos, eje Z
Z_DIR     EQU 38h             ; << NUEVO: 0 = normal, 1 = porta-pluma invertido

; --- buffer de trama ---
RX_HDR    EQU 40h
RX_CMD    EQU 41h
RX_PAY    EQU 42h
RX_CHK    EQU 43h
RX_PAY2   EQU 44h             ; DY  (solo trama extendida)
RX_PAY3   EQU 45h             ; FLAGS (solo trama extendida)

; --- bits para Bresenham (byte 20h, area bit-direccionable) ---
X_IS_MAJ  BIT 00h
X_NEG     BIT 01h
Y_NEG     BIT 02h

; --- pines ---
LED_PIN   BIT P3.5

;=======================================================================
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
;=======================================================================
INIT_UART:
      MOV SCON, #50h
      MOV TH1, #BAUD_TIMER
      MOV TL1, #BAUD_TIMER
      SETB TR1
      CLR TI
      CLR RI
      RET

;=======================================================================
INIT:
      MOV TMOD, #21h          ; T1 = modo 2 (baud), T0 = modo 1 (delay)
      MOV PCON, #00h          ; SMOD=0 explicito: el baudaje no depende de
                              ; como quedara PCON tras un arranque raro
      MOV SP,   #4Fh
      MOV FASE_X, #00h
      MOV FASE_Y, #00h
      MOV FASE_Z, #00h
      MOV VEL,    #05h        ; XY: 5 ms  (antes 3 — demasiado rapido)
      MOV VEL_Z,  #08h        ; Z : 8 ms  (el eje que pelea con la gravedad)
      MOV PEN_N,  #100        ; valor por defecto; el PC lo cambia con C_PENN
      MOV Z_POS,  #00h        ; al arrancar asumimos pluma arriba
      MOV Z_DIR,  #00h        ; montaje normal; el PC lo cambia con C_ZDIR
      MOV P1, #00h
      MOV P2, #00h

      ; --- enclavamiento inicial: fase 0 a los tres motores ---
      LCALL WRITE_X
      LCALL WRITE_Y
      LCALL WRITE_Z

      LCALL INIT_UART
      LCALL LED_BLINK_3X
      MOV A, #'O'
      LCALL UART_SEND
      MOV A, #'K'
      LCALL UART_SEND

;=======================================================================
; MAIN — recepcion de trama con resincronizacion
;
;   Trama estandar : [AA][CMD][PAY][CHK]            = 4 bytes
;   Trama extendida: [AA][08][DX][DY][FLAGS][CHK]   = 6 bytes
;
; La cabecera se espera indefinidamente. Los bytes siguientes tienen
; timeout: si expira, se descarta la trama y se vuelve a buscar 0xAA.
;=======================================================================
MAIN:
      LCALL UART_RECV         ; bloqueante: esperar cabecera
      CJNE A, #HEADER_B, MAIN ; no es AA → seguir buscando
      MOV RX_HDR, A

      LCALL UART_RECV_TO
      JNC MN_C1
      LJMP MAIN               ; timeout → resincronizar
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

      ; validar checksum: HDR xor CMD xor PAY xor CHK = 0
      MOV A, RX_HDR
      XRL A, RX_CMD
      XRL A, RX_PAY
      XRL A, RX_CHK
      JZ CHK_OK
      LJMP SEND_NACK
CHK_OK:
      CPL LED_PIN             ; señal visual: trama valida recibida

;=======================================================================
; DECODE
;=======================================================================
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
      LJMP SEND_NACK          ; comando desconocido

;=======================================================================
; RECV_EXT — trama extendida de CMD_LINE
;=======================================================================
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
      MOV RX_PAY3, A           ; FLAGS

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

;=======================================================================
; MOVIMIENTO X / Y — N pasos con delay VEL
;=======================================================================
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
;-----------------------------------------------------------------------
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
;-----------------------------------------------------------------------
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
;-----------------------------------------------------------------------
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

;=======================================================================
; MOVIMIENTO Z RELATIVO — usa VEL_Z y actualiza Z_POS con saturacion
;
;   C_ZP (Z+) = SUBIR pluma  → Z_POS disminuye, satura en 0
;   C_ZN (Z-) = BAJAR pluma  → Z_POS aumenta,   satura en 255
;
; La saturacion evita que Z_POS se envuelva y pierda el sentido. Si
; llegas al tope, usa C_ZSET para redefinir el cero de pluma.
;=======================================================================
CMD_ZP:
      MOV A, RX_PAY
      JNZ ZP_GO
      LJMP SEND_ACK
ZP_GO:
      MOV R4, A
ZP_L: LCALL STEP_Z_UP
      LCALL DELAY_Z
      MOV A, Z_POS
      JZ ZP_SAT               ; ya en 0 → no decrementar mas
      DEC Z_POS
ZP_SAT:
      DJNZ R4, ZP_L
      LJMP SEND_ACK
;-----------------------------------------------------------------------
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
      SJMP ZN_SAT             ; ya en 255 → saturar
ZN_INC:
      INC Z_POS
ZN_SAT:
      DJNZ R4, ZN_L
      LJMP SEND_ACK

;=======================================================================
; PLUMA — ABSOLUTA E IDEMPOTENTE
;
; CMD_PU : llevar Z a la posicion 0        (pluma arriba)
; CMD_PD : llevar Z a la posicion PEN_N    (pluma abajo)
;
; No hay flag "ya esta arriba/abajo". Se calcula el delta real desde
; Z_POS, asi que:
;   - repetir el comando no hace nada malo (delta = 0)
;   - si el estado se habia desviado, el comando lo CORRIGE
;   - si el PC reintenta por un ACK perdido, no hay doble movimiento
;
; [SW-30] El sentido fisico lo resuelven STEP_Z_UP / STEP_Z_DN segun
; Z_DIR, asi que esta logica es la misma con el porta-pluma montado
; en un sentido o en el otro.
;=======================================================================
CMD_PU:
      MOV A, Z_POS
      JNZ PU_GO
      LJMP SEND_ACK           ; ya esta en el cero
PU_GO:
      MOV R4, A               ; subir exactamente Z_POS pasos
PU_L: LCALL STEP_Z_UP
      LCALL DELAY_Z
      DJNZ R4, PU_L
      MOV Z_POS, #00h
      LJMP SEND_ACK
;-----------------------------------------------------------------------
CMD_PD:
      MOV A, PEN_N
      CLR C
      SUBB A, Z_POS           ; A = PEN_N - Z_POS
      JZ PD_OK                ; ya esta a la profundidad correcta
      JC PD_UP                ; borrow → Z_POS > PEN_N → hay que SUBIR
      MOV R4, A               ; bajar el delta
PD_L: LCALL STEP_Z_DN
      LCALL DELAY_Z
      DJNZ R4, PD_L
      SJMP PD_OK
PD_UP:
      MOV A, Z_POS
      CLR C
      SUBB A, PEN_N           ; A = Z_POS - PEN_N
      MOV R4, A
PD_UL:
      LCALL STEP_Z_UP
      LCALL DELAY_Z
      DJNZ R4, PD_UL
PD_OK:
      MOV Z_POS, PEN_N
      LJMP SEND_ACK

;=======================================================================
; STEP_XY: paso simultaneo X+Y (fallback para modo interactivo)
; bits del payload: [0]=XD [1]=XE [2]=YD [3]=YE
;=======================================================================
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

;=======================================================================
; CMD_LINE — Bresenham interno de 8 bits (sin cambios respecto a v1;
; verificado correcto, incluido el camino LN_CARRY)
;
;   R2 = ERR, R3 = contador, R4 = MAJOR, R5 = MINOR
;=======================================================================
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

      CLR X_IS_MAJ            ; Y es el eje mayor
      MOV R4, RX_PAY2
      MOV R5, RX_PAY
      MOV R3, RX_PAY2
      SJMP LN_SETUP
LN_X_MAJ:
      SETB X_IS_MAJ           ; X es el eje mayor
      MOV R4, RX_PAY
      MOV R5, RX_PAY2
      MOV R3, RX_PAY
LN_SETUP:
      MOV A, R4
      CLR C
      RRC A                   ; ERR = MAJOR / 2
      MOV R2, A
      MOV A, R5
      JZ LN_PURE              ; MINOR = 0 → linea pura

LN_LOOP:
      MOV A, R2
      ADD A, R5               ; ERR += MINOR
      JC LN_CARRY

      MOV R2, A
      CLR C
      SUBB A, R4
      JC LN_NO_MN             ; ERR < MAJOR → sin paso menor
      MOV R2, A
      SJMP LN_DO_MN
LN_CARRY:
      CLR C
      SUBB A, R4              ; correcto pese al wrap de 8 bits
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
;-----------------------------------------------------------------------
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

;=======================================================================
; CONTROL
;=======================================================================
CMD_SPD:                      ; velocidad XY, minimo 2 ms
      MOV A, RX_PAY
      CJNE A, #02h, SPD_C
SPD_C:
      JNC SPD_OK
      MOV A, #02h
SPD_OK:
      MOV VEL, A
      LJMP SEND_ACK
;-----------------------------------------------------------------------
CMD_SPDZ:                     ; velocidad Z, minimo 4 ms (proteccion de par)
      MOV A, RX_PAY
      CJNE A, #04h, SPZ_C
SPZ_C:
      JNC SPZ_OK
      MOV A, #04h
SPZ_OK:
      MOV VEL_Z, A
      LJMP SEND_ACK
;-----------------------------------------------------------------------
CMD_PENN:                     ; profundidad de pluma en pasos
      MOV A, RX_PAY
      JNZ PN_OK
      LJMP SEND_ACK           ; ignorar 0
PN_OK:
      MOV PEN_N, A
      LJMP SEND_ACK
;-----------------------------------------------------------------------
CMD_ZSET:                     ; "la pluma esta arriba, aqui es el cero"
      MOV Z_POS, #00h
      LJMP SEND_ACK
;-----------------------------------------------------------------------
CMD_ZDIR:                     ; [SW-30] sentido fisico del eje Z
      ; payload 00h = montaje normal, cualquier otro = invertido.
      ;
      ; NO se toca Z_POS: el PC sube la pluma ANTES de cambiar el
      ; sentido, asi que al llegar aqui Z_POS ya vale 0 y el estado
      ; sigue siendo coherente con el nuevo montaje.
      MOV A, RX_PAY
      JZ ZDR_NORM
      MOV Z_DIR, #01h
      LJMP SEND_ACK
ZDR_NORM:
      MOV Z_DIR, #00h
      LJMP SEND_ACK
;-----------------------------------------------------------------------
CMD_OFF:                      ; apaga SOLO X e Y — Z sigue sujeta
      ANL P1, #0F0h           ; X off, preserva P1.4-P1.7
      ANL P2, #0F0h           ; Y off, PRESERVA el nibble alto (Z)
      LJMP SEND_ACK
;-----------------------------------------------------------------------
CMD_ZOFF:                     ; apaga las bobinas de Z (¡la pluma puede caer!)
      ANL P2, #0Fh            ; Z off, preserva Y
      LJMP SEND_ACK
;-----------------------------------------------------------------------
CMD_PNG:
      LJMP SEND_ACK
;-----------------------------------------------------------------------
CMD_STAT:                     ; ACK + Z_POS + PEN_N + VEL + VEL_Z + Z_DIR
      ; 6 bytes. El PC lee los 5 primeros como obligatorios y el 6º de
      ; forma opcional, para poder detectar firmware viejo sin C_ZDIR.
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

;=======================================================================
; RESPUESTAS
;=======================================================================
SEND_ACK:
      MOV A, #ACK_B
      LCALL UART_SEND
      LJMP MAIN

SEND_NACK:
      MOV A, #NACK_B
      LCALL UART_SEND
      LJMP MAIN

;=======================================================================
; FUNCIONES DE PASO
;=======================================================================
STEP_X_CW:
      INC FASE_X
      MOV A, FASE_X
      CJNE A, #08h, WXC
      MOV FASE_X, #00h
WXC:  LCALL WRITE_X
      RET
;-----------------------------------------------------------------------
STEP_X_CCW:
      DEC FASE_X
      MOV A, FASE_X
      CJNE A, #0FFh, WXCC
      MOV FASE_X, #07h
WXCC: LCALL WRITE_X
      RET
;-----------------------------------------------------------------------
STEP_Y_CW:
      INC FASE_Y
      MOV A, FASE_Y
      CJNE A, #08h, WYC
      MOV FASE_Y, #00h
WYC:  LCALL WRITE_Y
      RET
;-----------------------------------------------------------------------
STEP_Y_CCW:
      DEC FASE_Y
      MOV A, FASE_Y
      CJNE A, #0FFh, WYCC
      MOV FASE_Y, #07h
WYCC: LCALL WRITE_Y
      RET
;-----------------------------------------------------------------------
STEP_Z_CW:
      INC FASE_Z
      MOV A, FASE_Z
      CJNE A, #08h, WZC
      MOV FASE_Z, #00h
WZC:  LCALL WRITE_Z
      RET
;-----------------------------------------------------------------------
STEP_Z_CCW:
      DEC FASE_Z
      MOV A, FASE_Z
      CJNE A, #0FFh, WZCC
      MOV FASE_Z, #07h
WZCC: LCALL WRITE_Z
      RET

;=======================================================================
; SENTIDO FISICO DEL EJE Z — [SW-30]
;
; Segun como quede montado el porta-pluma, el mismo sentido de giro
; puede SUBIR o BAJAR la pluma. Toda la logica de arriba habla en
; terminos de SUBIR/BAJAR y son estas dos rutinas — el UNICO sitio —
; las que traducen eso a CW/CCW mirando Z_DIR.
;
; La semantica de Z_POS NO cambia con el montaje:
;   Z_POS = 0      -> pluma ARRIBA
;   Z_POS = PEN_N  -> pluma ABAJO
; por eso C_PU/C_PD siguen siendo absolutos e idempotentes y el flujo
; de calibracion con C_ZSET es identico en los dos montajes.
;
;   Z_DIR = 0 : subir = CW   (montaje normal, por defecto)
;   Z_DIR = 1 : subir = CCW  (porta-pluma invertido)
;
; Se salta con LJMP, no con LCALL: el RET de STEP_Z_xx vuelve directo
; al llamador, asi que no se gasta un nivel extra de pila por paso.
; A queda machacada, pero ningun llamador la necesita viva.
;=======================================================================
STEP_Z_UP:                    ; un medio paso SUBIENDO la pluma
      MOV A, Z_DIR
      JNZ SZU_INV
      LJMP STEP_Z_CW
SZU_INV:
      LJMP STEP_Z_CCW
;-----------------------------------------------------------------------
STEP_Z_DN:                    ; un medio paso BAJANDO la pluma
      MOV A, Z_DIR
      JNZ SZD_INV
      LJMP STEP_Z_CCW
SZD_INV:
      LJMP STEP_Z_CW

;=======================================================================
; ESCRITURA AL PUERTO
; ANL/ORL sobre puerto son read-modify-write y leen el LATCH,
; por eso los nibbles de Y y Z no se pisan entre si.
;=======================================================================
WRITE_X:
      MOV A, FASE_X
      MOV DPTR, #HALF_STEP
      MOVC A, @A+DPTR
      ANL P1, #0F0h
      ORL P1, A
      RET
;-----------------------------------------------------------------------
WRITE_Y:
      MOV A, FASE_Y
      MOV DPTR, #HALF_STEP
      MOVC A, @A+DPTR
      ANL P2, #0F0h
      ORL P2, A
      RET
;-----------------------------------------------------------------------
WRITE_Z:
      MOV A, FASE_Z
      MOV DPTR, #HALF_STEP
      MOVC A, @A+DPTR
      SWAP A
      ANL P2, #0Fh
      ORL P2, A
      RET

;=======================================================================
; Secuencia de medio paso del 28BYJ-48 (verificada correcta)
;=======================================================================
HALF_STEP:
      DB 01h    ; A
      DB 03h    ; A+B
      DB 02h    ; B
      DB 06h    ; B+C
      DB 04h    ; C
      DB 0Ch    ; C+D
      DB 08h    ; D
      DB 09h    ; D+A

;=======================================================================
; UART
;=======================================================================
UART_SEND:
      CLR TI
      MOV SBUF, A
WT_TX:
      JNB TI, WT_TX
      CLR TI
      RET
;-----------------------------------------------------------------------
UART_RECV:                    ; bloqueante (solo para esperar cabecera)
      JNB RI, UART_RECV
      CLR RI
      MOV A, SBUF
      RET
;-----------------------------------------------------------------------
; UART_RECV_TO — recibe un byte con timeout de ~200 ms
;   Salida:  C=0 → byte valido en A
;            C=1 → timeout (trama incompleta, hay que resincronizar)
;
; A 9600 baud un byte tarda ~1,04 ms, asi que sobra margen para el
; siguiente byte de una trama que el PC envia de golpe.
;
; Cuentas: JB(2 ciclos) + DJNZ(2) = 4 ciclos = 4,34 us a 11,0592 MHz.
;   bucle interno 230 vueltas  -> ~1 ms
;   bucle externo 200 vueltas  -> ~200 ms
; Debe quedar POR DEBAJO del timeout de lectura del PC (>= 2 s) para
; que el micro resincronice antes de que el PC se rinda.
;-----------------------------------------------------------------------
UART_RECV_TO:
      PUSH 06
      PUSH 07
      MOV R7, #200
URT_O:
      MOV R6, #230            ; ~1 ms por vuelta
URT_I:
      JB RI, URT_GOT
      DJNZ R6, URT_I
      DJNZ R7, URT_O
      POP 07
      POP 06
      SETB C                  ; timeout
      RET
URT_GOT:
      CLR RI
      MOV A, SBUF
      POP 07
      POP 06
      CLR C
      RET

;=======================================================================
; DELAYS — 1 ms con 11.0592 MHz: 922 ciclos → 65536-922 = FC66h
; R5 se salva porque el bucle de Bresenham tambien lo usa.
;=======================================================================
DELAY_STEP:                   ; VEL ms   (ejes X e Y)
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
;-----------------------------------------------------------------------
DELAY_Z:                      ; VEL_Z ms (eje Z)
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

;=======================================================================
LED_BLINK_3X:
      MOV R7, #06h
BLK:  CPL LED_PIN
      LCALL DELAY_100MS
      DJNZ R7, BLK
      CLR LED_PIN
      RET
;-----------------------------------------------------------------------
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
