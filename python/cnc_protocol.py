"""
esta se encarga de la comunicacion con el 8052
8
"""

import os
import sys
import json
import time
import threading

import serial
import serial.tools.list_ports


# constantes del protocolo

HEADER = 0xAA
ACK    = 0x06
NACK   = 0x15

# comandos de movimiento
CMD_X_POS   = 0x01
CMD_X_NEG   = 0x02
CMD_Y_POS   = 0x03
CMD_Y_NEG   = 0x04
CMD_STEP_XY = 0x07
CMD_LINE    = 0x08
CMD_Z_POS   = 0x0A          
CMD_Z_NEG   = 0x0B          

# comandos de control
CMD_PEN_UP     = 0x10
CMD_PEN_DOWN   = 0x11
CMD_SET_SPEED  = 0x12       # velocidad de X e Y
CMD_MOTORS_OFF = 0x13      
CMD_PING       = 0x20
CMD_GET_STATE  = 0x21      
CMD_SET_PEN_N  = 0x22       
CMD_SET_SPD_Z  = 0x23       
CMD_Z_OFF      = 0x24      
CMD_Z_SET_ZERO = 0x25       
CMD_Z_INVERT   = 0x26       

BAUD = 9600


Z_SPEED_DEFAULT = 8
XY_SPEED_DEFAULT = 5

POSITION_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '.last_position'))

POSITION_MAX_AGE_S = 7200


class CNCProtocol:

    def __init__(self, port=None, simulate=False):
        self.simulate = simulate
        self.ser = None
        self.port = port


        self._lock = threading.RLock()

        # posicion en pasos enteros
        self.pos_x = 0
        self.pos_y = 0
        self.pos_z = 0          

        self.pen_steps = 100
        self.z_speed = Z_SPEED_DEFAULT
        self._last_speed_ok = None   # cache de VEL confirmada por ACK


        self.z_invert = False
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


    @property
    def pen_down_flag(self):
        """no hay flag propio de pluma, se deriva de Z_POS que es la
        unica fuente de verdad y se puede releer con get_state()"""
        return self.pos_z >= max(1, self.pen_steps)


    def connect(self):
        if self.simulate:
            print("  [SIM] Modo simulacion activo")
            return True

        if self.port is None:
            self.port = self._auto_detect_port()
        if self.port is None:
            return False

        with self._lock:
            try:
                self.ser = serial.Serial(self.port, BAUD, timeout=0.5)
            except (serial.SerialException, OSError, ValueError) as e:
                print(f"  ERROR: no se pudo abrir {self.port}: {e}")
                self.ser = None
                return False

            try:
                time.sleep(0.3)
                self.ser.reset_input_buffer()


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
            self._last_speed_ok = None     
            self.z_invert_supported = None

    def _auto_detect_port(self):
        puertos = serial.tools.list_ports.comports()
        if not puertos:
            print("  ERROR: No se encontraron puertos COM")
            return None
        if len(puertos) == 1:
            print(f"  Puerto auto-detectado: {puertos[0].device}")
            return puertos[0].device
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


    def sync_firmware(self):
        """alinea pc y micro, llamar al conectar y ante cualquier sospecha
        de desincronizacion. primero se empuja lo que manda el pc (VEL_Z,
        PEN_N, Z_DIR) y recien despues se lee el estado resultante, asi
        lo cacheado es lo que el micro confirmo y no lo que creiamos"""
        if self.simulate:
            self.z_invert_supported = True
            return True

        self._last_speed_ok = None         
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
        """lee el estado real del micro: ACK + Z_POS + PEN_N + VEL + VEL_Z
        + Z_DIR (6 bytes). los primeros 5 son obligatorios, el 6to (Z_DIR)
        es opcional para poder hablar con firmware viejo que no lo tiene -
        si no llega, z_invert queda None y z_invert_supported en False asi
        la ui puede avisar "reflashea el micro" en vez de mentir"""
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
                    self.ser.timeout = 0.25
                    extra = self.ser.read(1)
            except Exception:
                self.comm_lost = True
                self._last_speed_ok = None
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


    def send_command(self, cmd, payload=0x00, retries=2, timeout=None):
        """manda [AA][CMD][PAY][CHK] y espera ACK, devuelve True/False.
        ojo con retries: movimientos relativos (X/Y/Z) no son idempotentes
        en el firmware, si se pierde el ACK despues de ejecutar un reintento
        mueve de nuevo. por eso esos van con retries=1, los de pluma
        (absolutos e idempotentes) si pueden reintentar tranquilos"""
        if self.simulate:
            self.stats['sent'] += 1
            self.stats['ack'] += 1
            self._consecutive_failures = 0
            return True

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

        with self._lock:                      
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

                    self._consecutive_failures += 1
                    self.comm_lost = True
                    self._last_speed_ok = None
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
            self._last_speed_ok = None
        return False

    def send_line_segment(self, abs_dx, abs_dy, dir_x, dir_y):
        """trama extendida [AA][08][DX][DY][FLAGS][CHK], bresenham en firmware"""
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

        with self._lock:
            if not self.ser or not self.ser.is_open:
                self.comm_lost = True
                return False
            self.stats['sent'] += 1
            try:
                self.ser.reset_input_buffer()
                self.ser.write(frame)
                self.ser.timeout = timeout
                resp = self.ser.read(1)
            except Exception:
                self._consecutive_failures += 1
                self.comm_lost = True
                self._last_speed_ok = None
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
            self._last_speed_ok = None
        return False

    # movimiento x/y

    @staticmethod
    def _sign(direction):
        """la posicion cacheada se actualiza con direction * pasos, si
        alguien manda direction=2 pos_x avanzaria el doble que el eje
        real. direccion es un sentido no un factor, se normaliza a ±1"""
        return 1 if direction > 0 else -1

    def step_x(self, direction, count=1):
        count = int(count)
        if count <= 0:                      
            return True                      
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
        if count <= 0:
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

    # movimiento z

    def step_z(self, direction, count=1):
        """jog relativo de Z, +1 sube la pluma, -1 baja. no manda
        SET_SPEED, Z tiene su propia VEL_Z asi que nunca hereda la
        velocidad rapida de x/y. "subir"/"bajar" son siempre fisicos,
        el firmware traduce el sentido segun Z_DIR, aca no hay que invertir"""
        count = int(count)
        if count <= 0:
            return True
        direction = self._sign(direction)

        cmd = CMD_Z_POS if direction > 0 else CMD_Z_NEG
        executed = 0
        remaining = count
        while remaining > 0:
            chunk = min(remaining, 255)
            if not self.send_command(cmd, chunk, retries=1):
                break
            executed += chunk
            remaining -= chunk
        self.pos_z = max(0, min(255, self.pos_z - direction * executed))
        self._maybe_save_position()
        return executed == count

    def pen_up(self):
        """sube la pluma a Z_POS=0, idempotente - el firmware calcula el
        delta real asi que repetirlo no hace nada raro"""
        ok = self.send_command(CMD_PEN_UP, retries=3)
        if ok:
            self.pos_z = 0
        return ok

    def pen_down(self):
        """baja la pluma a Z_POS=PEN_N, idempotente y autocorrectivo: si Z
        se habia desviado esto la lleva a la profundidad que corresponde"""
        ok = self.send_command(CMD_PEN_DOWN, retries=3)
        if ok:
            self.pos_z = self.pen_steps
        return ok

    def set_pen_steps(self, steps):
        """profundidad de pluma, esto si llega hasta el firmware"""
        steps = max(1, min(255, int(steps)))
        ok = self.send_command(CMD_SET_PEN_N, steps)
        if ok:
            self.pen_steps = steps
        return ok

    def set_speed_z(self, ms):
        """velocidad de Z, independiente de x/y, minimo 4ms (el firmware
        tambien lo limita por las dudas)"""
        ms = max(4, min(255, int(ms)))
        ok = self.send_command(CMD_SET_SPD_Z, ms)
        if ok:
            self.z_speed = ms
        return ok

    def z_set_zero(self):
        """define la posicion actual como 'pluma arriba' (Z_POS=0), usar
        despues de subir la pluma a mano o si el eje toco el tope"""
        ok = self.send_command(CMD_Z_SET_ZERO)
        if ok:
            self.pos_z = 0
        return ok

    def set_z_invert(self, invert, move_pen=True):
        """sentido fisico de Z segun como quedo montado el porta-pluma -
        el mecanismo se puede armar de dos formas y en una el giro que
        deberia subir la pluma la baja. la inversion la hace el firmware
        (C_ZDIR) a proposito, si se emulara aca Z_POS=0 significaria
        "arriba" en un montaje y "abajo" en el otro, dos verdades para la
        misma variable de nuevo. move_pen sube la pluma antes de cambiar
        el sentido (lo correcto cuando lo pide el usuario); sync_firmware
        pasa False pq ahi solo se reafirma lo que ya estaba, no hace
        falta el movimiento sorpresa. devuelve False si el firmware no
        conoce C_ZDIR (NACK), ahi toca reflashear"""
        invert = bool(invert)

        if self.simulate:
            self.z_invert = invert
            self.z_invert_supported = True
            return True

        if move_pen and invert != self.z_invert:
            self.pen_up()

        ok = self.send_command(CMD_Z_INVERT, 0x01 if invert else 0x00)
        if ok:
            self.z_invert = invert
            self.z_invert_supported = True
        elif not self.comm_lost:
            self.z_invert_supported = False
        return ok

    def z_off(self):
        """apaga las bobinas de Z, ojo que la pluma puede caer por
        gravedad, hay que recolocarla y llamar z_set_zero() despues"""
        return self.send_command(CMD_Z_OFF)

    # paso simultaneo xy

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

    # control

    def set_speed(self, ms):
        """velocidad de x/y, no afecta a Z. cachea el valor para no
        reenviar la misma velocidad en cada segmento de un arco (un
        circulo mandaba cientos de tramas iguales), el cache solo se
        actualiza si hubo ACK asi que nunca queda mintiendo"""
        ms = max(2, min(255, int(ms)))
        if ms == self._last_speed_ok:
            return True
        ok = self.send_command(CMD_SET_SPEED, ms)
        self._last_speed_ok = ms if ok else None
        return ok

    def motors_off(self):
        """apaga solo x/y, Z sigue energizada para que la pluma no se
        caiga - para apagar Z esta z_off() aparte"""
        return self.send_command(CMD_MOTORS_OFF)

    def ping(self):
        return self.send_command(CMD_PING)

    # backlash

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

    # utilidades

    def reset_position(self):
        """origen xy, no toca Z - el cero de pluma se fija aparte con
        z_set_zero(), es otra operacion"""
        self.pos_x = 0
        self.pos_y = 0
        self._last_dir_x = 0
        self._last_dir_y = 0

    def _save_position(self):
        """escritura atomica, si el proceso muere a mitad no queda un
        json truncado que te hace perder la posicion entera"""
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
        """se llama una vez por movimiento (no por paso) asi que guarda
        cada 100 movimientos, a proposito - si guardara por segmento de
        arco serian cientos de fsync por cada circulo"""
        self._step_counter += 1
        if self._step_counter >= 100:
            self._step_counter = 0
            self._save_position()

    @staticmethod
    def load_last_position():
        """valida el contenido pq el archivo lo puede haber tocado
        cualquiera, y estos valores terminan mandando sobre pos_x/pos_y"""
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
