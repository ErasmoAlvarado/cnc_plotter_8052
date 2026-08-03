"""
cnc_api.py — API FastAPI del Mini CNC Plotter — v2 FINAL

CAMBIOS RESPECTO A LA v1 (ver DIAGNOSTICO.md):

 [SW-3a] El puerto serie ya esta protegido por un RLock dentro de
         CNCProtocol, asi que los hilos de job y los endpoints HTTP no
         pueden intercalar bytes de tramas distintas.
 [SW-3b] TODOS los endpoints que mueven algo comprueban _require_idle().
         Antes /api/pen, /api/home, /api/motors-off y /api/ping no lo
         hacian: pulsar el boton de pluma en mitad de un dibujo inyectaba
         una trama en el stream y desincronizaba el firmware.
 [SW-3c] Los endpoints bloqueantes son 'def', no 'async def'. FastAPI los
         ejecuta en un threadpool. Antes congelaban el event loop entero
         (WebSocket incluido) durante cada movimiento.
 [SW-1]  pen_down_flag es una propiedad derivada; ya no se le asigna.
         La recuperacion de posicion pregunta al MCU en vez de fiarse
         de un fichero de hace una hora.
 [SW-5]  /api/pen-config envia de verdad la profundidad al firmware.
 [SW-6]  El jog de Z usa steps_per_mm_z y tiene limites propios.
 [SW-16] run_gcode_thread comprueba proto ademas de plotter.
 [SW-17] /api/disconnect aborta el job y espera al hilo.
 [SW-18] La calibracion de backlash no suma pasos que no se ejecutaron.
 [SW-22] CORS restringido a localhost.
 NUEVO   /api/z-set-zero, /api/z-off, /api/resync y aborto por segmento.

CAMBIOS DE ESTA REVISION:

 [SW-30] /api/pen-holder: sentido fisico del eje Z segun como este
         montado el porta-pluma. Va al firmware (C_ZDIR), no se emula.

 [SW-48] job_state["active"] se marca en el ENDPOINT, no dentro del
         hilo. Antes, dos POST /api/run seguidos pasaban los dos por
         _require_idle() antes de que el primer hilo llegase a marcar
         nada, y acababan dos hilos mandando tramas al mismo puerto.

 [SW-49] abort_event se limpia al conectar y solo cuenta durante un
         job. Antes, un /api/stop (o un /api/disconnect) dejaba el flag
         puesto para siempre: la siguiente calibracion o patron se
         cancelaba sola, en silencio, sin mover un paso.

 [SW-50] /api/jog normaliza la direccion a ±1 y usa |distancia|. Con
         direction=2 la posicion cacheada avanzaba el doble que el eje.

 [SW-51] Validacion de rangos en TODOS los modelos de entrada. Un
         steps_per_mm=0 en /api/settings dejaba la API dando 500 por
         division por cero en cada peticion posterior.

 [SW-52] Los hilos de job capturan proto/plotter en locales. Un
         /api/disconnect a mitad los ponia a None y el hilo moria con
         AttributeError dentro del finally, sin avisar por WebSocket.

 [SW-53] El preview de /api/upload-gcode esta acotado. Un fichero con
         miles de arcos generaba cientos de miles de puntos en un solo
         JSON y tumbaba al navegador.
"""

import asyncio
import math
import os
import threading
import time
from contextlib import asynccontextmanager
from typing import Optional, List

import serial.tools.list_ports
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from cnc_protocol import CNCProtocol, CMD_X_POS, CMD_X_NEG, CMD_Y_POS, CMD_Y_NEG
from cnc_plotter import CNCPlotter
from cnc_config import load_config, save_config
from gcode_transform import IDENTITY, Bounds, GcodeTransform, build as build_transform
from gcode_walk import ArcEvent, MoveEvent, bounds_of, command_line_count, walk
from soft_limits import LimitExceeded, TOLERANCE_MM, check_bounds, remaining_mm


# ─── LIMITES ─────────────────────────────────────────────────────────

MAX_GCODE_LINES = 200_000        # ~10 MB de G-code
MAX_PREVIEW_PATHS = 5_000        # trazos que se mandan al frontend
MAX_PREVIEW_ARC_POINTS = 64      # puntos por arco en el preview


# ─── ESTADO GLOBAL ───────────────────────────────────────────────────

proto: Optional[CNCProtocol] = None
plotter: Optional[CNCPlotter] = None

job_state = {
    "active": False,
    "progress": 0.0,
    "lines_processed": 0,
    "total_lines": 0,
    "total_steps": 0,
    "elapsed": 0.0,
}

loaded_gcode: List[str] = []

# Transformacion aplicada al G-code cargado (espejo en Y / ajuste al area).
# Vive junto a loaded_gcode y no dentro del fichero: el fichero no se toca
# nunca, asi que el usuario puede quitar el espejo sin volver a subirlo.
gcode_transform: GcodeTransform = IDENTITY
gcode_bounds_raw: Bounds = Bounds()      # caja SIN transformar, la del fichero

abort_event = threading.Event()
job_thread: Optional[threading.Thread] = None
active_websockets: List[WebSocket] = []
loop: Optional[asyncio.AbstractEventLoop] = None

# [SW-48] Serializa la comprobacion "esta libre?" con el "pues lo cojo".
# Sin esto las dos peticiones ganan la carrera y arrancan dos hilos.
job_lock = threading.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global loop
    loop = asyncio.get_running_loop()
    yield
    # apagado limpio: abortar job, ESPERARLO y dejar la pluma arriba
    abort_event.set()
    if job_thread and job_thread.is_alive():
        job_thread.join(timeout=10.0)
    if proto:
        try:
            proto.pen_up()
            proto.motors_off()
            proto.disconnect()
        except Exception:
            pass


app = FastAPI(title="Mini CNC Plotter API", version="2.0", lifespan=lifespan)

# [SW-22] '*' + credenciales en algo que mueve motores es mala idea:
# cualquier web abierta en el navegador podria comandar la maquina.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000", "http://127.0.0.1:8000",
        "http://localhost:5173", "http://127.0.0.1:5173",   # dev del frontend
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── HELPERS ─────────────────────────────────────────────────────────

def _require_conn():
    if not proto or not plotter:
        raise HTTPException(status_code=400, detail="No conectado")


def _require_idle():
    """[SW-3b] Nadie toca el puerto mientras hay un trabajo en curso."""
    if job_state["active"]:
        raise HTTPException(status_code=409, detail="Hay un job en curso")


def _claim_job():
    """[SW-48] Reserva el puerto para un trabajo nuevo, de forma atomica.

    _require_idle() sola no basta: entre "no hay job" y el start() del
    hilo hay una ventana en la que una segunda peticion tambien ve el
    puerto libre. Y como job_state["active"] lo marcaba el propio hilo,
    esa ventana duraba hasta el primer planificado del hilo — de sobra
    para que dos jobs se pisaran las tramas en el mismo puerto serie."""
    with job_lock:
        if job_state["active"]:
            raise HTTPException(status_code=409, detail="Hay un job en curso")
        abort_event.clear()              # [SW-49] arrancar sin abort viejo
        job_state.update({"active": True, "progress": 0.0,
                          "lines_processed": 0, "total_lines": 0,
                          "total_steps": 0, "elapsed": 0.0})


def _release_job():
    with job_lock:
        job_state["active"] = False


def _job_aborted() -> bool:
    """[SW-49] El abort SOLO cuenta mientras hay un trabajo en curso.

    plotter.abort_check apunta aqui. Antes apuntaba directo a
    abort_event.is_set, y como /api/stop y /api/disconnect dejan el flag
    puesto, cualquier movimiento largo posterior (calibracion, home,
    patron) se cancelaba solo entre segmentos sin decir nada."""
    return job_state["active"] and abort_event.is_set()


async def broadcast_ws(message: dict):
    for ws in list(active_websockets):
        try:
            await ws.send_json(message)
        except Exception:
            try:
                active_websockets.remove(ws)
            except ValueError:
                pass


def send_ws_message(msg: dict):
    if loop and not loop.is_closed():
        try:
            asyncio.run_coroutine_threadsafe(broadcast_ws(msg), loop)
        except Exception:
            pass


def _status_dict() -> dict:
    """[SW-3c] Version SINCRONA del estado. Antes status() era async y se
    llamaba con 'await' desde endpoints bloqueantes, lo que obligaba a
    que esos endpoints fueran async y congelaran el event loop."""
    cfg = load_config()

    if not proto or not plotter:
        return {
            "connected": False,
            "simulating": False,
            "port": None,
            "position": {"x_steps": 0, "y_steps": 0, "z_steps": 0,
                         "x_mm": 0.0, "y_mm": 0.0},
            "pen_down": False,
            "speed_draw": cfg["speed_draw"],
            "speed_rapid": cfg["speed_rapid"],
            "speed_z": cfg["speed_z"],
            "abs_mode": True,
            "steps_per_mm": {"x": cfg["steps_per_mm_x"],
                             "y": cfg["steps_per_mm_y"],
                             "z": cfg["steps_per_mm_z"]},
            "backlash": {"x": cfg["backlash_x"], "y": cfg["backlash_y"]},
            "stats": {"sent": 0, "ack": 0, "nack": 0,
                      "timeout": 0, "retries": 0},
            "comm_lost": False,
            "job": None,
            "pen_steps": cfg["pen_steps"],
            "max_x_mm": cfg["max_x_mm"],
            "max_y_mm": cfg["max_y_mm"],
            "pen_invert": cfg["pen_invert"],
            "pen_invert_supported": None,
            "z_pen_down_threshold": cfg["z_pen_down_threshold"],
            "enforce_soft_limits": cfg["enforce_soft_limits"],
            "invert_x": cfg["invert_x"],
            "invert_y": cfg["invert_y"],
        }

    return {
        "connected": True,
        "simulating": proto.simulate,
        "port": proto.port,
        "position": {
            "x_steps": proto.pos_x,
            "y_steps": proto.pos_y,
            "z_steps": proto.pos_z,
            "x_mm": plotter.gc_x,
            "y_mm": plotter.gc_y,
        },
        "pen_down": proto.pen_down_flag,
        "speed_draw": plotter.speed_draw,
        "speed_rapid": plotter.speed_rapid,
        "speed_z": proto.z_speed,
        "abs_mode": plotter.abs_mode,
        "steps_per_mm": {"x": plotter.spm_x, "y": plotter.spm_y,
                         "z": cfg["steps_per_mm_z"]},
        "backlash": {"x": proto.backlash_x, "y": proto.backlash_y},
        "stats": proto.stats,
        "comm_lost": proto.comm_lost,
        "job": job_state if job_state["active"] else None,
        "pen_steps": proto.pen_steps,
        "max_x_mm": plotter.max_x,
        "max_y_mm": plotter.max_y,
        "warnings": plotter.warnings,
        # [SW-30] estado del sentido del eje Z. 'supported' en False
        # significa firmware antiguo sin C_ZDIR: hay que reprogramarlo.
        "pen_invert": proto.z_invert,
        "pen_invert_supported": proto.z_invert_supported,
        "z_pen_down_threshold": plotter.z_pen_down_threshold,
        "enforce_soft_limits": plotter.enforce_soft_limits,
        # Presentacion, no cinematica: el backend solo los guarda y los
        # reporta; quien los aplica es frontend/src/coords.js.
        "invert_x": cfg["invert_x"],
        "invert_y": cfg["invert_y"],
    }


# ─── CONEXION ────────────────────────────────────────────────────────

class ConnectReq(BaseModel):
    port: Optional[str] = None
    simulate: bool = False


@app.post("/api/connect")
def connect(req: ConnectReq):
    global proto, plotter
    _require_idle()
    if proto and (proto.simulate or (proto.ser and proto.ser.is_open)):
        return {"ok": True, "port": proto.port, "message": "Ya conectado"}

    # [SW-49] Una desconexion o un /api/stop anterior dejaron el flag
    # puesto. Si no se limpia aqui, el primer movimiento largo de esta
    # sesion se aborta solo antes de mover un paso.
    abort_event.clear()

    nuevo = CNCProtocol(port=req.port, simulate=req.simulate)
    try:
        conectado = nuevo.connect()
    except Exception as e:
        raise HTTPException(status_code=400,
                            detail=f"No se pudo conectar: {e}")
    if not conectado:
        raise HTTPException(
            status_code=400,
            detail="No se pudo conectar: puerto no disponible o sin respuesta")

    proto = nuevo
    # [SW-5] from_config empuja VEL_Z, PEN_N y Z_DIR al firmware y relee.
    cfg = load_config()
    plotter = CNCPlotter.from_config(proto, cfg)
    plotter.abort_check = _job_aborted

    mcu = proto.get_state()

    # [SW-30] Avisar si la config pide pluma invertida y el micro no
    # sabe hacerlo: es un fallo silencioso muy caro (dibuja al aire y
    # arrastra la punta por el papel en los rapidos).
    aviso = None
    if cfg.get("pen_invert") and proto.z_invert_supported is False:
        aviso = ("La config pide el eje Z invertido pero este firmware no "
                 "soporta C_ZDIR. Reprograma el AT89S52 con la version "
                 "actual de 8052_v2.asm.")

    # Posicion anterior guardada en disco (solo X/Y: la Z real la sabe el MCU)
    last_pos = CNCProtocol.load_last_position()
    recovery = None
    if last_pos:
        recovery = {
            "pos_x": last_pos["pos_x"],
            "pos_y": last_pos["pos_y"],
            "pos_z": last_pos["pos_z"],
            "pen_down": last_pos["pen_down"],
            "age_seconds": last_pos["age_seconds"],
            "age_human": f"{int(last_pos['age_seconds'] // 60)} minutos",
        }

    return {
        "ok": True,
        "port": proto.port,
        "message": "Conectado",
        "mcu_state": mcu,
        "recovery": recovery,
        "warning": aviso,
    }


@app.post("/api/disconnect")
def disconnect():
    """[SW-17] Abortar el job y ESPERAR al hilo antes de matar 'proto'.
    Antes se ponia proto=None con el hilo vivo y reventaba con AttributeError."""
    global proto, plotter, job_thread
    abort_event.set()
    if job_thread and job_thread.is_alive():
        job_thread.join(timeout=10.0)
    if proto:
        try:
            proto.pen_up()
            proto._save_position()
            proto.motors_off()
        except Exception:
            pass
        proto.disconnect()
        proto = None
        plotter = None
    _release_job()
    # [SW-49] no dejar el abort armado para la proxima conexion
    abort_event.clear()
    return {"ok": True}


@app.get("/api/status")
def status():
    return _status_dict()


@app.post("/api/ping")
def ping():
    _require_conn()
    _require_idle()
    return {"ok": proto.ping()}


@app.post("/api/resync")
def resync():
    """Boton de panico. Relee el estado real del MCU (Z_POS, PEN_N, VEL,
    VEL_Z) y realinea el PC. Sustituye al 'reiniciar la app' de antes."""
    _require_conn()
    _require_idle()
    ok = proto.sync_firmware()
    # el resync relee Z_POS del micro: lo que creyeramos saber de la
    # pluma deja de valer y hay que volver a mandarlo la proxima vez
    plotter.invalidate_pen_cache()
    return {"ok": ok, "state": proto.get_state(), "status": _status_dict()}


@app.get("/api/serial-ports")
def get_serial_ports():
    return [{"port": p.device, "description": p.description}
            for p in serial.tools.list_ports.comports()]


@app.get("/api/config")
def get_config():
    return load_config()


# ─── G-CODE ──────────────────────────────────────────────────────────

def _preview_chord_tol(cfg) -> float:
    """La MISMA tolerancia de cuerda que usara el plotter al dibujar
    (CNCPlotter.chord_tol). Si el preview segmentase los arcos con otra
    tolerancia, la geometria previsualizada no seria exactamente la que se
    ejecuta — que es justo lo que este refactor viene a eliminar."""
    spm_x = max(1e-6, cfg["steps_per_mm_x"])
    spm_y = max(1e-6, cfg["steps_per_mm_y"])
    return min(1.0 / spm_x, 1.0 / spm_y)


def _gcode_payload(filename=None) -> dict:
    """Respuesta comun de /api/upload-gcode y /api/gcode-transform.

    Recorre el G-code cargado UNA vez con gcode_walk —el mismo interprete que
    lo va a dibujar— y saca de esa pasada el preview y la caja delimitadora.
    Antes eran dos recorridos distintos (el bucle de preview y gcode_bounds),
    cada uno con sus propias omisiones."""
    cfg = load_config()
    max_x, max_y = cfg["max_x_mm"], cfg["max_y_mm"]

    preview_paths = []
    preview_truncated = False
    min_x = min_y = float('inf')
    max_bx = max_by = float('-inf')

    # El indice de linea viaja con cada trazo del preview para que el frontend
    # pueda pintar en vivo QUE trazo se esta dibujando: el mensaje "progress"
    # del WebSocket manda 'line' contando sobre ESTA MISMA lista, asi que los
    # dos indices son directamente comparables.
    prev = gcode_transform.apply(0.0, 0.0)
    for ev in walk_loaded(cfg):
        if isinstance(ev, MoveEvent):
            puntos = [prev, (ev.x, ev.y)]
            muestra = puntos
            prev = (ev.x, ev.y)
        elif isinstance(ev, ArcEvent):
            pts = list(ev.points)
            # [SW-53] El preview es una ayuda visual, no el trabajo real: se
            # acota. Sin esto, un fichero de arcos generaba hasta 2000 puntos
            # POR arco y el JSON de respuesta llegaba a cientos de MB.
            paso = max(1, len(pts) // MAX_PREVIEW_ARC_POINTS)
            muestra = [prev] + pts[::paso]
            if muestra[-1] != pts[-1]:
                muestra.append(pts[-1])
            puntos = pts
            prev = pts[-1]
        else:
            continue

        for px, py in puntos:                 # caja sobre la geometria REAL,
            min_x = min(min_x, px)            # no sobre la muestra del preview
            max_bx = max(max_bx, px)
            min_y = min(min_y, py)
            max_by = max(max_by, py)

        if len(preview_paths) < MAX_PREVIEW_PATHS:
            preview_paths.append({
                "type": "draw" if ev.draw else "rapid",
                "line": ev.line,
                "points": [[p[0], p[1]] for p in muestra]})
        else:
            preview_truncated = True

    b = (Bounds(min_x, max_bx, min_y, max_by)
         if min_x != float('inf') else Bounds())
    violation = check_bounds(b, max_x, max_y)

    payload = {
        "ok": True,
        "total_lines": len(loaded_gcode),
        "command_lines": command_line_count(loaded_gcode),
        "bounds": b.as_dict(),
        "fits_in_area": violation is None,
        "limit_violation": violation.as_dict() if violation else None,
        "work_area": {"max_x_mm": max_x, "max_y_mm": max_y},
        "transform": gcode_transform.as_dict(),
        "preview_paths": preview_paths,
        "preview_truncated": preview_truncated,
    }
    if filename is not None:
        payload["filename"] = filename
    return payload


def walk_loaded(cfg):
    """Recorrido del G-code cargado con la transformacion vigente.

    initial_pen_down=False (el valor por defecto del walker) porque el
    preview describe el fichero, no el estado actual de la maquina."""
    return walk(loaded_gcode,
                z_pen_down_threshold=cfg["z_pen_down_threshold"],
                chord_tol=_preview_chord_tol(cfg),
                transform=gcode_transform)


@app.post("/api/upload-gcode")
async def upload_gcode(file: UploadFile = File(...)):
    global loaded_gcode, gcode_transform, gcode_bounds_raw
    # cambiar el fichero mientras se esta dibujando el anterior confunde
    # a cualquiera que mire la UI; el job usa su propia referencia, pero
    # el preview y los limites que se muestran serian los del otro
    _require_idle()

    content = await file.read()
    lineas = content.decode('utf-8', errors='replace').splitlines()
    if len(lineas) > MAX_GCODE_LINES:
        raise HTTPException(
            status_code=413,
            detail=f"G-code demasiado grande: {len(lineas)} lineas "
                   f"(maximo {MAX_GCODE_LINES})")

    loaded_gcode = lineas
    gcode_transform = IDENTITY          # fichero nuevo, sin espejo ni ajuste

    cfg = load_config()
    gcode_bounds_raw = bounds_of(lineas, cfg["z_pen_down_threshold"],
                                 _preview_chord_tol(cfg))
    return _gcode_payload(filename=file.filename)


class GcodeTransformReq(BaseModel):
    # Espejo en Y: el G-code estandar asume Y hacia arriba y esta maquina
    # tiene el origen arriba a la izquierda, asi que un fichero de CAM sale
    # del reves. Es por fichero y no global porque depende de con que se
    # exporto, no de la maquina.
    flip_y: bool = False
    # "Ajustar al area": escalar y centrar para que quepa.
    fit: bool = False


@app.post("/api/gcode-transform")
def set_gcode_transform(req: GcodeTransformReq):
    """Aplica espejo/ajuste al G-code YA cargado y devuelve el preview nuevo.

    No se vuelve a subir el fichero ni se reescribe: la transformacion es un
    dato aparte que consume el mismo walker. Por eso quitar el espejo es
    exactamente igual de barato que ponerlo, y el preview que se ve es el que
    se va a dibujar."""
    global gcode_transform
    _require_idle()
    if not loaded_gcode:
        raise HTTPException(status_code=400, detail="No hay G-code cargado")

    cfg = load_config()
    # Siempre desde la caja ORIGINAL: encadenar sobre la transformacion
    # anterior haria que pulsar "Ajustar al area" dos veces encogiera el
    # dibujo dos veces.
    gcode_transform = build_transform(gcode_bounds_raw,
                                      cfg["max_x_mm"], cfg["max_y_mm"],
                                      flip_y=req.flip_y, fit=req.fit)
    return _gcode_payload()


def run_gcode_thread(lines, abort_evt, pl: CNCPlotter, pr: CNCProtocol,
                     transform: GcodeTransform = IDENTITY):
    """[SW-52] pl/pr llegan por parametro, NO se leen de las globales.

    Un /api/disconnect a mitad de trabajo pone plotter y proto a None;
    si este hilo los leyera de las globales, moriria con AttributeError
    justo dentro del finally y el WebSocket nunca se enteraria de que el
    trabajo termino. Con referencias locales el hilo siempre acaba
    ordenadamente, aunque la sesion ya se haya cerrado por debajo."""
    total = len(lines)
    job_state.update({"total_lines": total, "lines_processed": 0,
                      "progress": 0.0, "total_steps": 0, "elapsed": 0.0})
    pl.begin_job()                      # [SW-43][SW-44][SW-46]
    t_start = time.perf_counter()
    last_ws_update = 0.0

    try:
        # El MISMO recorrido que genero el preview y que valido los limites.
        for ev in pl.events(lines, transform):
            if abort_evt.is_set():
                break
            if pr.comm_lost:
                send_ws_message({"type": "error",
                                 "message": "Comunicacion perdida con el MCU"})
                break

            pl.exec_event(ev)

            # 'line' es el indice de linea del fichero, el mismo con el que
            # /api/upload-gcode etiqueta cada trazo del preview: es lo que
            # permite al frontend pintar exactamente lo ya dibujado.
            job_state["lines_processed"] = ev.line + 1
            job_state["total_steps"] = pl.total_steps

            now = time.perf_counter()
            job_state["elapsed"] = now - t_start
            job_state["progress"] = (ev.line + 1) / total

            if now - last_ws_update > 0.2:
                last_ws_update = now
                send_ws_message({
                    "type": "progress",
                    "line": ev.line + 1,
                    "total": total,
                    "percent": job_state["progress"] * 100,
                    "pos_x_mm": pl.gc_x,
                    "pos_y_mm": pl.gc_y,
                    "pos_z_steps": pr.pos_z,
                    "steps": pl.total_steps,
                    "elapsed": job_state["elapsed"],
                })
    except LimitExceeded as e:
        # No deberia llegar aqui: /api/run ya valido la caja completa. Pasa
        # si el origen se movio despues de esa validacion.
        send_ws_message({"type": "error",
                         "message": f"Fuera del area util. {e}"})
    except Exception as e:
        send_ws_message({"type": "error",
                         "message": f"Error de ejecucion: {e}"})
    finally:
        # dejar SIEMPRE la pluma arriba, aunque se haya abortado
        try:
            pr.pen_up()
            pl.invalidate_pen_cache()
            pr._save_position()
        except Exception:
            pass
        _release_job()
        if abort_evt.is_set():
            send_ws_message({"type": "error", "message": "Abortado por el usuario"})
        else:
            send_ws_message({
                "type": "complete",
                "total_steps": pl.total_steps,
                "elapsed": time.perf_counter() - t_start,
                "warnings": pl.warnings,
            })


@app.post("/api/run")
def run_gcode():
    global job_thread
    _require_conn()
    if not loaded_gcode:
        raise HTTPException(status_code=400, detail="No hay G-code cargado")

    lines = loaded_gcode                # snapshot: el global puede cambiar
    transform = gcode_transform
    pl, pr = plotter, proto

    # PRE-VUELO. Antes esta comprobacion solo existia en plot_gcode_lines(),
    # que es el camino de la CLI: por HTTP no se ejecutaba NUNCA. Un fichero
    # marcado "no cabe" al subirlo se dibujaba igual, el carro llegaba al
    # tope y la maquina se descalibraba entera.
    if pl.enforce_soft_limits:
        b = bounds_of(lines, pl.z_pen_down_threshold, pl.chord_tol, transform)
        violation = check_bounds(b, pl.max_x, pl.max_y)
        if violation is not None:
            raise HTTPException(status_code=409, detail={
                "error": "fuera_de_area",
                "message": f"El dibujo no cabe en el area util. {violation.message()}.",
                "violation": violation.as_dict(),
                "bounds": b.as_dict(),
                "work_area": {"max_x_mm": pl.max_x, "max_y_mm": pl.max_y},
                # el frontend usa esto para ofrecer "Ajustar al area"
                "can_autofit": True,
            })

    pl.abort_check = _job_aborted       # [SW-49] aborto entre segmentos

    _claim_job()                        # [SW-48] marca ANTES de arrancar
    try:
        job_thread = threading.Thread(target=run_gcode_thread,
                                      args=(lines, abort_event, pl, pr, transform),
                                      daemon=True)
        job_thread.start()
    except Exception:
        _release_job()                  # si no arranco, liberar el puerto
        raise
    return {"ok": True, "total_lines": len(lines)}


@app.post("/api/stop")
def stop_gcode():
    era_activo = job_state["active"]
    abort_event.set()
    return {"ok": True, "was_running": era_activo}


# ─── POSICION ────────────────────────────────────────────────────────

class RecoverReq(BaseModel):
    action: str = Field(pattern='^(accept|reset)$')


@app.post("/api/recover-position")
def recover_position(req: RecoverReq):
    _require_conn()
    _require_idle()

    if req.action == "accept":
        # load_last_position() ya valida el fichero [SW-38], asi que si
        # devuelve algo, pos_x/pos_y estan y son enteros.
        last_pos = CNCProtocol.load_last_position()
        if not last_pos:
            raise HTTPException(status_code=400,
                                detail="No hay posicion guardada (o es demasiado vieja)")
        # [SW-1] X e Y salen del fichero; la Z REAL la sabe el MCU.
        proto.pos_x = last_pos["pos_x"]
        proto.pos_y = last_pos["pos_y"]
        proto.sync_firmware()
        plotter.invalidate_pen_cache()
        plotter._sync_gc_from_steps()
        CNCProtocol.clear_last_position()
        return {"ok": True, "message": "Posicion restaurada",
                "status": _status_dict()}

    proto.reset_position()
    plotter.gc_x = plotter.gc_y = 0.0
    CNCProtocol.clear_last_position()
    return {"ok": True, "message": "Origen XY reiniciado",
            "status": _status_dict()}


@app.post("/api/set-origin")
def set_origin():
    """Define la posicion XY actual como origen. NO toca la Z: el cero de
    la pluma se fija aparte con /api/z-set-zero, que es otra operacion."""
    _require_conn()
    _require_idle()
    proto.reset_position()
    plotter.gc_x = plotter.gc_y = 0.0
    CNCProtocol.clear_last_position()
    return {"ok": True, "message": "Origen XY fijado en la posicion actual"}


@app.post("/api/home")
def go_home():
    _require_conn()
    _require_idle()
    plotter.go_home()
    plotter.gc_x = plotter.gc_y = 0.0
    return _status_dict()


@app.post("/api/motors-off")
def motors_off():
    """Apaga SOLO X e Y. El eje Z sigue energizado para que la pluma no
    caiga por gravedad [SW-9]. Para apagar Z usa /api/z-off."""
    _require_conn()
    _require_idle()
    proto.motors_off()
    return _status_dict()


# ─── JOG ─────────────────────────────────────────────────────────────

class JogReq(BaseModel):
    axis: str = Field(pattern='^[xyzXYZ]$')
    direction: int
    # [SW-51] 0 no tiene sentido y 500 mm en una maquina de 40 mm tampoco
    distance_mm: float = Field(gt=0.0, le=500.0)


@app.post("/api/jog")
def jog(req: JogReq):
    _require_conn()
    _require_idle()
    cfg = load_config()

    axis = req.axis.lower()
    # [SW-50] La direccion es un SENTIDO, no un factor. Con direction=2,
    # step_x() hacia pos_x += 2*pasos y la posicion cacheada se separaba
    # del eje real: a partir de ahi todo el dibujo salia desplazado.
    direction = 1 if req.direction > 0 else -1

    if axis in ('x', 'y'):
        spm = plotter.spm_x if axis == 'x' else plotter.spm_y
        pos_steps = proto.pos_x if axis == 'x' else proto.pos_y
        limite = plotter.max_x if axis == 'x' else plotter.max_y

        steps = round(abs(req.distance_mm) * spm)
        actual_mm = pos_steps / spm
        future_mm = (pos_steps + direction * steps) / spm

        # A diferencia de antes, el limite del jog respeta enforce_soft_limits:
        # era el unico sitio de la app donde el ajuste no se tenia en cuenta.
        if plotter.enforce_soft_limits and (future_mm < -TOLERANCE_MM
                                            or future_mm > limite + TOLERANCE_MM):
            queda = remaining_mm(actual_mm, direction, limite)
            raise HTTPException(status_code=400, detail={
                "error": "fuera_de_area",
                # 'cuanto queda' en vez de solo 'no': el usuario esta delante
                # de la maquina intentando llegar a un sitio, y saber que le
                # quedan 3.2 mm es accionable; un 400 pelado no lo es.
                "message": (f"El eje {axis.upper()} llegaria a {future_mm:.1f} mm y "
                            f"el area es [0, {limite:g}] mm. "
                            f"En ese sentido quedan {queda:.1f} mm."),
                "axis": axis,
                "max_allowed_mm": round(queda, 2),
                "work_area": {"max_x_mm": plotter.max_x, "max_y_mm": plotter.max_y},
            })

        if axis == 'x':
            proto.step_x(direction, steps)
            plotter.gc_x = proto.pos_x / plotter.spm_x
        else:
            proto.step_y(direction, steps)
            plotter.gc_y = proto.pos_y / plotter.spm_y

    else:
        # [SW-6] escala propia de Z y limite propio. Antes usaba spm_x
        # y no tenia limite ninguno: se podia clavar contra el tope.
        spm_z = cfg["steps_per_mm_z"]
        steps = min(255, round(abs(req.distance_mm) * spm_z))
        if steps <= 0:
            raise HTTPException(
                status_code=400,
                detail=f"Distancia demasiado pequeña: {req.distance_mm}mm "
                       f"no llega a un paso con {spm_z} pasos/mm")
        future = proto.pos_z - direction * steps   # +1 sube => Z_POS baja
        if future < 0 or future > 255:
            raise HTTPException(
                status_code=400,
                detail=(f"Limite de Z: quedaria en {future} pasos (rango 0-255). "
                        f"Si tocaste el tope mecanico, usa /api/z-set-zero "
                        f"para redefinir el cero de la pluma."))
        proto.step_z(direction, steps)
        # el jog manual mueve Z por su cuenta: lo cacheado deja de valer
        plotter.invalidate_pen_cache()

    return _status_dict()


# ─── PLUMA / EJE Z ───────────────────────────────────────────────────

class PenReq(BaseModel):
    action: str          # "up" | "down" | "toggle"


@app.post("/api/pen")
def pen_action(req: PenReq):
    _require_conn()
    _require_idle()          # [SW-3b] ESTA era la guarda que faltaba
    # via plotter, no via proto: asi el cache de pluma [SW-46] se entera
    if req.action == 'up':
        plotter.pen_up()
    elif req.action == 'down':
        plotter.pen_down()
    elif req.action == 'toggle':
        plotter.pen_up() if proto.pen_down_flag else plotter.pen_down()
    else:
        raise HTTPException(status_code=400,
                            detail="Accion invalida (up|down|toggle)")
    return {"pen_down": proto.pen_down_flag, "z_steps": proto.pos_z}


class PenJogReq(BaseModel):
    # positivo = subir, negativo = bajar. Un paso de Z son decimas de mm:
    # 255 es el maximo que cabe en el payload de una trama.
    steps: int = Field(ge=-255, le=255)


@app.post("/api/pen-jog")
def pen_jog(req: PenJogReq):
    """Micro-jog del eje Z para calibrar la altura de la pluma."""
    _require_conn()
    _require_idle()
    if req.steps == 0:
        return {"ok": True, "z_steps": proto.pos_z}

    direction = 1 if req.steps > 0 else -1
    count = min(255, abs(req.steps))
    future = proto.pos_z - direction * count
    if future < 0 or future > 255:
        raise HTTPException(
            status_code=400,
            detail=f"Limite de Z: quedaria en {future} pasos (rango 0-255)")

    proto.step_z(direction, count)
    plotter.invalidate_pen_cache()
    return {"ok": True, "z_steps": proto.pos_z, "moved": count,
            "direction": "up" if direction > 0 else "down",
            "pen_down": proto.pen_down_flag}


class PenHolderReq(BaseModel):
    invert: bool


@app.post("/api/pen-holder")
def pen_holder(req: PenHolderReq):
    """[SW-30] Sentido fisico del eje Z segun como este montado el
    porta-pluma.

    EL PROBLEMA QUE RESUELVE: el mecanismo del eje Z se puede montar de
    dos formas, y en una de ellas el giro que deberia SUBIR la pluma la
    BAJA. Sin este ajuste, "pen up" dejaba la punta clavada en el papel
    y "pen down" la levantaba: los rapidos rayaban el dibujo y los
    trazos salian en blanco.

    COMO FUNCIONA: la inversion la hace el firmware (C_ZDIR), no el PC.
    Asi Z_POS = 0 sigue siendo "pluma arriba" y Z_POS = PEN_N sigue
    siendo "pluma abajo" en los dos montajes, con lo que pen_up/pen_down
    siguen siendo absolutos e idempotentes y el flujo de calibracion es
    exactamente el mismo.

    QUE HACE AL LLAMARLO: sube la pluma con el sentido ANTIGUO (para
    dejar Z_POS en 0 y no quedarse a medias), cambia el sentido y lo
    guarda en la config.

    DESPUES: revisa el cero de pluma. El sentido nuevo se aplica desde
    la posicion actual, asi que conviene hacer jog hasta la altura de
    seguridad y volver a llamar a /api/z-set-zero.
    """
    _require_conn()
    _require_idle()

    if proto.z_invert == req.invert:
        return {"ok": True, "pen_invert": proto.z_invert,
                "message": "Ya estaba en ese sentido", "rezero_needed": False}

    if not plotter.set_pen_invert(req.invert):
        if proto.z_invert_supported is False:
            raise HTTPException(
                status_code=501,
                detail="Este firmware no soporta C_ZDIR. Reprograma el "
                       "AT89S52 con la version actual de 8052_v2.asm.")
        raise HTTPException(status_code=502,
                            detail="El MCU no confirmo el cambio de sentido")

    if not save_config({"pen_invert": proto.z_invert}):
        raise HTTPException(
            status_code=500,
            detail="Sentido aplicado al MCU pero NO se pudo guardar en "
                   "la config: se perdera al reconectar")

    return {
        "ok": True,
        "pen_invert": proto.z_invert,
        "rezero_needed": True,
        "message": ("Sentido del eje Z invertido. Comprueba con "
                    "/api/pen-test-cycle y vuelve a fijar el cero con "
                    "/api/z-set-zero si la altura quedo mal."),
    }


@app.post("/api/z-set-zero")
def z_set_zero():
    """Define la altura actual de la pluma como 'arriba' (Z_POS = 0).

    Flujo de calibracion de pluma:
      1. jog de Z hasta la altura de seguridad
      2. este endpoint
      3. ajustar pen_steps con /api/pen-config
      4. probar con /api/pen-test-cycle
    Si el porta-pluma esta montado al reves, ANTES de todo esto hay que
    invertir el sentido con /api/pen-holder.

    A partir de aqui pen_up/pen_down son ABSOLUTOS: aunque se pierda un
    ACK o reinicies la app, siempre acaban en la posicion correcta."""
    _require_conn()
    _require_idle()
    ok = plotter.z_set_zero()
    return {"ok": ok, "z_steps": proto.pos_z}


@app.post("/api/z-off")
def z_off():
    """Apaga las bobinas del eje Z para que no se caliente.
    ATENCION: la pluma puede caer por gravedad. Despues hay que
    recolocarla y llamar a /api/z-set-zero."""
    _require_conn()
    _require_idle()
    ok = proto.z_off()
    plotter.invalidate_pen_cache()   # la pluma puede caerse: nada es fiable
    return {"ok": ok,
            "warning": "Z desenergizado: recoloca la pluma y vuelve a fijar el cero"}


@app.post("/api/pen-test-cycle")
def pen_test_cycle():
    """Ciclo completo ABAJO -> pausa -> ARRIBA para verificar la pluma.

    Es tambien la comprobacion del sentido del porta-pluma: si "abajo"
    levanta la punta y "arriba" la clava, hay que invertir el eje Z con
    /api/pen-holder."""
    _require_conn()
    _require_idle()
    # sin cache: este endpoint existe justo para mandar las dos tramas
    plotter.invalidate_pen_cache()
    plotter.pen_down()
    time.sleep(0.5)
    plotter.pen_up()
    st = proto.get_state()
    return {
        "ok": True,
        "pen_steps": proto.pen_steps,
        "pen_down": proto.pen_down_flag,
        "pen_invert": proto.z_invert,
        "mcu_z_pos": st["z_pos"] if st else None,
        # tras el ciclo Z_POS debe volver a 0; si no, se perdieron pasos.
        # Sin respuesta del MCU no se sabe: None, no False.
        "steps_lost": (st["z_pos"] != 0) if st else None,
    }


class PenTestLineReq(BaseModel):
    # Corta a proposito: es para mirar el trazo, no para gastar papel.
    length_mm: float = Field(default=20.0, gt=0.0, le=200.0)


@app.post("/api/pen-test-line")
def pen_test_line(req: PenTestLineReq = PenTestLineReq()):
    """Traza una linea corta AQUI MISMO y vuelve al punto de partida.

    Es lo que hace falta para ajustar la presion de la pluma: el ciclo de
    prueba dice si el eje Z pierde pasos, pero no si el trazo sale marcado,
    flojo o rayando el papel — eso solo se ve dibujando.

    A diferencia de /api/calibrate/steps/draw-line, NO redefine el origen:
    ajustar la pluma no deberia obligar a recalibrar la posicion."""
    _require_conn()
    _require_idle()

    inicio_x, inicio_y = plotter.gc_x, plotter.gc_y
    destino_x = inicio_x + req.length_mm

    # Si no cabe hacia la derecha, se traza hacia la izquierda antes que
    # rechazar la peticion: el usuario esta ajustando presion, no navegando.
    if plotter.enforce_soft_limits and destino_x > plotter.max_x + TOLERANCE_MM:
        destino_x = inicio_x - req.length_mm
        if destino_x < -TOLERANCE_MM:
            raise HTTPException(status_code=409, detail={
                "error": "fuera_de_area",
                "message": (f"No hay {req.length_mm:g} mm libres en X desde "
                            f"aqui ({inicio_x:.1f} mm). Movete al centro del "
                            f"area y volvé a probar."),
            })

    plotter.pen_down()
    plotter.line_to(destino_x, inicio_y)
    plotter.pen_up()
    plotter.rapid_to(inicio_x, inicio_y)     # dejarlo donde estaba

    return {"ok": True, "length_mm": abs(destino_x - inicio_x),
            "pen_steps": proto.pen_steps,
            "from": {"x_mm": inicio_x, "y_mm": inicio_y}}


class PenConfigReq(BaseModel):
    # Desde 1 y no desde 10: el ajuste fino de presion necesita bajar de 10
    # pasos en un porta-pluma sensible, y el firmware acepta 1..255 (PEN_N
    # es un byte y cnc_config._RANGES ya valida 1-255).
    pen_steps: int = Field(ge=1, le=255)


@app.post("/api/pen-config")
def pen_config(req: PenConfigReq):
    """[SW-5] Antes esto guardaba el valor en el JSON y NUNCA llegaba al
    firmware, que tenia PEN_N hardcodeado a 100. Ahora se envia y se
    verifica que el MCU lo confirma."""
    _require_conn()
    _require_idle()

    if not plotter.set_pen_steps(req.pen_steps):
        raise HTTPException(status_code=502, detail="El MCU no confirmo el cambio")

    # se guarda lo que el MCU confirmo, no lo que se pidio
    save_config({"pen_steps": proto.pen_steps})
    return {"ok": True, "pen_steps": proto.pen_steps}


# ─── AJUSTES ─────────────────────────────────────────────────────────

class SettingsReq(BaseModel):
    # [SW-51] Los rangos son los mismos que valida cnc_config._RANGES.
    # Sin ellos, un steps_per_mm=0 pasaba tal cual al plotter y cada
    # peticion posterior moria con ZeroDivisionError al convertir
    # pasos->mm: la API quedaba inservible hasta reiniciarla.
    steps_per_mm_x: float = Field(gt=0.0, le=5000.0)
    steps_per_mm_y: float = Field(gt=0.0, le=5000.0)
    steps_per_mm_z: float = Field(default=100.0, gt=0.0, le=5000.0)
    backlash_x: int = Field(ge=0, le=255)
    backlash_y: int = Field(ge=0, le=255)
    max_x_mm: float = Field(gt=0.0, le=1000.0)
    max_y_mm: float = Field(gt=0.0, le=1000.0)
    z_pen_down_threshold: Optional[float] = Field(default=None,
                                                  ge=-1000.0, le=1000.0)
    enforce_soft_limits: Optional[bool] = None
    # Sentido de los ejes TAL COMO LOS VE EL USUARIO. No cambian nada de la
    # cinematica: el espacio de pasos y los mm siguen viviendo en [0, max].
    # Solo dicen en que esquina se dibuja el (0,0) y hacia donde tiene que
    # mover cada flecha del D-pad. Ver frontend/src/coords.js.
    invert_x: Optional[bool] = None
    invert_y: Optional[bool] = None


@app.post("/api/settings")
def settings(req: SettingsReq):
    # Sin _require_conn(): el area de trabajo y el sentido de los ejes son
    # ajustes de presentacion, y obligar a tener la maquina enchufada para
    # cambiarlos no protegia de nada — solo impedia preparar la sesion.
    _require_idle()

    cambios = {
        "steps_per_mm_x": req.steps_per_mm_x,
        "steps_per_mm_y": req.steps_per_mm_y,
        "steps_per_mm_z": req.steps_per_mm_z,
        "backlash_x": req.backlash_x,
        "backlash_y": req.backlash_y,
        "max_x_mm": req.max_x_mm,
        "max_y_mm": req.max_y_mm,
    }
    if req.z_pen_down_threshold is not None:
        cambios["z_pen_down_threshold"] = req.z_pen_down_threshold
    if req.enforce_soft_limits is not None:
        cambios["enforce_soft_limits"] = req.enforce_soft_limits
    if req.invert_x is not None:
        cambios["invert_x"] = req.invert_x
    if req.invert_y is not None:
        cambios["invert_y"] = req.invert_y

    if plotter and proto:
        plotter.spm_x = req.steps_per_mm_x
        plotter.spm_y = req.steps_per_mm_y
        plotter.max_x = req.max_x_mm
        plotter.max_y = req.max_y_mm
        proto.backlash_x = req.backlash_x
        proto.backlash_y = req.backlash_y
        if req.z_pen_down_threshold is not None:
            plotter.z_pen_down_threshold = req.z_pen_down_threshold
        if req.enforce_soft_limits is not None:
            plotter.enforce_soft_limits = req.enforce_soft_limits
        # cambiar la escala mueve el significado de la posicion actual
        plotter._sync_gc_from_steps()

    if not save_config(cambios):
        raise HTTPException(status_code=500,
                            detail="Ajustes aplicados pero no guardados en disco")
    return {"ok": True, "status": _status_dict()}


class SpeedReq(BaseModel):
    draw: int = Field(ge=2, le=255)
    rapid: int = Field(ge=2, le=255)
    z: Optional[int] = Field(default=None, ge=4, le=255)


@app.post("/api/speed")
def speed(req: SpeedReq):
    """La velocidad de Z va aparte y vive en el firmware (VEL_Z), para que
    el eje Z no herede nunca la velocidad rapida de X/Y [SW-2].
    Minimo 4 ms: por debajo el 28BYJ-48 pierde par y se traba."""
    _require_conn()
    _require_idle()
    plotter.speed_draw = max(2, req.draw)
    plotter.speed_rapid = max(2, req.rapid)
    payload = {"speed_draw": plotter.speed_draw,
               "speed_rapid": plotter.speed_rapid}

    if req.z is not None:
        z_ms = max(4, min(255, req.z))
        if not proto.set_speed_z(z_ms):
            raise HTTPException(status_code=502,
                                detail="El MCU no confirmo la velocidad de Z")
        payload["speed_z"] = proto.z_speed

    save_config(payload)
    return {"ok": True, **payload}


# ─── PATRONES DE PRUEBA ──────────────────────────────────────────────

class TestPatternReq(BaseModel):
    pattern: str
    # [SW-51] size=0 dibujaba nada durante un rato; size=1e9 lanzaba
    # millones de tramas sin forma de pararlo mas que con /api/stop
    size: float = Field(gt=0.0, le=1000.0)


def run_pattern_thread(pattern, size, pl: CNCPlotter, pr: CNCProtocol):
    """[SW-52] pl/pr por parametro, igual que run_gcode_thread."""
    job_state.update({"total_lines": 1, "lines_processed": 0,
                      "progress": 0.0, "total_steps": 0, "elapsed": 0.0})
    pl.begin_job()
    t_start = time.perf_counter()
    try:
        PATTERNS[pattern](pl)(size)
        if not abort_event.is_set():
            pl.go_home()
    except LimitExceeded as e:
        send_ws_message({"type": "error",
                         "message": f"Fuera del area util. {e}"})
    except Exception as e:
        send_ws_message({"type": "error", "message": f"Error en el patron: {e}"})
    finally:
        try:
            pr.pen_up()
            pl.invalidate_pen_cache()
            pr._save_position()
        except Exception:
            pass
        _release_job()
        job_state["lines_processed"] = 1
        job_state["progress"] = 1.0
        send_ws_message({"type": "complete",
                         "total_steps": pl.total_steps,
                         "elapsed": time.perf_counter() - t_start,
                         "warnings": pl.warnings})


# El patron se valida en el endpoint, antes de arrancar el hilo: asi un
# nombre mal escrito da un 400 inmediato en vez de un error por WebSocket
# cuando el usuario ya cree que la maquina esta trabajando.
PATTERNS = {
    "square":   lambda pl: pl.draw_square,
    "triangle": lambda pl: pl.draw_triangle,
    "circle":   lambda pl: pl.draw_circle,
    "star":     lambda pl: pl.draw_star,
    "grid":     lambda pl: pl.draw_calibration_grid,
}

# Cuanto ocupa cada patron, en mm, para el tamano pedido. Hace falta porque
# 'size' NO significa lo mismo en todos: es el lado del cuadrado, pero el
# RADIO del circulo y el ESPACIADO de cada celda de la rejilla. Sin esto un
# "circulo de 60" en una maquina de 80 mm se sale (mide 121 mm de ancho), y
# hasta ahora se aceptaba y se dibujaba contra el tope.
PATTERN_EXTENTS = {
    "square":   lambda s: (s, s),
    "triangle": lambda s: (s, s * math.sqrt(3) / 2),
    "circle":   lambda s: (2 * s + 1, 2 * s + 1),   # centro en (r+1, r+1)
    "star":     lambda s: (s + 1, s + 1),           # r = s/2, centro en (r+1, r+1)
    "grid":     lambda s: (s * 4, s * 4),           # count=4 celdas por lado
}


def _pattern_bounds(pattern: str, size: float) -> Bounds:
    w, h = PATTERN_EXTENTS[pattern](size)
    return Bounds(0.0, w, 0.0, h)


def _pattern_max_size(pattern: str, max_x: float, max_y: float) -> float:
    """Tamano maximo de ese patron que cabe en el area.

    Se DERIVA de PATTERN_EXTENTS resolviendo la recta (todas las extensiones
    son afines en size) en vez de mantener una segunda tabla de maximos: dos
    tablas se desincronizan en cuanto alguien toque un patron, y el sintoma
    seria un boton habilitado para un dibujo que no cabe."""
    f = PATTERN_EXTENTS[pattern]
    w0, h0 = f(0.0)
    w1, h1 = f(1.0)
    limites = []
    if w1 - w0 > 1e-9:
        limites.append((max_x + TOLERANCE_MM - w0) / (w1 - w0))
    if h1 - h0 > 1e-9:
        limites.append((max_y + TOLERANCE_MM - h0) / (h1 - h0))
    return max(0.0, min(limites)) if limites else 1000.0


@app.get("/api/patterns")
def list_patterns():
    """Los patrones y hasta que tamano cabe cada uno en el area actual.

    El frontend lo necesita para deshabilitar el boton en vez de dejar
    pulsar y devolver un 409: 'un estado invalido no deberia poder pedirse'."""
    cfg = load_config()
    return {"ok": True, "patterns": [
        {"id": nombre,
         "max_size_mm": round(_pattern_max_size(nombre, cfg["max_x_mm"],
                                                cfg["max_y_mm"]), 2)}
        for nombre in sorted(PATTERNS)
    ]}


@app.post("/api/test-pattern")
def test_pattern(req: TestPatternReq):
    global job_thread
    _require_conn()
    if req.pattern not in PATTERNS:
        raise HTTPException(
            status_code=400,
            detail=f"Patron desconocido: {req.pattern}. "
                   f"Validos: {', '.join(sorted(PATTERNS))}")

    pl, pr = plotter, proto

    # Mismo pre-vuelo que /api/run. 'size' no es el ancho en todos los
    # patrones (en el circulo es el radio, en la rejilla el espaciado), asi
    # que el limite de 1000 mm del modelo no dice nada sobre si cabe.
    if pl.enforce_soft_limits:
        b = _pattern_bounds(req.pattern, req.size)
        violation = check_bounds(b, pl.max_x, pl.max_y)
        if violation is not None:
            maximo = _pattern_max_size(req.pattern, pl.max_x, pl.max_y)
            raise HTTPException(status_code=409, detail={
                "error": "fuera_de_area",
                "message": (f"Un {req.pattern} de {req.size:g} mm ocupa "
                            f"{b.width:.1f}x{b.height:.1f} mm y el area util es "
                            f"{pl.max_x:g}x{pl.max_y:g} mm. "
                            f"El maximo para este patron es {maximo:.1f} mm."),
                "violation": violation.as_dict(),
                "bounds": b.as_dict(),
                "max_size_mm": round(maximo, 2),
                "work_area": {"max_x_mm": pl.max_x, "max_y_mm": pl.max_y},
            })

    pl.abort_check = _job_aborted

    _claim_job()                        # [SW-48]
    try:
        job_thread = threading.Thread(
            target=run_pattern_thread,
            args=(req.pattern, req.size, pl, pr), daemon=True)
        job_thread.start()
    except Exception:
        _release_job()
        raise
    return {"ok": True}


# ─── CALIBRACION ─────────────────────────────────────────────────────

CAL_LINE_MM = 30.0


class CalStepsDrawReq(BaseModel):
    # X e Y se calibran por SEPARADO. Esta maquina es de cremallera y pinon
    # con dos ejes distintos: aplicar la medida de X tambien a Y —que es lo
    # que se hacia— dejaba Y sistematicamente mal calibrado.
    axis: str = Field(default='x', pattern='^[xyXY]$')


class CalStepsApplyReq(BaseModel):
    axis: str = Field(default='x', pattern='^[xyXY]$')
    measured_mm: float = Field(gt=0.0, le=1000.0)


@app.post("/api/calibrate/steps/draw-line")
def cal_steps_draw(req: CalStepsDrawReq = CalStepsDrawReq()):
    """Paso 1: dibuja una linea de referencia de 30 mm en el eje pedido."""
    _require_conn()
    _require_idle()
    axis = req.axis.lower()
    limite = plotter.max_x if axis == 'x' else plotter.max_y

    # La linea de referencia tambien tiene que caber: en un area pequena
    # estos 30 mm iban derechos contra el tope.
    if plotter.enforce_soft_limits and CAL_LINE_MM > limite + TOLERANCE_MM:
        raise HTTPException(status_code=409, detail={
            "error": "fuera_de_area",
            "message": (f"La linea de calibracion mide {CAL_LINE_MM:g} mm y el eje "
                        f"{axis.upper()} solo tiene {limite:g} mm. Ampliá el área "
                        f"en Ajustes si la máquina da más de sí."),
            "axis": axis,
        })

    proto.reset_position()
    plotter.gc_x = plotter.gc_y = 0.0
    plotter.pen_down()
    if axis == 'x':
        plotter.line_to(CAL_LINE_MM, 0)
    else:
        plotter.line_to(0, CAL_LINE_MM)
    plotter.pen_up()

    pasos = proto.pos_x if axis == 'x' else proto.pos_y
    spm = plotter.spm_x if axis == 'x' else plotter.spm_y
    return {"ok": True, "axis": axis, "target_mm": CAL_LINE_MM,
            "steps_sent": pasos, "current_spm": spm}


@app.post("/api/calibrate/steps/apply")
def cal_steps_apply(req: CalStepsApplyReq):
    """Paso 2: el usuario midio la linea; se recalcula steps_per_mm del eje."""
    _require_conn()
    _require_idle()
    axis = req.axis.lower()
    pasos = proto.pos_x if axis == 'x' else proto.pos_y
    if pasos <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"Dibuja primero la linea de referencia en {axis.upper()}")

    old_spm = plotter.spm_x if axis == 'x' else plotter.spm_y
    new_spm = pasos / req.measured_mm
    error_mm = abs(CAL_LINE_MM - req.measured_mm)

    if axis == 'x':
        plotter.spm_x = new_spm
        cambios = {"steps_per_mm_x": round(new_spm, 2)}
    else:
        plotter.spm_y = new_spm
        cambios = {"steps_per_mm_y": round(new_spm, 2)}
    cambios["last_calibration_date"] = time.strftime("%Y-%m-%d %H:%M")
    save_config(cambios)

    plotter.go_home()
    proto.reset_position()
    plotter.gc_x = plotter.gc_y = 0.0

    return {"ok": True, "axis": axis, "old_spm": round(old_spm, 2),
            "new_spm": round(new_spm, 2), "error_mm": round(error_mm, 2),
            "error_pct": round(error_mm / CAL_LINE_MM * 100, 1)}


class CalBacklashMoveReq(BaseModel):
    axis: str = Field(pattern='^[xyXY]$')
    steps: int = Field(ge=-10000, le=10000)   # positivo o negativo


@app.post("/api/calibrate/backlash/move")
def cal_backlash_move(req: CalBacklashMoveReq):
    """Mueve N pasos SIN compensacion de backlash, para poder medirlo puro."""
    _require_conn()
    _require_idle()
    axis = req.axis.lower()
    if req.steps == 0:
        return {"ok": True, "moved": 0,
                "pos_x": proto.pos_x, "pos_y": proto.pos_y}

    direction = 1 if req.steps > 0 else -1
    remaining = abs(req.steps)
    moved = 0
    cmd = ((CMD_X_POS if direction > 0 else CMD_X_NEG) if axis == 'x'
           else (CMD_Y_POS if direction > 0 else CMD_Y_NEG))

    while remaining > 0:
        chunk = min(remaining, 255)
        if not proto.send_command(cmd, chunk, retries=1):
            break                       # [SW-18] no sumar lo que no se movio
        moved += chunk
        remaining -= chunk

    if axis == 'x':
        proto.pos_x += direction * moved
        # este endpoint mueve el eje saltandose step_x(), asi que la
        # direccion cacheada para el backlash tambien hay que anotarla
        proto._update_dir('x', direction)
    else:
        proto.pos_y += direction * moved
        proto._update_dir('y', direction)
    plotter._sync_gc_from_steps()

    return {"ok": moved == abs(req.steps), "moved": moved,
            "pos_x": proto.pos_x, "pos_y": proto.pos_y}


class CalBacklashApplyReq(BaseModel):
    backlash_x: int = Field(ge=0, le=255)
    backlash_y: int = Field(ge=0, le=255)


@app.post("/api/calibrate/backlash/apply")
def cal_backlash_apply(req: CalBacklashApplyReq):
    _require_conn()
    _require_idle()
    proto.set_backlash(req.backlash_x, req.backlash_y)
    save_config({"backlash_x": proto.backlash_x,
                 "backlash_y": proto.backlash_y,
                 "last_calibration_date": time.strftime("%Y-%m-%d %H:%M")})
    proto.reset_position()
    plotter.gc_x = plotter.gc_y = 0.0
    return {"ok": True, "backlash_x": proto.backlash_x,
            "backlash_y": proto.backlash_y}


# ─── WEBSOCKET ───────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)
    try:
        st = await run_in_threadpool(_status_dict)
        await websocket.send_json({"type": "status", **st})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if websocket in active_websockets:
            active_websockets.remove(websocket)


# ─── FRONTEND ────────────────────────────────────────────────────────

frontend_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "frontend"))
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
else:
    print(f"Aviso: no se encontro el directorio de frontend '{frontend_dir}'.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
