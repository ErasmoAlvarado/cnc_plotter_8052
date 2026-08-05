"""
api usa fastapi
;se comunica con http y utiliza websockets or la comunicaacion bidereccional


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


# limites

MAX_GCODE_LINES = 200_000        
MAX_PREVIEW_PATHS = 5_000       
MAX_PREVIEW_ARC_POINTS = 64      


# estado global

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


gcode_transform: GcodeTransform = IDENTITY
gcode_bounds_raw: Bounds = Bounds()    

abort_event = threading.Event()
job_thread: Optional[threading.Thread] = None
active_websockets: List[WebSocket] = []
loop: Optional[asyncio.AbstractEventLoop] = None


job_lock = threading.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global loop
    loop = asyncio.get_running_loop()
    yield
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000", "http://127.0.0.1:8000",
        "http://localhost:5173", "http://127.0.0.1:5173",   
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# helpers

def _require_conn():
    if not proto or not plotter:
        raise HTTPException(status_code=400, detail="No conectado")


def _require_idle():
    """nadie toca el puerto mientras hay un job corriendo"""
    if job_state["active"]:
        raise HTTPException(status_code=409, detail="Hay un job en curso")


def _claim_job():
    """reserva el puerto para un trabajo nuevo de forma atomica.
    _require_idle() sola no alcanza, entre "no hay job" y que arranque el
    hilo hay una ventana donde una segunda peticion tambien ve libre el
    puerto - por eso esto marca active=True aca mismo y no dentro del
    hilo, sino dos jobs casi simultaneos se pisan las tramas"""
    with job_lock:
        if job_state["active"]:
            raise HTTPException(status_code=409, detail="Hay un job en curso")
        abort_event.clear()              # arrancar sin abort viejo pegado
        job_state.update({"active": True, "progress": 0.0,
                          "lines_processed": 0, "total_lines": 0,
                          "total_steps": 0, "elapsed": 0.0})


def _release_job():
    with job_lock:
        job_state["active"] = False


def _job_aborted() -> bool:
    """el abort solo cuenta mientras hay un job activo. plotter.abort_check
    apunta aca (no directo a abort_event.is_set) pq /api/stop y
    /api/disconnect dejan el flag puesto, y sino el siguiente movimiento
    largo (calibracion, home, patron) se cancelaria solo sin avisar"""
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
    """version sincrona del estado, asi los endpoints bloqueantes la
    pueden llamar sin tener que volverse async y congelar el event loop"""
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
        # supported=False es firmware viejo sin C_ZDIR, hay que reflashear
        "pen_invert": proto.z_invert,
        "pen_invert_supported": proto.z_invert_supported,
        "z_pen_down_threshold": plotter.z_pen_down_threshold,
        "enforce_soft_limits": plotter.enforce_soft_limits,
        # presentacion, no cinematica - el backend solo guarda y reporta,
        # quien lo aplica de verdad es frontend/src/coords.js
        "invert_x": cfg["invert_x"],
        "invert_y": cfg["invert_y"],
    }


# conexion

class ConnectReq(BaseModel):
    port: Optional[str] = None
    simulate: bool = False


@app.post("/api/connect")
def connect(req: ConnectReq):
    global proto, plotter
    _require_idle()
    if proto and (proto.simulate or (proto.ser and proto.ser.is_open)):
        return {"ok": True, "port": proto.port, "message": "Ya conectado"}

    # una desconexion o un /api/stop de antes puede haber dejado el flag
    # pegado, si no se limpia aca el primer movimiento largo de la sesion
    # se aborta solo sin mover nada
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
    # from_config empuja VEL_Z, PEN_N y Z_DIR al firmware y relee
    cfg = load_config()
    plotter = CNCPlotter.from_config(proto, cfg)
    plotter.abort_check = _job_aborted

    mcu = proto.get_state()

    aviso = None
    if cfg.get("pen_invert") and proto.z_invert_supported is False:
        aviso = ("La config pide el eje Z invertido pero este firmware no "
                 "soporta C_ZDIR. Reprograma el AT89S52 con la version "
                 "actual de 8052_v2.asm.")

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
    """aborta el job y espera al hilo antes de matar proto - si no se
    espera y el hilo sigue vivo, revienta con AttributeError"""
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
    """boton de panico, relee el estado real del mcu y realinea el pc en
    vez de tener que reiniciar toda la app"""
    _require_conn()
    _require_idle()
    ok = proto.sync_firmware()
    plotter.invalidate_pen_cache()
    return {"ok": ok, "state": proto.get_state(), "status": _status_dict()}


@app.get("/api/serial-ports")
def get_serial_ports():
    return [{"port": p.device, "description": p.description}
            for p in serial.tools.list_ports.comports()]


@app.get("/api/config")
def get_config():
    return load_config()


# g-code

def _preview_chord_tol(cfg) -> float:
    """la misma tolerancia de cuerda que usa el plotter al dibujar
    (CNCPlotter.chord_tol) - si el preview segmentara distinto, la
    geometria mostrada no seria la que se ejecuta de verdad"""
    spm_x = max(1e-6, cfg["steps_per_mm_x"])
    spm_y = max(1e-6, cfg["steps_per_mm_y"])
    return min(1.0 / spm_x, 1.0 / spm_y)


def _gcode_payload(filename=None) -> dict:
    """respuesta comun de /api/upload-gcode y /api/gcode-transform. recorre
    el g-code una vez con gcode_walk (el mismo interprete que dibuja) y de
    esa pasada saca preview y caja delimitadora juntos"""
    cfg = load_config()
    max_x, max_y = cfg["max_x_mm"], cfg["max_y_mm"]

    preview_paths = []
    preview_truncated = False
    min_x = min_y = float('inf')
    max_bx = max_by = float('-inf')

    # el indice de linea viaja con cada trazo del preview asi el frontend
    # puede pintar en vivo que trazo se esta dibujando 
    prev = gcode_transform.apply(0.0, 0.0)
    for ev in walk_loaded(cfg):
        if isinstance(ev, MoveEvent):
            puntos = [prev, (ev.x, ev.y)]
            muestra = puntos
            prev = (ev.x, ev.y)
        elif isinstance(ev, ArcEvent):
            pts = list(ev.points)

            paso = max(1, len(pts) // MAX_PREVIEW_ARC_POINTS)
            muestra = [prev] + pts[::paso]
            if muestra[-1] != pts[-1]:
                muestra.append(pts[-1])
            puntos = pts
            prev = pts[-1]
        else:
            continue

        for px, py in puntos:                 
            min_x = min(min_x, px)          
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
    """recorre el g-code cargado con el transform vigente. usa el default
    initial_pen_down=False pq el preview describe el archivo, no el
    estado actual de la maquina"""
    return walk(loaded_gcode,
                z_pen_down_threshold=cfg["z_pen_down_threshold"],
                chord_tol=_preview_chord_tol(cfg),
                transform=gcode_transform)


@app.post("/api/upload-gcode")
async def upload_gcode(file: UploadFile = File(...)):
    global loaded_gcode, gcode_transform, gcode_bounds_raw
    _require_idle()

    content = await file.read()
    lineas = content.decode('utf-8', errors='replace').splitlines()
    if len(lineas) > MAX_GCODE_LINES:
        raise HTTPException(
            status_code=413,
            detail=f"G-code demasiado grande: {len(lineas)} lineas "
                   f"(maximo {MAX_GCODE_LINES})")

    loaded_gcode = lineas
    gcode_transform = IDENTITY          #

    cfg = load_config()
    gcode_bounds_raw = bounds_of(lineas, cfg["z_pen_down_threshold"],
                                 _preview_chord_tol(cfg))
    return _gcode_payload(filename=file.filename)


class GcodeTransformReq(BaseModel):
    flip_y: bool = False
    fit: bool = False


@app.post("/api/gcode-transform")
def set_gcode_transform(req: GcodeTransformReq):
    """aplica espejo/ajuste al g-code ya cargado y devuelve el preview
    nuevo, sin resubir ni reescribir el archivo - el transform es un dato
    aparte que consume el mismo walker"""
    global gcode_transform
    _require_idle()
    if not loaded_gcode:
        raise HTTPException(status_code=400, detail="No hay G-code cargado")

    cfg = load_config()
    gcode_transform = build_transform(gcode_bounds_raw,
                                      cfg["max_x_mm"], cfg["max_y_mm"],
                                      flip_y=req.flip_y, fit=req.fit)
    return _gcode_payload()


def run_gcode_thread(lines, abort_evt, pl: CNCPlotter, pr: CNCProtocol,
                     transform: GcodeTransform = IDENTITY):
    """pl/pr llegan por parametro y no se leen de las globales, pq un
    /api/disconnect a mitad de trabajo las pone en None y si este hilo
    las leyera directo moriria con AttributeError dentro del finally sin
    avisar nunca por websocket"""
    total = len(lines)
    job_state.update({"total_lines": total, "lines_processed": 0,
                      "progress": 0.0, "total_steps": 0, "elapsed": 0.0})
    pl.begin_job()
    t_start = time.perf_counter()
    last_ws_update = 0.0

    try:
        for ev in pl.events(lines, transform):
            if abort_evt.is_set():
                break
            if pr.comm_lost:
                send_ws_message({"type": "error",
                                 "message": "Comunicacion perdida con el MCU"})
                break

            pl.exec_event(ev)


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
        send_ws_message({"type": "error",
                         "message": f"Fuera del area util. {e}"})
    except Exception as e:
        send_ws_message({"type": "error",
                         "message": f"Error de ejecucion: {e}"})
    finally:
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

    lines = loaded_gcode                
    transform = gcode_transform
    pl, pr = plotter, proto

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
                "can_autofit": True,
            })

    pl.abort_check = _job_aborted       

    _claim_job()                        #
    try:
        job_thread = threading.Thread(target=run_gcode_thread,
                                      args=(lines, abort_event, pl, pr, transform),
                                      daemon=True)
        job_thread.start()
    except Exception:
        _release_job()                  
        raise
    return {"ok": True, "total_lines": len(lines)}


@app.post("/api/stop")
def stop_gcode():
    era_activo = job_state["active"]
    abort_event.set()
    return {"ok": True, "was_running": era_activo}


# posicion

class RecoverReq(BaseModel):
    action: str = Field(pattern='^(accept|reset)$')


@app.post("/api/recover-position")
def recover_position(req: RecoverReq):
    _require_conn()
    _require_idle()

    if req.action == "accept":
        last_pos = CNCProtocol.load_last_position()
        if not last_pos:
            raise HTTPException(status_code=400,
                                detail="No hay posicion guardada (o es demasiado vieja)")
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
    """fija la posicion xy actual como origen, no toca Z - el cero de
    pluma se fija aparte con /api/z-set-zero"""
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
    """apaga solo x/y, Z sigue energizado para que la pluma no caiga por
    gravedad. para apagar Z esta /api/z-off aparte"""
    _require_conn()
    _require_idle()
    proto.motors_off()
    return _status_dict()


# jog

class JogReq(BaseModel):
    axis: str = Field(pattern='^[xyzXYZ]$')
    direction: int
    distance_mm: float = Field(gt=0.0, le=500.0)


@app.post("/api/jog")
def jog(req: JogReq):
    _require_conn()
    _require_idle()
    cfg = load_config()

    axis = req.axis.lower()
    direction = 1 if req.direction > 0 else -1

    if axis in ('x', 'y'):
        spm = plotter.spm_x if axis == 'x' else plotter.spm_y
        pos_steps = proto.pos_x if axis == 'x' else proto.pos_y
        limite = plotter.max_x if axis == 'x' else plotter.max_y

        steps = round(abs(req.distance_mm) * spm)
        actual_mm = pos_steps / spm
        future_mm = (pos_steps + direction * steps) / spm

        if plotter.enforce_soft_limits and (future_mm < -TOLERANCE_MM
                                            or future_mm > limite + TOLERANCE_MM):
            queda = remaining_mm(actual_mm, direction, limite)
            raise HTTPException(status_code=400, detail={
                "error": "fuera_de_area",
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
        plotter.invalidate_pen_cache()

    return _status_dict()


# pluma / eje z

class PenReq(BaseModel):
    action: str          


@app.post("/api/pen")
def pen_action(req: PenReq):
    _require_conn()
    _require_idle()          
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
    steps: int = Field(ge=-255, le=255)


@app.post("/api/pen-jog")
def pen_jog(req: PenJogReq):
    """micro-jog de Z para calibrar la altura de la pluma"""
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
    """sentido fisico de Z segun como quedo el porta-pluma - si esta al
    reves "pen up" clava la punta y "pen down" la levanta. la inversion
    la hace el firmware (C_ZDIR) no el pc, asi Z_POS=0/PEN_N siguen
    significando lo mismo en los dos montajes. al llamarlo sube la pluma
    con el sentido viejo primero (para no quedar a medias), cambia el
    sentido y lo guarda. despues conviene revisar el cero con jog +
    /api/z-set-zero, el sentido nuevo aplica desde la posicion actual"""
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
    """fija la altura actual como "arriba" (Z_POS=0). flujo: jog hasta
    altura segura -> este endpoint -> /api/pen-config -> /api/pen-test-cycle.
    si el porta-pluma esta al reves hay q invertir antes con /api/pen-holder.
    desde aca pen_up/pen_down quedan absolutos aunque se pierda un ACK"""
    _require_conn()
    _require_idle()
    ok = plotter.z_set_zero()
    return {"ok": ok, "z_steps": proto.pos_z}


@app.post("/api/z-off")
def z_off():
    """apaga las bobinas de Z, ojo que la pluma puede caer por gravedad,
    despues hay que recolocarla y llamar /api/z-set-zero"""
    _require_conn()
    _require_idle()
    ok = proto.z_off()
    plotter.invalidate_pen_cache()   
    return {"ok": ok,
            "warning": "Z desenergizado: recoloca la pluma y vuelve a fijar el cero"}


@app.post("/api/pen-test-cycle")
def pen_test_cycle():
    """ciclo abajo -> pausa -> arriba, sirve tambien para chequear el
    sentido del porta-pluma (si "abajo" levanta y "arriba" clava, hay que
    invertir con /api/pen-holder)"""
    _require_conn()
    _require_idle()
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
        "steps_lost": (st["z_pos"] != 0) if st else None,
    }


class PenTestLineReq(BaseModel):
    length_mm: float = Field(default=20.0, gt=0.0, le=200.0)


@app.post("/api/pen-test-line")
def pen_test_line(req: PenTestLineReq = PenTestLineReq()):
    """traza una linea corta aca mismo y vuelve al punto de partida, sirve
    para ajustar presion (el ciclo de prueba dice si Z pierde pasos pero
    no si el trazo sale marcado o rayando, eso solo se ve dibujando). a
    diferencia de calibrate/steps/draw-line esto NO redefine el origen"""
    _require_conn()
    _require_idle()

    inicio_x, inicio_y = plotter.gc_x, plotter.gc_y
    destino_x = inicio_x + req.length_mm

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
    pen_steps: int = Field(ge=1, le=255)


@app.post("/api/pen-config")
def pen_config(req: PenConfigReq):
    """esto si llega hasta el firmware y se verifica que el mcu lo confirma"""
    _require_conn()
    _require_idle()

    if not plotter.set_pen_steps(req.pen_steps):
        raise HTTPException(status_code=502, detail="El MCU no confirmo el cambio")

    save_config({"pen_steps": proto.pen_steps})
    return {"ok": True, "pen_steps": proto.pen_steps}


# ajustes

class SettingsReq(BaseModel):
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
    invert_x: Optional[bool] = None
    invert_y: Optional[bool] = None


@app.post("/api/settings")
def settings(req: SettingsReq):
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
    """la velocidad de Z va aparte, vive en el firmware (VEL_Z) para que
    Z nunca herede la velocidad rapida de x/y. minimo 4ms, mas rapido y
    el 28BYJ-48 pierde par y se traba"""
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


# patrones de prueba

class TestPatternReq(BaseModel):
    pattern: str
    size: float = Field(gt=0.0, le=1000.0)


def run_pattern_thread(pattern, size, pl: CNCPlotter, pr: CNCProtocol):
    """pl/pr por parametro, igual razon que run_gcode_thread"""
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



PATTERNS = {
    "square":   lambda pl: pl.draw_square,
    "triangle": lambda pl: pl.draw_triangle,
    "circle":   lambda pl: pl.draw_circle,
    "star":     lambda pl: pl.draw_star,
    "grid":     lambda pl: pl.draw_calibration_grid,
}


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
    """maximo tamano de ese patron que entra en el area. se deriva de
    PATTERN_EXTENTS resolviendo la recta en vez de mantener otra tabla
    aparte que se desincronizaria apenas alguien toque un patron"""
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
    """los patrones y hasta que tamano entra cada uno en el area actual,
    el frontend lo usa para deshabilitar el boton en vez de dejar pulsar
    y devolver un 409 despues"""
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

    _claim_job()
    try:
        job_thread = threading.Thread(
            target=run_pattern_thread,
            args=(req.pattern, req.size, pl, pr), daemon=True)
        job_thread.start()
    except Exception:
        _release_job()
        raise
    return {"ok": True}


# calibracion

CAL_LINE_MM = 30.0


class CalStepsDrawReq(BaseModel):

    axis: str = Field(default='x', pattern='^[xyXY]$')


class CalStepsApplyReq(BaseModel):
    axis: str = Field(default='x', pattern='^[xyXY]$')
    measured_mm: float = Field(gt=0.0, le=1000.0)


@app.post("/api/calibrate/steps/draw-line")
def cal_steps_draw(req: CalStepsDrawReq = CalStepsDrawReq()):
    """paso 1: dibuja una linea de referencia de 30mm en el eje pedido"""
    _require_conn()
    _require_idle()
    axis = req.axis.lower()
    limite = plotter.max_x if axis == 'x' else plotter.max_y


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
    """paso 2: el usuario midio la linea, se recalcula steps_per_mm del eje"""
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
    """mueve N pasos sin compensar backlash, para poder medirlo puro"""
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
            break                      
        moved += chunk
        remaining -= chunk

    if axis == 'x':
        proto.pos_x += direction * moved

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


# websocket

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


# frontend

frontend_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "frontend"))
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
else:
    print(f"Aviso: no se encontro el directorio de frontend '{frontend_dir}'.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
