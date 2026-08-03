"""
cnc_plotter.py — Cerebro del Mini CNC Plotter — v2 FINAL
G-code -> Bresenham -> Protocolo -> AT89S52 -> Motores

Cristal: 11.0592 MHz — Baud: 9600

PRECISION (sin cambios respecto a la v1, ya estaba bien):
  1. Bresenham entero puro, cero error de acumulacion float
  2. Conversion mm->pasos SIEMPRE desde la coordenada absoluta
  3. Compensacion de backlash por eje al invertir direccion
  4. Segmentacion adaptativa de arcos por tolerancia de cuerda
  5. Batching: CMD_LINE ejecuta el Bresenham dentro del firmware
  6. Posicion rastreada en enteros, nunca en float

CAMBIOS DE LA v2 (ver DIAGNOSTICO.md):
  [SW-11] z_pen_down_threshold configurable. Antes 'z < 0' obligaba a que
          el G-code usara Z negativos; con Z0/Z5 el dibujo salia en blanco.
  [SW-19] set_speed() sale del bucle de segmentos. Un circulo mandaba
          cientos de tramas SET_SPEED identicas.
  [SW-20] Los arcos ya no reenvian pen_down por segmento.
  [SW-12] Limites coherentes: se leen de la config y se VALIDAN ANTES de
          lanzar el trabajo (avisando), no a mitad de dibujo con una
          excepcion que deja la maquina tirada.
  [SW-1]  pen_down_flag es ahora una propiedad derivada de pos_z. Ya no
          existe la doble maquina de estados que hacia que la pluma
          "a veces si y a veces no".
  NUEVO   abort_check: permite cancelar entre segmentos, no solo entre
          lineas de G-code.
  NUEVO   from_config() y set_pen_steps(): la config llega de verdad al
          firmware en vez de quedarse en el JSON.

CAMBIOS DE ESTA REVISION:
  [SW-30] pen_invert llega al firmware desde from_config().
  [SW-40] G0 con Z en la misma linea: antes bajaba la pluma (_apply_z) y
          rapid_to la volvia a subir acto seguido. La pluma daba un
          golpe contra el papel en cada rapido de ese estilo.
  [SW-41] G2/G3 ya no fuerzan pen_down. Antes cualquier arco dibujaba
          aunque el fichero lo hubiera pedido con la pluma arriba, y la
          Z de esa misma linea se ignoraba.
  [SW-42] M3/M4/M5 se aplican ANTES del movimiento de la misma linea
          (el estado de pluma manda sobre el trazo que lo acompaña) y
          M2/M30 despues (son fin de programa).
  [SW-43] plot_gcode_lines() reinicia abs_mode y feedrate. Al lanzar un
          segundo trabajo se heredaba el G91 del anterior y todo salia
          en relativo.
  [SW-44] gc_x/gc_y se re-derivan de los pasos reales al empezar. Si no,
          el primer arco del trabajo se trazaba desde una posicion
          imaginaria.
  [SW-46] _apply_z() no reenvia pluma arriba/abajo si ya esta en ese
          estado. Un post-procesador que repite Z en cada linea gastaba
          un viaje completo de UART por segmento.
  [SW-47] arc_to_segments() detecta arcos con radios incoherentes
          (I/J que no cuadran con el destino) y cae a linea recta en vez
          de dibujar una espiral silenciosa.
"""

import math
import sys
import time

from cnc_protocol import CNCProtocol
# parse_gcode_line y arc_to_segments vivian aqui; se movieron a gcode_parse
# para que gcode_walk pueda usarlos sin import circular. Se re-exportan porque
# cnc_api.py y los tests los importan desde este modulo desde siempre.
from gcode_parse import arc_to_segments, parse_gcode_line   # noqa: F401
from gcode_transform import IDENTITY, GcodeTransform
from gcode_walk import ArcEvent, DwellEvent, MoveEvent, PenEvent, bounds_of, walk
from soft_limits import LimitExceeded, check_bounds, check_point


# ─── BRESENHAM (entero puro, sin float) ──────────────────────────────

def bresenham_steps(x0, y0, x1, y1):
    """Lista de (dx, dy) con valores -1/0/+1 para una recta en pasos.
    Se conserva para el modo interactivo y para tests; el camino normal
    de dibujo usa CMD_LINE, que hace el Bresenham dentro del firmware."""
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
    """Compatibilidad: la tupla que esperaba el codigo anterior.

    La caja la calcula ahora gcode_walk.bounds_of(), que recorre el fichero
    con el MISMO interprete que lo dibuja. Antes esta funcion era un tercer
    interprete propio que, entre otras cosas, se saltaba el viaje al origen
    de G28 y de M2/M30."""
    from gcode_walk import command_line_count
    b = bounds_of(lines)
    return b.min_x, b.max_x, b.min_y, b.max_y, command_line_count(lines)


# ─── PLOTTER ─────────────────────────────────────────────────────────

class CNCPlotter:

    def __init__(self, proto, steps_per_mm_x=170.67, steps_per_mm_y=170.67,
                 max_x_mm=40.0, max_y_mm=40.0, speed_draw=5, speed_rapid=6,
                 z_pen_down_threshold=0.0, enforce_soft_limits=True):
        """
        proto: instancia de CNCProtocol ya conectada.
        steps_per_mm: 4096 pasos/rev / 24 mm de circunferencia = 170.67
                      -> 0.00586 mm/paso = 5.86 micras de resolucion.
        speed_draw / speed_rapid: ms entre pasos de X e Y.
           OJO: la velocidad del eje Z NO se controla aqui. Vive en el
           firmware (VEL_Z) para que Z nunca herede la velocidad rapida
           de X/Y — ese era el bug SW-2.
        z_pen_down_threshold: en G-code, Z <= umbral significa pluma abajo.
        """
        self.proto = proto
        self.spm_x = steps_per_mm_x
        self.spm_y = steps_per_mm_y
        self.max_x = max_x_mm
        self.max_y = max_y_mm
        self.speed_draw = speed_draw
        self.speed_rapid = speed_rapid
        self.z_pen_down_threshold = z_pen_down_threshold
        self.enforce_soft_limits = enforce_soft_limits

        # estado G-code
        self.abs_mode = True        # G90 = True, G91 = False
        self.gc_x = 0.0
        self.gc_y = 0.0
        self.feedrate = 100.0

        # contadores
        self.lines_processed = 0
        self.total_steps = 0
        self.t_start = 0

        # avisos acumulados durante un trabajo (fuera de area, etc.)
        self.warnings = []

        # callable opcional que devuelve True si hay que abortar.
        # Permite cancelar ENTRE SEGMENTOS, no solo entre lineas.
        self.abort_check = None

        # [SW-46] Ultimo comando de pluma REALMENTE enviado en este
        # trabajo (True=abajo, False=arriba, None=aun ninguno). Sirve
        # para no repetir la trama cuando el G-code trae la misma Z en
        # cada linea. Se pone a None al empezar cada trabajo, asi que
        # la primera pluma del trabajo siempre se envia de verdad y el
        # estado del micro queda reafirmado.
        self._pen_cmd_sent = None

    # ─── CONSTRUCCION DESDE CONFIG ───────────────────────────────

    @classmethod
    def from_config(cls, proto, cfg):
        """Crea el plotter desde la config Y empuja al firmware lo que
        le corresponde al firmware (profundidad y velocidad de pluma).
        [SW-5] antes pen_steps se guardaba en el JSON y no llegaba nunca."""
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
        # [SW-30] el sentido del eje Z tambien es config: hay que
        # empujarlo ANTES del sync, que es quien lo manda al micro.
        proto.z_invert = bool(cfg.get("pen_invert", False))
        proto.sync_firmware()      # manda VEL_Z + PEN_N + Z_DIR y relee
        return plotter

    def _aborted(self):
        return bool(self.abort_check and self.abort_check())

    # ─── CONVERSION mm -> pasos ──────────────────────────────────
    # CLAVE DE PRECISION: convertir siempre la coordenada ABSOLUTA del
    # destino, nunca el delta, para no acumular error de redondeo.
    #   G1 X0.3 -> round(0.3*170.67) = 51
    #   G1 X0.6 -> round(0.6*170.67) = 102  (delta 51)
    #   G1 X0.9 -> round(0.9*170.67) = 154  (delta 52)  <- necesario
    #   G1 X1.2 -> round(1.2*170.67) = 205  (delta 51)
    # Convirtiendo el delta 0.3 mm cuatro veces darian 204: falta un paso.

    def mm_to_steps_x(self, mm):
        return round(mm * self.spm_x)

    def mm_to_steps_y(self, mm):
        return round(mm * self.spm_y)

    # ─── MOVIMIENTO CORE (en pasos) ──────────────────────────────

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
        """Movimiento rapido: batch por eje. X e Y secuenciales."""
        self.proto.set_speed(self.speed_rapid)
        if dx != 0:
            self.proto.step_x(1 if dx > 0 else -1, abs(dx))
        if dy != 0:
            self.proto.step_y(1 if dy > 0 else -1, abs(dy))
        self.total_steps += abs(dx) + abs(dy)

    def _draw_line(self, tx, ty, dx, dy):
        """Linea dibujada. Las diagonales van con CMD_LINE: el firmware
        ejecuta Bresenham con Timer0, sin el jitter de 5-15 ms por paso
        que metia el USB y que ponia a los motores en resonancia."""
        self.proto.set_speed(self.speed_draw)

        if dy == 0:                       # horizontal pura
            self.proto.step_x(1 if dx > 0 else -1, abs(dx))
            self.total_steps += abs(dx)
            return
        if dx == 0:                       # vertical pura
            self.proto.step_y(1 if dy > 0 else -1, abs(dy))
            self.total_steps += abs(dy)
            return

        dir_x = 1 if dx > 0 else -1
        dir_y = 1 if dy > 0 else -1
        self.proto.compensate_backlash_xy(dir_x, dir_y)

        abs_dx, abs_dy = abs(dx), abs(dy)
        max_steps = max(abs_dx, abs_dy)

        if max_steps <= 255:
            # los pasos solo se contabilizan si el micro los confirmo;
            # si no, ni pos_* ni total_steps deben avanzar
            if self.proto.send_line_segment(abs_dx, abs_dy, dir_x, dir_y):
                self.proto.pos_x = tx
                self.proto.pos_y = ty
                self.proto._maybe_save_position()
                self.total_steps += max_steps
        else:
            self._draw_line_chunked(abs_dx, abs_dy, dir_x, dir_y)

    def _draw_line_chunked(self, abs_dx, abs_dy, dir_x, dir_y):
        """Divide una linea larga en segmentos de 255 pasos como maximo.
        El acumulador entero garantiza que la suma de los segmentos da
        exactamente abs_dx pasos en X y abs_dy en Y, sin drift.

        No recibe el destino a proposito: pos_x/pos_y se acumulan segmento
        a segmento SOLO con lo que el micro confirmo. Si se cortase a
        mitad (abort o fallo de comunicacion), forzar la posicion final
        haria creer que el carro llego donde no llego."""
        major = max(abs_dx, abs_dy)
        x_is_major = abs_dx >= abs_dy
        minor_total = min(abs_dx, abs_dy)

        n_segs = (major + 254) // 255
        prev_minor_acc = 0

        for seg in range(n_segs):
            if self._aborted():           # cancelar entre segmentos
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
                break                     # fallo de comunicacion: parar
            self.proto.pos_x += dir_x * seg_dx
            self.proto.pos_y += dir_y * seg_dy
            self.proto._maybe_save_position()
            self.total_steps += max(seg_dx, seg_dy)

    # ─── API DE ALTO NIVEL (en mm) ───────────────────────────────

    def _check_area(self, x_mm, y_mm):
        """Ultima red antes de mover. Lanza LimitExceeded.

        Antes solo acumulaba un aviso de texto y dejaba pasar el movimiento
        [SW-12]. La razon era buena — reventar a mitad de un dibujo deja la
        maquina a medias — pero la consecuencia era peor: sin finales de
        carrera, seguir moviendo contra el tope pierde pasos y descalibra la
        maquina entera. Un trabajo cortado se rehace; una calibracion perdida
        hay que medirla otra vez con regla.

        Lo que hace que esto no corte trabajos legitimos es que el pre-vuelo
        (soft_limits.check_bounds sobre la caja completa, antes de empezar)
        ya rechazo todo lo que no cabe. Si se llega aqui es porque el origen
        se movio a mano despues del pre-vuelo, y ahi parar es lo correcto."""
        if not self.enforce_soft_limits:
            return
        violation = check_point(x_mm, y_mm, self.max_x, self.max_y)
        if violation is None:
            return
        if violation.message() not in self.warnings:
            self.warnings.append(violation.message())
        raise LimitExceeded(violation)

    def line_to(self, x_mm, y_mm):
        """Dibujar una linea hasta la posicion absoluta (mm)."""
        self._check_area(x_mm, y_mm)
        self.move_to_steps(self.mm_to_steps_x(x_mm),
                           self.mm_to_steps_y(y_mm), draw=True)
        self.gc_x, self.gc_y = x_mm, y_mm

    def rapid_to(self, x_mm, y_mm):
        """Movimiento rapido hasta (mm), con la pluma arriba."""
        self._check_area(x_mm, y_mm)
        self._set_pen(False)
        self.move_to_steps(self.mm_to_steps_x(x_mm),
                           self.mm_to_steps_y(y_mm), draw=False)
        self.gc_x, self.gc_y = x_mm, y_mm

    @property
    def chord_tol(self):
        """Error de cuerda maximo al descomponer arcos: un paso de motor.
        Afinar mas no se puede imprimir, y multiplica los segmentos."""
        return min(1.0 / self.spm_x, 1.0 / self.spm_y)

    def arc_to(self, x_mm, y_mm, i_mm, j_mm, clockwise=True, draw=True):
        """Arco G2/G3 desde la posicion actual, descomponiendolo aqui mismo.
        Lo usan los patrones de prueba (draw_circle), que piden arcos
        directamente sin pasar por un fichero de G-code."""
        segments = arc_to_segments(self.gc_x, self.gc_y, x_mm, y_mm,
                                   i_mm, j_mm, clockwise, self.chord_tol)
        self.trace_points(segments, draw)

    def trace_points(self, points, draw=True):
        """Recorre una polilinea ya calculada.
        [SW-19] La velocidad se fija UNA vez, no por segmento — un circulo
        mandaba cientos de tramas SET_SPEED identicas.
        [SW-41] draw=False la recorre con la pluma arriba, para respetar los
        ficheros que posicionan siguiendo una curva."""
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
        """Olvida el estado de pluma cacheado. Hay que llamarlo si algo
        externo mueve el eje Z por su cuenta (jog manual, resync,
        z_set_zero), para que el proximo pen_up/pen_down se envie de
        verdad en vez de darse por hecho."""
        self._pen_cmd_sent = None

    def set_pen_steps(self, steps):
        """Profundidad de pluma. Va de verdad al firmware (CMD_SET_PEN_N)."""
        ok = self.proto.set_pen_steps(steps)
        # Cambiar PEN_N mueve el destino de "pluma abajo": lo cacheado
        # deja de valer aunque el flag siga diciendo lo mismo.
        self.invalidate_pen_cache()
        return ok

    def z_set_zero(self):
        """Define la altura actual de la pluma como el cero de 'arriba'."""
        ok = self.proto.z_set_zero()
        self.invalidate_pen_cache()
        return ok

    def set_pen_invert(self, invert):
        """[SW-30] Sentido fisico del eje Z (porta-pluma montado al reves).
        Ver CNCProtocol.set_z_invert: la inversion la hace el firmware."""
        ok = self.proto.set_z_invert(invert)
        self.invalidate_pen_cache()
        return ok

    def go_home(self):
        self.rapid_to(0, 0)

    # ─── EJECUCION G-CODE ────────────────────────────────────────

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
        """Deja el interprete de G-code en un estado limpio y coherente
        con la maquina. Lo llaman plot_gcode_lines() y el hilo de job de
        la API: sin esto, el segundo trabajo de una sesion arrastra el
        estado del primero."""
        self.t_start = time.perf_counter()
        self.lines_processed = 0
        self.total_steps = 0
        self.warnings = []

        # [SW-43] Estado modal del interprete. Si el trabajo anterior
        # acabo en G91, el siguiente empezaba en relativo y se dibujaba
        # completamente descolocado.
        self.abs_mode = True
        self.feedrate = 100.0

        # [SW-46] La primera pluma del trabajo se envia siempre.
        self.invalidate_pen_cache()

        # [SW-44] gc_x/gc_y son la posicion en mm segun el interprete;
        # proto.pos_x/y es donde esta la maquina de verdad. Si vienen de
        # un jog manual no coinciden, y arc_to() usa gc_* como centro de
        # referencia: el primer arco saldria desplazado.
        self._sync_gc_from_steps()

    def _sync_gc_from_steps(self):
        self.gc_x = self.proto.pos_x / self.spm_x if self.spm_x else 0.0
        self.gc_y = self.proto.pos_y / self.spm_y if self.spm_y else 0.0

    def events(self, lines, transform: GcodeTransform = IDENTITY):
        """El recorrido de gcode_walk con los parametros de ESTA maquina.

        Un solo sitio donde se decide el umbral de pluma, la tolerancia de
        cuerda y el estado inicial de la pluma, para que el preview y el
        pre-vuelo puedan pedir exactamente el mismo recorrido."""
        return walk(lines,
                    z_pen_down_threshold=self.z_pen_down_threshold,
                    chord_tol=self.chord_tol,
                    transform=transform,
                    initial_pen_down=self.proto.pen_down_flag)

    def plot_gcode_lines(self, lines, transform: GcodeTransform = IDENTITY):
        """Ejecuta una lista de lineas de G-code."""
        total = len(lines)
        self.begin_job()

        # Validar el area ANTES de mover nada. Ahora es un bloqueo, no un
        # aviso: sin finales de carrera, dejar que el carro llegue al tope
        # pierde pasos y descalibra la maquina.
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
        """Traduce UN evento de gcode_walk a movimiento real.

        Toda la interpretacion del G-code (modales, orden de pluma, arcos,
        relativos) ya la hizo el walker; aqui solo queda mover. Esa es la
        razon de ser del walker: que el preview y el pre-vuelo consuman esta
        misma lista de eventos y no puedan ver otra geometria."""
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
        """Punto unico por el que pasan TODOS los cambios de pluma.

        [SW-46] Evita reenviar la trama si la pluma ya esta donde se
        pide. pen_up/pen_down son idempotentes en el firmware, asi que
        repetirlos no rompe nada — pero cuesta un viaje completo de UART
        (~5 ms mas el movimiento de Z), y hay post-procesadores que
        ponen la misma Z en cada una de las miles de lineas del fichero.

        _pen_cmd_sent vale None al empezar cada trabajo, de modo que la
        primera pluma del trabajo SIEMPRE se envia y reafirma el estado
        real del micro; a partir de ahi pos_z solo cambia con ACK, asi
        que el cache no puede quedarse mintiendo sin que se entere
        comm_lost."""
        if self._pen_cmd_sent is down:
            return True
        ok = self.proto.pen_down() if down else self.proto.pen_up()
        # Solo se cachea lo que el micro confirmo. Si fallo, se deja en
        # None para que el proximo intento vuelva a mandarlo.
        self._pen_cmd_sent = down if ok else None
        return ok

    # _apply_z() y _resolve_xy() vivian aqui. Ahora los hace gcode_walk, que
    # es quien interpreta el fichero; el plotter solo mueve.

    # ─── PATRONES DE PRUEBA ──────────────────────────────────────

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

    # ─── CALIBRACION (CLI) ───────────────────────────────────────

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
        """Calibracion de pluma con el nuevo Z absoluto.
        Es el flujo que arregla el problema del eje Z: se fija un cero
        fisico y a partir de ahi pen_up/pen_down son ABSOLUTOS.

        [SW-30] Si el porta-pluma quedo montado al reves (subir baja y
        bajar sube), lo PRIMERO es la opcion V. Todo lo demas depende de
        que el sentido sea el correcto."""
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
        """Cambia el sentido del eje Z y lo deja guardado en la config."""
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


# ─── CLI ─────────────────────────────────────────────────────────────

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
        """input() + float() sin que un dedazo tire toda la sesion."""
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
                plotter.invalidate_pen_cache()   # el jog manual movio Z
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
        proto.pen_up()          # dejar la pluma arriba, no clavada
        proto.motors_off()      # apaga X e Y; Z sigue sujeta (SW-9)
        proto.disconnect()
        print("  Desconectado.")


def interactive_mode(proto):
    """Control manual paso a paso."""
    print("\n  ═══ MODO INTERACTIVO ═══")
    print("  W/S = Y+/Y-      A/D = X+/X-")
    print("  U/J = subir/bajar pluma          P = pen toggle")
    print("  Z   = fijar cero de pluma aqui")
    print("  V   = invertir sentido del eje Z (porta-pluma al reves)")
    print("  +/- = velocidad XY   0 = motores XY off")
    print("  R   = resincronizar con el MCU     Q = salir\n")

    vel = 5
    proto.set_speed(vel)
    n = 50          # pasos por pulsacion en X/Y
    nz = 20         # pasos por pulsacion en Z (mas fino)

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
