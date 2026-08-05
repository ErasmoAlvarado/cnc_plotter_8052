"""


la conversion mm a pasos , cerebro del plotter
"""

import math
import sys
import time

from cnc_protocol import CNCProtocol
from gcode_parse import arc_to_segments, parse_gcode_line   # noqa: F401
from gcode_transform import IDENTITY, GcodeTransform
from gcode_walk import ArcEvent, DwellEvent, MoveEvent, PenEvent, bounds_of, walk
from soft_limits import LimitExceeded, check_bounds, check_point



def bresenham_steps(x0, y0, x1, y1):
    """lista de pasos dx dy por eje para una recta.
    se usa en modo interactivo y en tests, el dibujo normal usa CMD_LINE
    que hace bresenham dentro del firmware"""
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy

    steps = []
    while x0 != x1 or y0 != y1:
        e2 = 2 * err
        mx, my = 0, 0
        if e2 >= dy:
            err += dy
            x0 += sx
            mx = sx
        if e2 <= dx:
            err += dx
            y0 += sy
            my = sy
        steps.append((mx, my))
    return steps


def gcode_bounds(lines):
    """compat con la tupla que esperaba el codigo viejo.
    la caja la calcula gcode_walk.bounds_of con el mismo interprete que dibuja.
    esto no es un interprete aparte"""
    from gcode_walk import command_line_count
    b = bounds_of(lines)
    return b.min_x, b.max_x, b.min_y, b.max_y, command_line_count(lines)


class CNCPlotter:

    def __init__(self, proto, steps_per_mm_x=170.67, steps_per_mm_y=170.67,
                 max_x_mm=40.0, max_y_mm=40.0, speed_draw=5, speed_rapid=6,
                 z_pen_down_threshold=0.0, enforce_soft_limits=True):
        """proto ya debe estar conectado. steps_per_mm default sale de
        4096 pasos por revolucion sobre 24mm de circunferencia, unos 170.67.
        speed_z no esta aca, vive en el firmware aparte"""
        self.proto = proto
        self.spm_x = steps_per_mm_x
        self.spm_y = steps_per_mm_y
        self.max_x = max_x_mm
        self.max_y = max_y_mm
        self.speed_draw = speed_draw
        self.speed_rapid = speed_rapid
        self.z_pen_down_threshold = z_pen_down_threshold
        self.enforce_soft_limits = enforce_soft_limits

        self.abs_mode = True        
        self.gc_x = 0.0
        self.gc_y = 0.0
        self.feedrate = 100.0

        self.lines_processed = 0
        self.total_steps = 0
        self.t_start = 0

        self.warnings = []

        self.abort_check = None


        self._pen_cmd_sent = None

    @classmethod
    def from_config(cls, proto, cfg):
        """arma el plotter desde la config y empuja al firmware
        la profundidad y velocidad de pluma"""
        plotter = cls(
            proto,
            steps_per_mm_x=cfg.get("steps_per_mm_x", 170.67),
            steps_per_mm_y=cfg.get("steps_per_mm_y", 170.67),
            max_x_mm=cfg.get("max_x_mm", 40.0),
            max_y_mm=cfg.get("max_y_mm", 40.0),
            speed_draw=cfg.get("speed_draw", 5),
            speed_rapid=cfg.get("speed_rapid", 6),
            z_pen_down_threshold=cfg.get("z_pen_down_threshold", 0.0),
            enforce_soft_limits=cfg.get("enforce_soft_limits", True),
        )
        proto.backlash_x = cfg.get("backlash_x", 0)
        proto.backlash_y = cfg.get("backlash_y", 0)
        proto.pen_steps = cfg.get("pen_steps", 100)
        proto.z_speed = cfg.get("speed_z", 8)
        proto.z_invert = bool(cfg.get("pen_invert", False))
        proto.sync_firmware()      # manda VEL_Z + PEN_N + Z_DIR y relee
        return plotter

    def _aborted(self):
        return bool(self.abort_check and self.abort_check())


    def mm_to_steps_x(self, mm):
        return round(mm * self.spm_x)

    def mm_to_steps_y(self, mm):
        return round(mm * self.spm_y)

    def move_to_steps(self, target_x, target_y, draw=False):
        dx = target_x - self.proto.pos_x
        dy = target_y - self.proto.pos_y
        if dx == 0 and dy == 0:
            return
        if draw:
            self._draw_line(target_x, target_y, dx, dy)
        else:
            self._rapid_move(dx, dy)

    def _rapid_move(self, dx, dy):
        """rapido, batch por eje, x e y van secuenciales"""
        self.proto.set_speed(self.speed_rapid)
        if dx != 0:
            self.proto.step_x(1 if dx > 0 else -1, abs(dx))
        if dy != 0:
            self.proto.step_y(1 if dy > 0 else -1, abs(dy))
        self.total_steps += abs(dx) + abs(dy)

    def _draw_line(self, tx, ty, dx, dy):
        """linea dibujada, las diagonales van por CMD_LINE con bresenham en el firmware usando Timer0
        para evitar el jitter de USB que hacia resonar los motores"""
        self.proto.set_speed(self.speed_draw)

        if dy == 0:                       # horizontal 
            self.proto.step_x(1 if dx > 0 else -1, abs(dx))
            self.total_steps += abs(dx)
            return
        if dx == 0:                       # vertical
            self.proto.step_y(1 if dy > 0 else -1, abs(dy))
            self.total_steps += abs(dy)
            return

        dir_x = 1 if dx > 0 else -1
        dir_y = 1 if dy > 0 else -1
        self.proto.compensate_backlash_xy(dir_x, dir_y)

        abs_dx, abs_dy = abs(dx), abs(dy)
        max_steps = max(abs_dx, abs_dy)

        if max_steps <= 255:

            if self.proto.send_line_segment(abs_dx, abs_dy, dir_x, dir_y):
                self.proto.pos_x = tx
                self.proto.pos_y = ty
                self.proto._maybe_save_position()
                self.total_steps += max_steps
        else:
            self._draw_line_chunked(abs_dx, abs_dy, dir_x, dir_y)

    def _draw_line_chunked(self, abs_dx, abs_dy, dir_x, dir_y):
        """corta una linea larga en trozos de max 255 pasos.
        el acumulador entero suma los trozos exacto, abs_dx y abs_dy sin drift.
        no recibe el destino, pos_x y pos_y solo suman lo que el micro confirmo.
        asi si se corta a mitad no queda una posicion mentirosa"""
        major = max(abs_dx, abs_dy)
        x_is_major = abs_dx >= abs_dy
        minor_total = min(abs_dx, abs_dy)

        n_segs = (major + 254) // 255
        prev_minor_acc = 0

        for seg in range(n_segs):
            if self._aborted():          
                return
            seg_start = seg * 255
            seg_end = min(seg_start + 255, major)
            seg_major = seg_end - seg_start

            cur_minor_acc = round(seg_end * minor_total / major) if major else 0
            seg_minor = cur_minor_acc - prev_minor_acc
            prev_minor_acc = cur_minor_acc

            if x_is_major:
                seg_dx, seg_dy = seg_major, seg_minor
            else:
                seg_dx, seg_dy = seg_minor, seg_major

            if not self.proto.send_line_segment(seg_dx, seg_dy, dir_x, dir_y):
                break                    
            self.proto.pos_x += dir_x * seg_dx
            self.proto.pos_y += dir_y * seg_dy
            self.proto._maybe_save_position()
            self.total_steps += max(seg_dx, seg_dy)

    def _check_area(self, x_mm, y_mm):
        """ultima red antes de mover, tira LimitExceeded.
        si llega aca es porque el origen se movio a mano despues del prevuelo.
        sin finales de carrera, seguir empujando contra el tope pierde pasos"""
        if not self.enforce_soft_limits:
            return
        violation = check_point(x_mm, y_mm, self.max_x, self.max_y)
        if violation is None:
            return
        if violation.message() not in self.warnings:
            self.warnings.append(violation.message())
        raise LimitExceeded(violation)

    def line_to(self, x_mm, y_mm):
        """dibuja hasta la posicion absoluta en mm"""
        self._check_area(x_mm, y_mm)
        self.move_to_steps(self.mm_to_steps_x(x_mm),
                           self.mm_to_steps_y(y_mm), draw=True)
        self.gc_x, self.gc_y = x_mm, y_mm

    def rapid_to(self, x_mm, y_mm):
        """rapido hasta la posicion en mm con la pluma arriba"""
        self._check_area(x_mm, y_mm)
        self._set_pen(False)
        self.move_to_steps(self.mm_to_steps_x(x_mm),
                           self.mm_to_steps_y(y_mm), draw=False)
        self.gc_x, self.gc_y = x_mm, y_mm

    @property
    def chord_tol(self):
        """error de cuerda max al partir arcos: un paso de motor, mas fino
        que eso no se nota y solo multiplica segmentos de mas"""
        return min(1.0 / self.spm_x, 1.0 / self.spm_y)

    def arc_to(self, x_mm, y_mm, i_mm, j_mm, clockwise=True, draw=True):
        """arco G2 o G3 desde la posicion actual, lo usan los patrones de
        prueba como draw_circle que piden arcos sin pasar por un archivo"""
        segments = arc_to_segments(self.gc_x, self.gc_y, x_mm, y_mm,
                                   i_mm, j_mm, clockwise, self.chord_tol)
        self.trace_points(segments, draw)

    def trace_points(self, points, draw=True):
        """recorre una polilinea ya calculada.
        la velocidad se fija una sola vez antes del loop, no por segmento.
        un circulo mandaria cientos de tramas SET_SPEED iguales si no.
        con draw=False recorre con la pluma arriba, para posicionar por una curva"""
        self.proto.set_speed(self.speed_draw if draw else self.speed_rapid)
        for sx, sy in points:
            if self._aborted():
                return
            if draw:
                self.line_to(sx, sy)
            else:
                self.rapid_to(sx, sy)

    def pen_up(self):
        return self._set_pen(False)

    def pen_down(self):
        return self._set_pen(True)

    def invalidate_pen_cache(self):
        """olvida el estado de pluma cacheado.
        llamar si algo externo mueve Z por su cuenta, jog manual, resync o z_set_zero.
        asi el proximo pen_up o pen_down se manda de verdad y no se asume"""
        self._pen_cmd_sent = None

    def set_pen_steps(self, steps):
        """profundidad de pluma, va al firmware de verdad, CMD_SET_PEN_N"""
        ok = self.proto.set_pen_steps(steps)
        self.invalidate_pen_cache()
        return ok

    def z_set_zero(self):
        """fija la altura actual como el cero de 'arriba'"""
        ok = self.proto.z_set_zero()
        self.invalidate_pen_cache()
        return ok

    def set_pen_invert(self, invert):
        """sentido fisico de Z, si el portapluma quedo al reves.
        la inversion la hace el firmware, ver CNCProtocol.set_z_invert"""
        ok = self.proto.set_z_invert(invert)
        self.invalidate_pen_cache()
        return ok

    def go_home(self):
        self.rapid_to(0, 0)

    def plot_gcode_file(self, filename):
        try:
            with open(filename, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
        except FileNotFoundError:
            print(f"  ERROR: Archivo no encontrado: {filename}")
            return False
        print(f"  Archivo cargado: {filename} ({len(lines)} lineas)")
        return self.plot_gcode_lines(lines)

    def begin_job(self):
        """deja el interprete en estado limpio, lo llaman plot_gcode_lines()
        y el hilo de job de la api - sin esto el segundo trabajo de la
        sesion arrastra el estado del primero"""
        self.t_start = time.perf_counter()
        self.lines_processed = 0
        self.total_steps = 0
        self.warnings = []

        self.abs_mode = True
        self.feedrate = 100.0

        self.invalidate_pen_cache()

        self._sync_gc_from_steps()

    def _sync_gc_from_steps(self):
        self.gc_x = self.proto.pos_x / self.spm_x if self.spm_x else 0.0
        self.gc_y = self.proto.pos_y / self.spm_y if self.spm_y else 0.0

    def events(self, lines, transform: GcodeTransform = IDENTITY):
        """gcode_walk con los parametros de esta maquina puesta, un solo
        lugar donde se decide umbral de pluma / tolerancia de cuerda /
        estado inicial, asi preview y pre-vuelo piden el mismo recorrido"""
        return walk(lines,
                    z_pen_down_threshold=self.z_pen_down_threshold,
                    chord_tol=self.chord_tol,
                    transform=transform,
                    initial_pen_down=self.proto.pen_down_flag)

    def plot_gcode_lines(self, lines, transform: GcodeTransform = IDENTITY):
        """ejecuta una lista de lineas de g-code"""
        total = len(lines)
        self.begin_job()


        if self.enforce_soft_limits:
            b = bounds_of(lines, self.z_pen_down_threshold,
                          self.chord_tol, transform)
            violation = check_bounds(b, self.max_x, self.max_y)
            if violation is not None:
                print(f"  ERROR: el trabajo ocupa X[{b.min_x:.1f}, {b.max_x:.1f}] "
                      f"Y[{b.min_y:.1f}, {b.max_y:.1f}] mm y el area util es "
                      f"{self.max_x}x{self.max_y} mm.")
                print(f"  {violation.message()}. No se ha movido nada.")
                return False

        print(f"  Ejecutando {total} lineas de G-code...")

        try:
            for ev in self.events(lines, transform):
                if self._aborted():
                    print("\n  Abortado.")
                    break
                if getattr(self.proto, 'comm_lost', False):
                    print("\n  ERROR: comunicacion perdida con el MCU.")
                    break

                self.exec_event(ev)
                self.lines_processed = ev.line + 1

                if self.lines_processed % 20 == 0:
                    elapsed = time.perf_counter() - self.t_start
                    pct = self.lines_processed / total * 100
                    print(f"\r  [{pct:5.1f}%] linea {self.lines_processed}/{total} "
                          f"pos=({self.gc_x:.1f},{self.gc_y:.1f})mm "
                          f"pasos={self.total_steps} t={elapsed:.0f}s",
                          end='', flush=True)
        except LimitExceeded as e:
            print(f"\n  ERROR: {e}. Trabajo detenido.")
            return False

        elapsed = time.perf_counter() - self.t_start
        print(f"\n  Completado: {self.lines_processed} lineas, "
              f"{self.total_steps} pasos, {elapsed:.1f}s")
        for w in self.warnings:
            print(f"  AVISO: {w}")
        return True

    def exec_event(self, ev):
        """traduce un evento de gcode_walk a movimiento real - toda la
        interpretacion del g-code ya la hizo el walker, aca solo se mueve"""
        if isinstance(ev, MoveEvent):
            if ev.draw:
                self.proto.set_speed(self.speed_draw)
                self.line_to(ev.x, ev.y)
            else:
                self.rapid_to(ev.x, ev.y)
        elif isinstance(ev, ArcEvent):
            self.trace_points(ev.points, ev.draw)
        elif isinstance(ev, PenEvent):
            self._set_pen(ev.down)
        elif isinstance(ev, DwellEvent):
            time.sleep(ev.seconds)

    def _set_pen(self, down):
        """unico punto por donde pasan todos los cambios de pluma. no
        reenvia si ya esta en el estado pedido - pen_up/down son
        idempotentes en el firmware asi que repetir no rompe nada, pero
        cuesta un viaje de UART entero y hay post-procesadores que ponen
        la misma Z en cada linea del archivo. _pen_cmd_sent arranca en
        None en cada trabajo asi la primera pluma siempre se manda de
        verdad"""
        if self._pen_cmd_sent is down:
            return True
        ok = self.proto.pen_down() if down else self.proto.pen_up()

        self._pen_cmd_sent = down if ok else None
        return ok



    # patrones 

    def draw_square(self, size_mm=10):
        print(f"  Dibujando cuadrado {size_mm}x{size_mm}mm...")
        self.rapid_to(0, 0)
        self.pen_down()
        self.line_to(size_mm, 0)
        self.line_to(size_mm, size_mm)
        self.line_to(0, size_mm)
        self.line_to(0, 0)
        self.pen_up()
        print("  OK. Medir con regla para calibrar steps_per_mm.")

    def draw_triangle(self, size_mm=15):
        print(f"  Dibujando triangulo lado={size_mm}mm...")
        h = size_mm * math.sqrt(3) / 2
        self.rapid_to(0, 0)
        self.pen_down()
        self.line_to(size_mm, 0)
        self.line_to(size_mm / 2, h)
        self.line_to(0, 0)
        self.pen_up()
        print("  OK.")

    def draw_circle(self, radius_mm=5, cx_mm=None, cy_mm=None):
        if cx_mm is None:
            cx_mm = radius_mm + 1
        if cy_mm is None:
            cy_mm = radius_mm + 1
        print(f"  Dibujando circulo r={radius_mm}mm centro=({cx_mm},{cy_mm})...")
        start_x, start_y = cx_mm + radius_mm, cy_mm
        self.rapid_to(start_x, start_y)
        self.pen_down()
        self.arc_to(cx_mm - radius_mm, cy_mm, -radius_mm, 0, clockwise=True)
        self.arc_to(start_x, start_y, radius_mm, 0, clockwise=True)
        self.pen_up()
        print("  OK.")

    def draw_star(self, size_mm=12):
        print(f"  Dibujando estrella r={size_mm}mm...")
        r = size_mm / 2
        cx = cy = r + 1
        pts = [(cx + r * math.cos(math.radians(90 + k * 72)),
                cy + r * math.sin(math.radians(90 + k * 72))) for k in range(5)]
        self.rapid_to(*pts[0])
        self.pen_down()
        for idx in [2, 4, 1, 3, 0]:
            self.line_to(*pts[idx])
        self.pen_up()
        print("  OK.")

    def draw_calibration_grid(self, spacing_mm=5, count=4):
        total = spacing_mm * count
        print(f"  Dibujando grilla {total}x{total}mm "
              f"({count}x{count} celdas de {spacing_mm}mm)...")
        for i in range(count + 1):
            y = i * spacing_mm
            self.rapid_to(0, y)
            self.pen_down()
            self.line_to(total, y)
            self.pen_up()
        for i in range(count + 1):
            x = i * spacing_mm
            self.rapid_to(x, 0)
            self.pen_down()
            self.line_to(x, total)
            self.pen_up()
        self.rapid_to(0, 0)
        print(f"  OK. Cada celda debe medir {spacing_mm}mm exactos.")

    # calibracion 

    def calibrate_steps(self):
        print("\n  ═══ CALIBRACION DE PRECISION ═══")
        print("  Se dibuja una linea de referencia de 20mm en X...")
        target_mm = 20.0
        self.proto.reset_position()
        self.gc_x = self.gc_y = 0.0
        self.pen_down()
        self.line_to(target_mm, 0)
        self.pen_up()

        print(f"  Pasos enviados: {self.proto.pos_x}")
        print(f"  Valor teorico:  {self.mm_to_steps_x(target_mm)} pasos\n")

        try:
            real = float(input("  Medir la linea real con regla (mm): "))
            if real > 0:
                new_spm = self.proto.pos_x / real
                print(f"  steps_per_mm actual: {self.spm_x:.2f}")
                print(f"  steps_per_mm nuevo:  {new_spm:.2f}")
                print(f"  Error: {abs(target_mm - real):.2f}mm "
                      f"({abs(target_mm - real)/target_mm*100:.1f}%)")
                if input("  Aplicar? (s/n): ").strip().lower() == 's':
                    self.spm_x = self.spm_y = new_spm
                    print(f"  Aplicado: {new_spm:.2f} steps/mm")
        except ValueError:
            print("  Valor invalido, calibracion cancelada.")

        self.rapid_to(0, 0)
        self.proto.reset_position()
        self.gc_x = self.gc_y = 0.0

    def calibrate_backlash(self):
        print("\n  ═══ CALIBRACION DE BACKLASH ═══")
        print("  Es el juego mecanico de los engranajes: al invertir la")
        print("  direccion, los primeros pasos se pierden.\n")
        n_steps = 200
        print(f"  Moviendo X +{n_steps} pasos...")
        self.proto.step_x(+1, n_steps)
        input("  Marcar la posicion actual con lapiz. [Enter]")
        print(f"  Moviendo X -{n_steps} pasos...")
        self.proto.step_x(-1, n_steps)
        print("  Si volvio EXACTO a la marca: backlash = 0")
        print("  Si se quedo corto: esa diferencia es el backlash.")
        try:
            bl = int(input("  Pasos de diferencia (0 si esta bien): "))
            if bl >= 0:
                self.proto.set_backlash(bl, bl)
                print(f"  Backlash configurado: X={bl}, Y={bl} pasos")
        except ValueError:
            pass
        self.proto.reset_position()
        self.gc_x = self.gc_y = 0.0

    def calibrate_pen(self):
        """calibracion de pluma con Z absoluto: fija un cero fisico y desde
        ahi pen_up/pen_down son absolutos. si el porta-pluma quedo al
        reves lo primero es la opcion V, todo lo demas depende de eso"""
        print("\n  ═══ CALIBRACION DE PLUMA (eje Z) ═══")
        print("  Orden recomendado:  V → U/J hasta la altura segura → Z → N → T\n")
        print("  V = invertir sentido del eje Z (porta-pluma al reves)")
        print("  U = subir 10 pasos   J = bajar 10 pasos")
        print("  Z = fijar AQUI el cero de 'pluma arriba'")
        print("  N = fijar profundidad   T = probar ciclo   Q = salir\n")
        while True:
            sentido = 'INVERTIDO' if self.proto.z_invert else 'normal'
            cmd = input(f"  [Z_POS={self.proto.pos_z} "
                        f"sentido={sentido}] > ").strip().upper()
            if cmd == 'Q':
                break
            elif cmd == 'U':
                self.proto.step_z(+1, 10)
            elif cmd == 'J':
                self.proto.step_z(-1, 10)
            elif cmd == 'V':
                self._toggle_pen_invert()
            elif cmd == 'Z':
                self.z_set_zero()
                print("    Cero de pluma fijado aqui (Z_POS = 0)")
            elif cmd == 'N':
                try:
                    n = int(input("    Profundidad en pasos (10-255): "))
                    if self.set_pen_steps(n):
                        print(f"    PEN_N = {self.proto.pen_steps} (confirmado por el MCU)")
                    else:
                        print("    El MCU no confirmo el cambio.")
                except ValueError:
                    print("    Valor invalido.")
            elif cmd == 'T':
                self.pen_down()
                time.sleep(0.5)
                self.pen_up()
                st = self.proto.get_state()
                if st:
                    print(f"    Tras el ciclo: Z_POS={st['z_pos']} "
                          f"(debe ser 0), PEN_N={st['pen_n']}")
            else:
                print("    Opcion no reconocida.")

    def _toggle_pen_invert(self):
        """cambia el sentido de Z y lo guarda en la config"""
        from cnc_config import save_config

        nuevo = not self.proto.z_invert
        print(f"    Cambiando a sentido {'INVERTIDO' if nuevo else 'normal'}...")
        print("    (se sube la pluma primero, con el sentido antiguo)")

        if not self.set_pen_invert(nuevo):
            if self.proto.z_invert_supported is False:
                print("    ERROR: este firmware no conoce C_ZDIR.")
                print("    Reprograma el AT89S52 con la version actual de")
                print("    8052_v2.asm y vuelve a intentarlo.")
            else:
                print("    ERROR: el MCU no confirmo el cambio.")
            return

        save_config({"pen_invert": self.proto.z_invert})
        print(f"    Sentido del eje Z: "
              f"{'INVERTIDO' if self.proto.z_invert else 'normal'} (guardado)")
        print("    Comprueba con T que la pluma baja al papel y sube al aire.")
        print("    Si el cero quedo mal, ajusta con U/J y pulsa Z.")


# no se usa

def main():
    from cnc_config import load_config, save_config

    print()
    print("  ╔═══════════════════════════════════════════════╗")
    print("  ║   MINI CNC PLOTTER — AT89S52 @ 11.0592MHz     ║")
    print("  ║   v2 — Z absoluto · sin desincronizacion      ║")
    print("  ║   UART 9600 baud                              ║")
    print("  ╚═══════════════════════════════════════════════╝")
    print()
    print("  Modo:  [1] Hardware (puerto serial)   [2] Simulacion")
    mode = input("  > ").strip()

    proto = CNCProtocol(simulate=(mode == '2'))
    if not proto.connect():
        print("  ERROR: No se pudo conectar.")
        sys.exit(1)

    cfg = load_config()
    plotter = CNCPlotter.from_config(proto, cfg)

    if not proto.simulate:
        print("  PING OK — MCU respondio" if proto.ping()
              else "  ADVERTENCIA: PING fallo, verificar conexion")
        st = proto.get_state()
        if st:
            print(f"  Estado MCU: Z_POS={st['z_pos']} PEN_N={st['pen_n']} "
                  f"VEL={st['vel']}ms VEL_Z={st['vel_z']}ms")
            print(f"  Eje Z: sentido "
                  f"{'INVERTIDO' if proto.z_invert else 'normal'}")
            if proto.z_invert_supported is False:
                print("  AVISO: firmware antiguo sin C_ZDIR. La opcion de")
                print("         porta-pluma invertido no estara disponible")
                print("         hasta reprogramar el micro con 8052_v2.asm.")

    def pedir_float(prompt, defecto):
        """input + float sin que un dedazo tire toda la sesion"""
        txt = input(prompt).strip()
        if not txt:
            return defecto
        try:
            return float(txt)
        except ValueError:
            print(f"  Valor invalido, usando {defecto}.")
            return defecto

    draw_ops = {'2', '3', '4', '5', '6', '7'}

    try:
        while True:
            print()
            print("  ─── MENU ─────────────────────────")
            print("  [1] Test de conexion (PING)")
            print("  [2] Cuadrado (10mm)      [3] Triangulo (15mm)")
            print("  [4] Circulo (r=5mm)      [5] Estrella")
            print("  [6] Grilla de calibracion")
            print("  [7] Cargar archivo G-code")
            print("  [8] Calibrar steps/mm    [9] Calibrar backlash")
            print("  [C] Calibrar PLUMA (eje Z)")
            print("  [R] Resincronizar con el MCU")
            print("  [I] Modo interactivo     [S] Estadisticas")
            print("  [G] Guardar config       [0] Salir")

            opcion = input("  > ").strip().upper()

            if opcion == '0':
                break
            elif opcion == '1':
                print(f"  PING: {'OK' if proto.ping() else 'FALLO'}")
            elif opcion == '2':
                plotter.draw_square(pedir_float("  Tamaño mm [10]: ", 10))
            elif opcion == '3':
                plotter.draw_triangle()
            elif opcion == '4':
                plotter.draw_circle(pedir_float("  Radio mm [5]: ", 5))
            elif opcion == '5':
                plotter.draw_star()
            elif opcion == '6':
                plotter.draw_calibration_grid()
            elif opcion == '7':
                fname = input("  Archivo G-code: ").strip()
                if fname:
                    plotter.plot_gcode_file(fname)
            elif opcion == '8':
                plotter.calibrate_steps()
            elif opcion == '9':
                plotter.calibrate_backlash()
            elif opcion == 'C':
                plotter.calibrate_pen()
            elif opcion == 'R':
                ok = proto.sync_firmware()
                plotter.invalidate_pen_cache()
                st = proto.get_state()
                print(f"  Resync: {'OK' if ok else 'FALLO'} — {st}")
            elif opcion == 'I':
                interactive_mode(proto)
                plotter.invalidate_pen_cache()   
                plotter._sync_gc_from_steps()
            elif opcion == 'S':
                proto.print_stats()
            elif opcion == 'G':
                ok = save_config({
                    "steps_per_mm_x": plotter.spm_x,
                    "steps_per_mm_y": plotter.spm_y,
                    "backlash_x": proto.backlash_x,
                    "backlash_y": proto.backlash_y,
                    "pen_steps": proto.pen_steps,
                    "speed_z": proto.z_speed,
                    "pen_invert": proto.z_invert,
                })
                print("  Config guardada." if ok
                      else "  ERROR: no se pudo guardar la config.")
            else:
                print("  Opcion no valida.")

            if opcion in draw_ops:
                plotter.go_home()

    except KeyboardInterrupt:
        print("\n  Interrumpido.")
    finally:
        proto.pen_up()        
        proto.motors_off()     
        proto.disconnect()
        print("  Desconectado.")


def interactive_mode(proto):
    """control manual paso a paso"""
    print("\n  ═══ MODO INTERACTIVO ═══")
    print("  W/S = Y+/Y-      A/D = X+/X-")
    print("  U/J = subir/bajar pluma          P = pen toggle")
    print("  Z   = fijar cero de pluma aqui")
    print("  V   = invertir sentido del eje Z (porta-pluma al reves)")
    print("  +/- = velocidad XY   0 = motores XY off")
    print("  R   = resincronizar con el MCU     Q = salir\n")

    vel = 5
    proto.set_speed(vel)
    n = 50          
    nz = 20         

    while True:
        cmd = input("  > ").strip().upper()
        if not cmd:
            continue
        if cmd == 'Q':
            break
        elif cmd == 'W':
            proto.step_y(+1, n)
        elif cmd == 'S':
            proto.step_y(-1, n)
        elif cmd == 'D':
            proto.step_x(+1, n)
        elif cmd == 'A':
            proto.step_x(-1, n)
        elif cmd == 'U':
            proto.step_z(+1, nz)
        elif cmd == 'J':
            proto.step_z(-1, nz)
        elif cmd == 'Z':
            proto.z_set_zero()
            print("    Cero de pluma fijado aqui")
        elif cmd == 'V':
            from cnc_config import save_config
            nuevo = not proto.z_invert
            if proto.set_z_invert(nuevo):
                save_config({"pen_invert": proto.z_invert})
                print(f"    Sentido del eje Z: "
                      f"{'INVERTIDO' if proto.z_invert else 'normal'} (guardado)")
                print("    Revisa el cero de pluma: pulsa U/J y luego Z.")
            elif proto.z_invert_supported is False:
                print("    ERROR: firmware antiguo sin C_ZDIR. Reprograma")
                print("    el AT89S52 con la version actual de 8052_v2.asm.")
            else:
                print("    ERROR: el MCU no confirmo el cambio.")
        elif cmd == 'P':
            if proto.pen_down_flag:
                proto.pen_up()
                print("    Pen UP")
            else:
                proto.pen_down()
                print("    Pen DOWN")
        elif cmd == '+':
            vel = max(2, vel - 1)
            proto.set_speed(vel)
            print(f"    Velocidad XY: {vel}ms")
        elif cmd == '-':
            vel = min(20, vel + 1)
            proto.set_speed(vel)
            print(f"    Velocidad XY: {vel}ms")
        elif cmd == '0':
            proto.motors_off()
            print("    Motores XY OFF (Z sigue sujeta)")
        elif cmd == 'R':
            proto.sync_firmware()
            print(f"    Resincronizado: {proto.get_state()}")
        else:
            print(f"    '{cmd}' no reconocido")

        print(f"    pos=({proto.pos_x},{proto.pos_y},Z:{proto.pos_z}) "
              f"pen_down={proto.pen_down_flag} "
              f"z_inv={proto.z_invert}")


if __name__ == '__main__':
    main()
