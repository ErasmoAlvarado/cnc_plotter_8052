"""
cnc_protocol.py — Capa de comunicacion con el AT89S52  — v2 (CORREGIDA)
Protocolo binario: [AA][CMD][PAY][CHK] -> [ACK/NACK]
Cristal: 11.0592 MHz — Baud: 9600

CAMBIOS RESPECTO A LA v1 (ver DIAGNOSTICO.md):

 [SW-3] threading.RLock sobre TODO acceso al puerto serie. Antes, los
        hilos de job y los endpoints HTTP escribian a la vez sobre el
        mismo objeto Serial y las tramas se intercalaban byte a byte.

 [SW-1] Se elimina la doble maquina de estados de la pluma. El firmware
        lleva Z_POS absoluto; aqui solo se cachea y se RESINCRONIZA
        desde el micro con get_state(). pen_down se DERIVA de Z_POS.

 [SW-2] Ya no se manda SET_SPEED antes de cada movimiento Z. El firmware
        tiene VEL_Z propia. Se configura una vez en sync_firmware().

 [SW-5] set_pen_steps() envia de verdad la profundidad de pluma al micro.

 [SW-8] C_ZP / C_ZN movidos a 0x0A / 0x0B (antes 0x06 colisionaba con ACK).

 [SW-4] Los reintentos de comandos de movimiento se limitan, porque el
        firmware NO es idempotente en movimientos relativos. Los comandos
        de pluma si lo son (posicion absoluta), asi que ahi si se reintenta.

 [SW-10] step_z persiste posicion como step_x/step_y.
 [SW-13] connect() ya no bloquea 5 s esperando el "OK" de bienvenida.
 [SW-15] _auto_detect_port() no llama a input() si no hay TTY.

CAMBIOS DE ESTA REVISION:

 [SW-30] set_z_invert(): sentido fisico del eje Z configurable segun como
         quede montado el porta-pluma. La inversion vive EN EL FIRMWARE
         (C_ZDIR); aqui solo se envia y se cachea. Deliberadamente NO se
         emula en el PC: hacerlo obligaria a que Z_POS=0 significase
         "arriba" a veces y "abajo" otras, que es exactamente la doble
         maquina de estados que [SW-1] elimino.

 [SW-33] connect() captura los errores de serial.Serial (puerto ocupado,
         inexistente, sin permisos) y devuelve False en vez de propagar
         la excepcion hasta un 500 de FastAPI.

 [SW-34] get_state() lee 6 bytes (el 6º es Z_DIR) pero acepta 5 para
         detectar firmware antiguo sin C_ZDIR, en vez de dar timeout.

 [SW-35] step_x/step_y/step_z normalizan la direccion a ±1. Con
         direction=2 la posicion cacheada avanzaba el DOBLE que la real.

 [SW-36] step_*() con count<=0 ya no dispara la compensacion de backlash
         de un movimiento que no existe.

 [SW-37] _save_position() escribe de forma atomica (tmp + os.replace).
         Un corte a mitad dejaba un JSON truncado y se perdia la posicion.

 [SW-38] load_last_position() valida el contenido del fichero. Un
         .last_position manipulado provocaba KeyError/TypeError arriba.

 [SW-39] El cache de velocidad se invalida al perder la comunicacion:
         si el micro se reinicio, VEL vuelve a su default y el cache
         mentia hasta el siguiente sync.
"""

import os
import sys
import json
import time
import threading

import serial
import serial.tools.list_ports


# ─── CONSTANTES DEL PROTOCOLO ────────────────────────────────────────

HEADER = 0xAA
ACK    = 0x06
NACK   = 0x15

# Comandos de movimiento
CMD_X_POS   = 0x01
CMD_X_NEG   = 0x02
CMD_Y_POS   = 0x03
CMD_Y_NEG   = 0x04
CMD_STEP_XY = 0x07
CMD_LINE    = 0x08
CMD_Z_POS   = 0x0A          # CAMBIADO: era 0x05
CMD_Z_NEG   = 0x0B          # CAMBIADO: era 0x06 (colisionaba con ACK)

# Comandos de control
CMD_PEN_UP     = 0x10
CMD_PEN_DOWN   = 0x11
CMD_SET_SPEED  = 0x12       # velocidad de X e Y
CMD_MOTORS_OFF = 0x13       # apaga SOLO X e Y (Z sigue sujeta)
CMD_PING       = 0x20
CMD_GET_STATE  = 0x21       # NUEVO: leer Z_POS / PEN_N / VEL / VEL_Z
CMD_SET_PEN_N  = 0x22       # NUEVO: profundidad de pluma
CMD_SET_SPD_Z  = 0x23       # NUEVO: velocidad del eje Z
CMD_Z_OFF      = 0x24       # NUEVO: apagar bobinas de Z
CMD_Z_SET_ZERO = 0x25       # NUEVO: definir el cero de pluma aqui
CMD_Z_INVERT   = 0x26       # NUEVO: sentido fisico del eje Z [SW-30]

BAUD = 9600

# Velocidad por defecto del eje Z, en ms entre medios pasos.
# El 28BYJ-48 a 5 V (menos ~1 V de caida en la ULN2003) pierde par
# drasticamente por encima de ~250 medios pasos/s cuando carga peso.
# 8 ms = 125 pasos/s: lento, pero no falla. Bajalo solo si va sobrado.
Z_SPEED_DEFAULT = 8
XY_SPEED_DEFAULT = 5

POSITION_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '.last_position'))

# Edad maxima de .last_position para fiarse de el (2 h). Pasado ese
# tiempo lo mas probable es que alguien haya movido los ejes a mano.
POSITION_MAX_AGE_S = 7200


class CNCProtocol:

    def __init__(self, port=None, simulate=False):
        self.simulate = simulate
        self.ser = None
        self.port = port

        # [SW-3] Un solo lock reentrante protege el puerto. Todos los
        # metodos publicos lo toman, asi que la API web y los hilos de
        # job ya no pueden intercalar tramas.
        self._lock = threading.RLock()

        # posicion en pasos enteros
        self.pos_x = 0
        self.pos_y = 0
        self.pos_z = 0          # espejo de Z_POS del firmware

        # profundidad de pluma (pasos). Debe coincidir con PEN_N del micro.
        self.pen_steps = 100
        self.z_speed = Z_SPEED_DEFAULT
        self._last_speed_ok = None   # cache de VEL confirmada por ACK

        # [SW-30] Sentido fisico del eje Z (porta-pluma montado al reves).
        # Espejo de Z_DIR en el firmware; la inversion la hace EL MICRO.
        self.z_invert = False
        # None = todavia no lo sabemos. False = firmware antiguo sin C_ZDIR.
        self.z_invert_supported = None

        # backlash
        self.backlash_x = 0
        self.backlash_y = 0
        self._last_dir_x = 0
        self._last_dir_y = 0

        self.stats = {'sent': 0, 'ack': 0, 'nack': 0, 'timeout': 0, 'retries': 0}
        self._step_counter = 0
        self._consecutive_failures = 0
        self.comm_lost = False

    # ─── ESTADO DE LA PLUMA (derivado, no cacheado) ──────────────

    @property
    def pen_down_flag(self):
        """[SW-1] La pluma NO tiene flag propio. Se deriva de la posicion
        absoluta de Z, que es la unica fuente de verdad y se puede
        resincronizar desde el firmware con get_state()."""
        return self.pos_z >= max(1, self.pen_steps)

    # ─── CONEXION ────────────────────────────────────────────────

    def connect(self):
        if self.simulate:
            print("  [SIM] Modo simulacion activo")
            return True

        if self.port is None:
            self.port = self._auto_detect_port()
        if self.port is None:
            return False

        with self._lock:
            # [SW-33] puerto ocupado / inexistente / sin permisos son
            # situaciones NORMALES, no un crash: se informa y se sale.
            try:
                self.ser = serial.Serial(self.port, BAUD, timeout=0.5)
            except (serial.SerialException, OSError, ValueError) as e:
                print(f"  ERROR: no se pudo abrir {self.port}: {e}")
                self.ser = None
                return False

            try:
                time.sleep(0.3)
                self.ser.reset_input_buffer()

                # [SW-13] lectura NO bloqueante del "OK": si el micro ya
                # habia arrancado no lo enviara, y antes esperabamos 5 s.
                welcome = self.ser.read(10)
                if welcome:
                    txt = welcome.decode('ascii', errors='replace').strip()
                    print(f"  MCU: {txt}")
                self.ser.reset_input_buffer()
            except (serial.SerialException, OSError) as e:
                print(f"  ERROR: fallo leyendo de {self.port}: {e}")
                try:
                    self.ser.close()
                except Exception:
                    pass
                self.ser = None
                return False

            self.comm_lost = False
            self._consecutive_failures = 0

        # [SW-1] Resincronizar SIEMPRE al conectar. El AT89S52 no se
        # resetea al abrir el puerto, asi que conserva su estado entre
        # ejecuciones de la app: hay que leerlo, no asumirlo.
        self.sync_firmware()
        return True

    def disconnect(self):
        self._save_position()
        with self._lock:
            if self.ser and self.ser.is_open:
                try:
                    self.ser.close()
                except Exception:
                    pass
            self.ser = None
            self._last_speed_ok = None      # [SW-39] el cache muere aqui
            self.z_invert_supported = None

    def _auto_detect_port(self):
        puertos = serial.tools.list_ports.comports()
        if not puertos:
            print("  ERROR: No se encontraron puertos COM")
            return None
        if len(puertos) == 1:
            print(f"  Puerto auto-detectado: {puertos[0].device}")
            return puertos[0].device
        # [SW-15] no bloquear con input() si corremos como servidor
        if not sys.stdin or not sys.stdin.isatty():
            print(f"  Varios puertos; usando el primero: {puertos[0].device}")
            return puertos[0].device
        print("  Puertos disponibles:")
        for i, p in enumerate(puertos):
            print(f"    [{i}] {p.device} - {p.description}")
        try:
            idx = int(input("  Seleccionar: "))
            return puertos[idx].device
        except (ValueError, IndexError):
            return puertos[0].device

    # ─── SINCRONIZACION CON EL FIRMWARE ──────────────────────────

    def sync_firmware(self):
        """Alinea PC y micro. Llamar al conectar y tras cualquier
        sospecha de desincronizacion.

        El orden importa: primero se EMPUJA lo que el PC manda (VEL_Z,
        PEN_N, Z_DIR) y despues se LEE el estado resultante, de forma
        que los valores cacheados sean los que el micro confirmo, no
        los que creiamos tener."""
        if self.simulate:
            self.z_invert_supported = True
            return True

        self._last_speed_ok = None          # invalidar cache de velocidad
        self.set_speed_z(self.z_speed)
        self.set_pen_steps(self.pen_steps)
        self.set_z_invert(self.z_invert, move_pen=False)

        st = self.get_state()
        if st:
            self.pos_z = st['z_pos']
            self.pen_steps = st['pen_n']
            self.z_speed = st['vel_z']
            if st['z_invert'] is not None:
                self.z_invert = st['z_invert']
            return True
        return False

    def get_state(self):
        """Lee el estado real del micro.

        Respuesta: ACK + Z_POS + PEN_N + VEL + VEL_Z + Z_DIR (6 bytes).

        [SW-34] Los 5 primeros son obligatorios; el 6º (Z_DIR) es
        opcional para poder hablar con firmware anterior a [SW-30]. Si
        no llega, z_invert queda en None y z_invert_supported en False:
        asi la UI puede decir "reflashea el micro" en vez de fingir que
        el ajuste se aplico."""
        if self.simulate:
            self.z_invert_supported = True
            return {'z_pos': self.pos_z, 'pen_n': self.pen_steps,
                    'vel': XY_SPEED_DEFAULT, 'vel_z': self.z_speed,
                    'z_invert': self.z_invert}

        with self._lock:
            if not self.ser or not self.ser.is_open:
                self.comm_lost = True
                return None
            try:
                self.ser.reset_input_buffer()
                chk = HEADER ^ CMD_GET_STATE ^ 0x00
                self.ser.write(bytes([HEADER, CMD_GET_STATE, 0x00, chk]))
                self.stats['sent'] += 1
                self.ser.timeout = 2.0
                resp = self.ser.read(5)
                extra = b''
                if len(resp) == 5 and resp[0] == ACK:
                    # el 6º byte, si existe, ya viene detras: 1 ms a 9600
                    self.ser.timeout = 0.25
                    extra = self.ser.read(1)
            except Exception:
                self.comm_lost = True
                self._last_speed_ok = None          # [SW-39]
                return None

        if len(resp) != 5 or resp[0] != ACK:
            self.stats['timeout'] += 1
            return None

        self.stats['ack'] += 1
        self.comm_lost = False
        self._consecutive_failures = 0

        z_invert = bool(extra[0]) if extra else None
        self.z_invert_supported = extra != b''

        return {'z_pos': resp[1], 'pen_n': resp[2],
                'vel': resp[3], 'vel_z': resp[4], 'z_invert': z_invert}

    # ─── PROTOCOLO BASE ──────────────────────────────────────────

    def send_command(self, cmd, payload=0x00, retries=2, timeout=None):
        """Envia [AA][CMD][PAY][CHK] y espera ACK. Retorna True/False.

        [SW-4] OJO con `retries`: el firmware NO es idempotente en
        movimientos relativos (X/Y/Z). Si el ACK se pierde despues de
        ejecutar, un reintento MUEVE OTRA VEZ. Por eso los movimientos
        usan retries=1 y timeout generoso, mientras que los comandos
        de pluma (absolutos, idempotentes) si pueden reintentar.
        """
        if self.simulate:
            self.stats['sent'] += 1
            self.stats['ack'] += 1
            self._consecutive_failures = 0
            return True

        # timeouts dinamicos con margen amplio (evita falsos timeouts
        # que disparan reintentos y dobles movimientos)
        if timeout is None:
            if cmd in (CMD_X_POS, CMD_X_NEG, CMD_Y_POS, CMD_Y_NEG):
                timeout = max(4.0, payload * 0.030)
            elif cmd in (CMD_Z_POS, CMD_Z_NEG):
                timeout = max(4.0, payload * (self.z_speed + 3) / 1000.0)
            elif cmd in (CMD_PEN_UP, CMD_PEN_DOWN):
                timeout = max(6.0, 255 * (self.z_speed + 3) / 1000.0)
            else:
                timeout = 2.0

        chk = HEADER ^ cmd ^ payload
        frame = bytes([HEADER, cmd, payload, chk])

        with self._lock:                       # [SW-3] seccion critica
            if not self.ser or not self.ser.is_open:
                self.comm_lost = True
                return False

            for attempt in range(max(1, retries)):
                self.stats['sent'] += 1
                try:
                    self.ser.reset_input_buffer()
                    self.ser.write(frame)
                    self.ser.timeout = timeout
                    resp = self.ser.read(1)
                except Exception:
                    # el puerto se murio (cable fuera, driver caido).
                    # Contabilizarlo igual que cualquier otro fallo.
                    self._consecutive_failures += 1
                    self.comm_lost = True
                    self._last_speed_ok = None      # [SW-39]
                    return False

                if resp and resp[0] == ACK:
                    self.stats['ack'] += 1
                    self._consecutive_failures = 0
                    self.comm_lost = False
                    return True
                elif resp and resp[0] == NACK:
                    self.stats['nack'] += 1
                else:
                    self.stats['timeout'] += 1

                if attempt < retries - 1:
                    self.stats['retries'] += 1
                    time.sleep(0.05)

        self._consecutive_failures += 1
        if self._consecutive_failures >= 5:
            self.comm_lost = True
            self._last_speed_ok = None              # [SW-39]
        return False

    def send_line_segment(self, abs_dx, abs_dy, dir_x, dir_y):
        """Trama extendida [AA][08][DX][DY][FLAGS][CHK] — Bresenham en firmware."""
        if self.simulate:
            self.stats['sent'] += 1
            self.stats['ack'] += 1
            self._consecutive_failures = 0
            return True

        abs_dx = max(0, min(255, int(abs_dx)))
        abs_dy = max(0, min(255, int(abs_dy)))

        flags = 0x00
        if dir_x < 0:
            flags |= 0x01
        if dir_y < 0:
            flags |= 0x02

        chk = HEADER ^ CMD_LINE ^ abs_dx ^ abs_dy ^ flags
        frame = bytes([HEADER, CMD_LINE, abs_dx, abs_dy, flags, chk])

        n_steps = max(abs_dx, abs_dy, 1)
        timeout = max(4.0, n_steps * 0.030)

        with self._lock:                       # [SW-3]
            if not self.ser or not self.ser.is_open:
                self.comm_lost = True
                return False
            # [SW-4] una sola oportunidad: reintentar redibujaria el segmento
            self.stats['sent'] += 1
            try:
                self.ser.reset_input_buffer()
                self.ser.write(frame)
                self.ser.timeout = timeout
                resp = self.ser.read(1)
            except Exception:
                self._consecutive_failures += 1
                self.comm_lost = True
                self._last_speed_ok = None          # [SW-39]
                return False

        if resp and resp[0] == ACK:
            self.stats['ack'] += 1
            self._consecutive_failures = 0
            self.comm_lost = False
            return True
        if resp and resp[0] == NACK:
            self.stats['nack'] += 1
        else:
            self.stats['timeout'] += 1

        self._consecutive_failures += 1
        if self._consecutive_failures >= 5:
            self.comm_lost = True
            self._last_speed_ok = None              # [SW-39]
        return False

    # ─── MOVIMIENTO X / Y ────────────────────────────────────────

    @staticmethod
    def _sign(direction):
        """[SW-35] La posicion cacheada se actualiza con `direction *
        pasos`. Si alguien llama con direction=2 (o -3), pos_x avanza el
        doble que el eje real y todo el dibujo sale desplazado. La
        direccion es un SENTIDO, no un factor: se normaliza a ±1."""
        return 1 if direction > 0 else -1

    def step_x(self, direction, count=1):
        count = int(count)
        if count <= 0:                       # [SW-36] nada que mover:
            return True                      # ni backlash ni trama
        direction = self._sign(direction)

        comp = self._backlash_comp('x', direction)
        cmd = CMD_X_POS if direction > 0 else CMD_X_NEG
        if comp > 0:
            self.send_command(cmd, comp, retries=1)
        executed = 0
        remaining = count
        while remaining > 0:
            chunk = min(remaining, 255)
            if not self.send_command(cmd, chunk, retries=1):
                break
            executed += chunk
            remaining -= chunk
        self.pos_x += direction * executed
        self._maybe_save_position()
        return executed == count

    def step_y(self, direction, count=1):
        count = int(count)
        if count <= 0:                       # [SW-36]
            return True
        direction = self._sign(direction)

        comp = self._backlash_comp('y', direction)
        cmd = CMD_Y_POS if direction > 0 else CMD_Y_NEG
        if comp > 0:
            self.send_command(cmd, comp, retries=1)
        executed = 0
        remaining = count
        while remaining > 0:
            chunk = min(remaining, 255)
            if not self.send_command(cmd, chunk, retries=1):
                break
            executed += chunk
            remaining -= chunk
        self.pos_y += direction * executed
        self._maybe_save_position()
        return executed == count

    # ─── MOVIMIENTO Z ────────────────────────────────────────────

    def step_z(self, direction, count=1):
        """Jog relativo de Z. direction: +1 = subir pluma, -1 = bajar.

        [SW-2] Ya NO manda SET_SPEED: el firmware tiene VEL_Z propia,
        asi que el eje Z nunca hereda la velocidad rapida de X/Y.
        [SW-6] pos_z se satura en 0..255 igual que Z_POS en el micro.
        [SW-30] "subir" y "bajar" son SIEMPRE fisicos: el firmware ya
        traduce el sentido segun Z_DIR, aqui no hay nada que invertir.
        """
        count = int(count)
        if count <= 0:                       # [SW-36]
            return True
        direction = self._sign(direction)    # [SW-35]

        cmd = CMD_Z_POS if direction > 0 else CMD_Z_NEG
        executed = 0
        remaining = count
        while remaining > 0:
            chunk = min(remaining, 255)
            if not self.send_command(cmd, chunk, retries=1):
                break
            executed += chunk
            remaining -= chunk
        # +1 (subir) reduce Z_POS, -1 (bajar) lo aumenta
        self.pos_z = max(0, min(255, self.pos_z - direction * executed))
        self._maybe_save_position()          # [SW-10]
        return executed == count

    def pen_up(self):
        """Sube la pluma a Z_POS=0. Idempotente: el firmware calcula el
        delta real, asi que repetirlo no hace nada y nunca se pasa."""
        ok = self.send_command(CMD_PEN_UP, retries=3)
        if ok:
            self.pos_z = 0
        return ok

    def pen_down(self):
        """Baja la pluma a Z_POS=PEN_N. Idempotente y autocorrectivo:
        si Z se habia desviado, este comando lo lleva a la profundidad
        correcta (subiendo o bajando, lo que haga falta)."""
        ok = self.send_command(CMD_PEN_DOWN, retries=3)
        if ok:
            self.pos_z = self.pen_steps
        return ok

    def set_pen_steps(self, steps):
        """[SW-5] Ahora la profundidad de pluma SI llega al firmware."""
        steps = max(1, min(255, int(steps)))
        ok = self.send_command(CMD_SET_PEN_N, steps)
        if ok:
            self.pen_steps = steps
        return ok

    def set_speed_z(self, ms):
        """Velocidad del eje Z, independiente de X/Y. Minimo 4 ms
        (el firmware tambien lo limita, por si acaso)."""
        ms = max(4, min(255, int(ms)))
        ok = self.send_command(CMD_SET_SPD_Z, ms)
        if ok:
            self.z_speed = ms
        return ok

    def z_set_zero(self):
        """Define la posicion actual de Z como 'pluma arriba' (Z_POS=0).
        Usalo tras subir la pluma a mano o si el eje toco el tope."""
        ok = self.send_command(CMD_Z_SET_ZERO)
        if ok:
            self.pos_z = 0
        return ok

    def set_z_invert(self, invert, move_pen=True):
        """[SW-30] Sentido fisico del eje Z segun como este montado el
        porta-pluma.

        El problema: el mecanismo del eje Z se puede montar de dos
        formas y en una de ellas el giro que deberia SUBIR la pluma la
        BAJA. Sin esto, "pen up" en la UI dejaba la pluma clavada en el
        papel y "pen down" la levantaba.

        La inversion se hace EN EL FIRMWARE (C_ZDIR), no aqui. Es
        deliberado: si se emulara en el PC, Z_POS=0 significaria
        "arriba" con un montaje y "abajo" con el otro, y volveriamos a
        tener dos verdades sobre la misma variable — justo la doble
        maquina de estados que [SW-1] elimino. Con C_ZDIR:

          - Z_POS = 0      es SIEMPRE pluma arriba
          - Z_POS = PEN_N  es SIEMPRE pluma abajo
          - pen_up()/pen_down() siguen siendo absolutos e idempotentes
          - el flujo de calibracion (z_set_zero) no cambia

        move_pen: sube la pluma ANTES de cambiar el sentido. Es lo
        correcto en una peticion del usuario — con la pluma arriba
        Z_POS ya vale 0 y el estado sigue siendo coherente con el
        montaje nuevo. En sync_firmware() se pasa False porque ahi solo
        se esta reafirmando el valor que ya estaba puesto, y subir la
        pluma en cada reconexion seria un movimiento sorpresa.

        Devuelve False si el firmware no soporta C_ZDIR (responde NACK);
        en ese caso hay que reprogramar el micro con 8052_v2.asm.
        """
        invert = bool(invert)

        if self.simulate:
            self.z_invert = invert
            self.z_invert_supported = True
            return True

        if move_pen and invert != self.z_invert:
            # Con el sentido ANTIGUO, que es el que sigue vigente en el
            # micro en este instante. Asi Z_POS queda en 0 y el cambio
            # de sentido no deja la pluma en una posicion ambigua.
            self.pen_up()

        ok = self.send_command(CMD_Z_INVERT, 0x01 if invert else 0x00)
        if ok:
            self.z_invert = invert
            self.z_invert_supported = True
        elif not self.comm_lost:
            # Hubo respuesta, pero fue NACK: el micro no conoce C_ZDIR.
            self.z_invert_supported = False
        return ok

    def z_off(self):
        """Apaga las bobinas de Z. ATENCION: la pluma puede caer por
        gravedad; despues hay que recolocarla y llamar a z_set_zero()."""
        return self.send_command(CMD_Z_OFF)

    # ─── PASO SIMULTANEO XY ──────────────────────────────────────

    def step_xy(self, dx, dy):
        payload = 0
        if dx != 0:
            payload |= 0x02
            if dx < 0:
                payload |= 0x01
            self._update_dir('x', dx)
        if dy != 0:
            payload |= 0x08
            if dy < 0:
                payload |= 0x04
            self._update_dir('y', dy)

        ok = self.send_command(CMD_STEP_XY, payload, retries=1)
        if ok:
            self.pos_x += dx
            self.pos_y += dy
            self._maybe_save_position()
        return ok

    # ─── CONTROL ─────────────────────────────────────────────────

    def set_speed(self, ms):
        """Velocidad de X e Y. No afecta a Z.

        [SW-19] Cachea el valor para no reenviar la misma velocidad en
        cada segmento de arco (un circulo mandaba cientos de tramas
        identicas). El cache SOLO se actualiza si hubo ACK, y cualquier
        fallo lo invalida: nunca puede quedarse mintiendo.
        """
        ms = max(2, min(255, int(ms)))
        if ms == self._last_speed_ok:
            return True
        ok = self.send_command(CMD_SET_SPEED, ms)
        self._last_speed_ok = ms if ok else None
        return ok

    def motors_off(self):
        """[SW-9] Apaga SOLO X e Y. Z sigue energizada para que la
        pluma no se caiga. Para apagar Z usa z_off() a proposito."""
        return self.send_command(CMD_MOTORS_OFF)

    def ping(self):
        return self.send_command(CMD_PING)

    # ─── BACKLASH ────────────────────────────────────────────────

    def set_backlash(self, x_steps=0, y_steps=0):
        self.backlash_x = max(0, int(x_steps))
        self.backlash_y = max(0, int(y_steps))

    def _backlash_comp(self, axis, new_dir):
        if axis == 'x':
            if (self._last_dir_x != 0 and new_dir != 0
                    and self._last_dir_x != new_dir):
                self._last_dir_x = new_dir
                return self.backlash_x
            if new_dir != 0:
                self._last_dir_x = new_dir
        elif axis == 'y':
            if (self._last_dir_y != 0 and new_dir != 0
                    and self._last_dir_y != new_dir):
                self._last_dir_y = new_dir
                return self.backlash_y
            if new_dir != 0:
                self._last_dir_y = new_dir
        return 0

    def _update_dir(self, axis, direction):
        if axis == 'x':
            self._last_dir_x = direction
        elif axis == 'y':
            self._last_dir_y = direction

    def compensate_backlash_xy(self, dir_x, dir_y):
        if dir_x != 0:
            comp = self._backlash_comp('x', dir_x)
            if comp > 0:
                cmd = CMD_X_POS if dir_x > 0 else CMD_X_NEG
                self.send_command(cmd, comp, retries=1)
        if dir_y != 0:
            comp = self._backlash_comp('y', dir_y)
            if comp > 0:
                cmd = CMD_Y_POS if dir_y > 0 else CMD_Y_NEG
                self.send_command(cmd, comp, retries=1)

    # ─── UTILIDADES ──────────────────────────────────────────────

    def reset_position(self):
        """Origen XY. NO toca Z: el cero de la pluma se fija aparte
        con z_set_zero(), que es una operacion fisica distinta."""
        self.pos_x = 0
        self.pos_y = 0
        self._last_dir_x = 0
        self._last_dir_y = 0

    def _save_position(self):
        """[SW-37] Escritura atomica. Antes se escribia in-place: si el
        proceso moria a mitad (o se cerraba el portatil), el fichero
        quedaba truncado y al arrancar se perdia la posicion entera."""
        data = {
            "pos_x": self.pos_x,
            "pos_y": self.pos_y,
            "pos_z": self.pos_z,
            "pen_down": self.pen_down_flag,
            "timestamp": time.time(),
        }
        tmp = POSITION_FILE + '.tmp'
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, POSITION_FILE)
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass

    def _maybe_save_position(self):
        """Se llama una vez por movimiento (no por paso), asi que esto
        guarda cada 100 MOVIMIENTOS. Es a proposito: escribir en cada
        segmento de un arco haria cientos de fsync por circulo."""
        self._step_counter += 1
        if self._step_counter >= 100:
            self._step_counter = 0
            self._save_position()

    @staticmethod
    def load_last_position():
        """[SW-38] Valida el contenido. El fichero lo puede haber tocado
        cualquiera (o haberse quedado a medias en una version anterior),
        y sus valores acaban en pos_x/pos_y, que mandan sobre el area de
        trabajo entera."""
        try:
            if not os.path.exists(POSITION_FILE):
                return None
            with open(POSITION_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return None

            ts = data.get("timestamp")
            if not isinstance(ts, (int, float)):
                return None
            age_seconds = time.time() - ts
            # Un timestamp futuro significa reloj cambiado: no fiarse.
            if age_seconds < 0 or age_seconds > POSITION_MAX_AGE_S:
                return None

            clean = {}
            for key in ("pos_x", "pos_y", "pos_z"):
                val = data.get(key)
                if not isinstance(val, (int, float)) or isinstance(val, bool):
                    return None
                clean[key] = int(val)

            clean["pen_down"] = bool(data.get("pen_down", False))
            clean["age_seconds"] = age_seconds
            return clean
        except Exception:
            return None

    @staticmethod
    def clear_last_position():
        try:
            if os.path.exists(POSITION_FILE):
                os.remove(POSITION_FILE)
        except Exception:
            pass

    def print_stats(self):
        s = self.stats
        total = s['sent']
        if total == 0:
            print("  Sin comandos enviados.")
            return
        success = s['ack'] / total * 100 if total else 0
        print(f"  Comandos: {total} enviados, {s['ack']} ACK, "
              f"{s['nack']} NACK, {s['timeout']} timeout, "
              f"{s['retries']} reintentos ({success:.1f}% exito)")
        print(f"  Posicion: X={self.pos_x} Y={self.pos_y} Z={self.pos_z} "
              f"(pen_down={self.pen_down_flag})")
        print(f"  Eje Z: {'INVERTIDO' if self.z_invert else 'normal'} "
              f"(porta-pluma), VEL_Z={self.z_speed}ms, PEN_N={self.pen_steps}")
