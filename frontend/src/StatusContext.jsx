import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { api, openStatusSocket } from './api'

const StatusContext = createContext(null)

const POLL_INTERVAL_MS = 1500
const WS_RETRY_MS = 2000

// La estela viva se guarda en memoria; un trabajo largo emite ~5 muestras por
// segundo, asi que se acota para no crecer sin limite en sesiones de horas.
const MAX_TRAIL_POINTS = 20000

// Distancia minima entre dos muestras guardadas de la estela, en mm.
//
// La mayoria de las muestras que llegan durante un trabajo estan practicamente
// encima de la anterior (el cabezal apenas se movio en 200 ms de trazo lento) y
// se pintarian en el mismo pixel. Descartarlas tiene dos efectos que importan:
// el array crece mucho mas despacio, y —sobre todo— sigue siendo un array al
// que SOLO se anade, que es lo que permite a useTrailPath ir concatenando el
// atributo `d` en vez de reconstruirlo entero cinco veces por segundo.
const TRAIL_MIN_STEP_MM = 0.15

const EMPTY_LIVE = { active: false, line: 0, x: null, y: null, zSteps: null, trail: [] }

const Z_ENERGIZED_KEY = 'cnc.zEnergized'

export function StatusProvider({ children }) {
  const [status, setStatus] = useState(null)
  const [config, setConfig] = useState(null)
  const [banner, setBanner] = useState(null)
  const [gcode, setGcode] = useState(null)
  const [live, setLive] = useState(EMPTY_LIVE)

  // El backend no reporta si el eje Z esta energizado: es una consecuencia de
  // haber llamado a /api/z-off y solo la sabe quien pulso el boton. Se guarda
  // en sessionStorage para que el aviso sobreviva a un F5 — perder ese banner
  // significa que la pluma puede estar cayendose por gravedad sin que nadie lo
  // sepa.
  const [zEnergized, setZEnergizedState] = useState(
    () => sessionStorage.getItem(Z_ENERGIZED_KEY) !== 'false',
  )

  const statusRef = useRef(null)
  const mountedRef = useRef(true)
  const wsRef = useRef(null)
  const wsRetryTimer = useRef(null)

  statusRef.current = status

  const setZEnergized = useCallback((value) => {
    sessionStorage.setItem(Z_ENERGIZED_KEY, value ? 'true' : 'false')
    setZEnergizedState(value)
  }, [])

  const refreshStatus = useCallback(async () => {
    try {
      const st = await api.getStatus()
      if (mountedRef.current) {
        setStatus(st)
        // Si el banner visible era el de "no se pudo consultar el estado" de un
        // intento anterior, se limpia solo al recuperar la conexion con el backend.
        setBanner((prev) => (prev?.text?.startsWith('No se pudo consultar el estado') ? null : prev))
      }
      return st
    } catch (e) {
      if (mountedRef.current) {
        setBanner({ type: 'error', text: `No se pudo consultar el estado: ${e.message}` })
      }
      return null
    }
  }, [])

  // last_calibration_date solo viaja en /api/config, no en /api/status: sin
  // esta llamada la tarjeta de calibracion no puede decir "hace 3 dias".
  const refreshConfig = useCallback(async () => {
    try {
      const cfg = await api.getConfig()
      if (mountedRef.current) setConfig(cfg)
      return cfg
    } catch {
      // no es critico: la tarjeta cae a "estado desconocido" en vez de romper
      return null
    }
  }, [])

  // Estado inicial, sin esperar al WebSocket.
  useEffect(() => {
    mountedRef.current = true
    refreshStatus()
    refreshConfig()
    return () => {
      mountedRef.current = false
    }
  }, [refreshStatus, refreshConfig])

  // WebSocket con reconexion simple.
  useEffect(() => {
    let alive = true

    function connect() {
      if (!alive) return
      wsRef.current = openStatusSocket({
        onOpen: () => {},
        onMessage: (msg) => {
          if (!alive) return
          if (msg.type === 'status') {
            const { type: _type, ...rest } = msg
            setStatus(rest)
          } else if (msg.type === 'progress') {
            setStatus((prev) =>
              prev
                ? {
                    ...prev,
                    job: {
                      ...(prev.job || {}),
                      active: true,
                      progress: msg.percent / 100,
                      lines_processed: msg.line,
                      total_lines: msg.total,
                      total_steps: msg.steps,
                      elapsed: msg.elapsed,
                    },
                    position: {
                      ...prev.position,
                      x_mm: msg.pos_x_mm,
                      y_mm: msg.pos_y_mm,
                      z_steps: msg.pos_z_steps,
                    },
                  }
                : prev,
            )
            // Muestra para el lienzo. Es la posicion REAL reportada por el
            // backend, no una interpolacion: la estela es la prueba de por
            // donde paso la maquina.
            setLive((prev) => {
              const punto = [msg.pos_x_mm, msg.pos_y_mm, msg.pos_z_steps]
              const ultimo = prev.trail[prev.trail.length - 1]
              // Se guarda la muestra si el cabezal se movio lo suficiente O si
              // cambio el estado de la pluma — ese cambio es el que corta el
              // trazo, y perderlo uniria dos trazos que no se tocan.
              const vale =
                !ultimo ||
                ultimo[2] !== punto[2] ||
                Math.abs(ultimo[0] - punto[0]) >= TRAIL_MIN_STEP_MM ||
                Math.abs(ultimo[1] - punto[1]) >= TRAIL_MIN_STEP_MM

              let trail = prev.trail
              if (vale) {
                trail =
                  prev.trail.length >= MAX_TRAIL_POINTS
                    ? [...prev.trail.slice(1), punto]
                    : [...prev.trail, punto]
              }
              return {
                active: true,
                line: msg.line,
                x: msg.pos_x_mm,
                y: msg.pos_y_mm,
                zSteps: msg.pos_z_steps,
                trail,
              }
            })
          } else if (msg.type === 'error') {
            setBanner({ type: 'error', text: msg.message })
            // El recorrido se congela donde quedo: sirve para ver en que punto
            // del dibujo se aborto.
            setLive((prev) => ({ ...prev, active: false }))
            refreshStatus()
          } else if (msg.type === 'complete') {
            const warn = msg.warnings?.length ? ` (avisos: ${msg.warnings.join(', ')})` : ''
            setBanner({ type: 'success', text: `Trabajo completado${warn}` })
            setLive((prev) => ({ ...prev, active: false }))
            refreshStatus()
          }
        },
        onClose: () => {
          if (!alive) return
          wsRetryTimer.current = setTimeout(connect, WS_RETRY_MS)
        },
      })
    }

    connect()
    return () => {
      alive = false
      if (wsRetryTimer.current) clearTimeout(wsRetryTimer.current)
      wsRef.current?.close()
    }
  }, [refreshStatus])

  // Polling de respaldo: solo cuando no hay un job activo (el backend no emite
  // "status" periodico por WS fuera de un job, solo progreso).
  useEffect(() => {
    const id = setInterval(() => {
      if (!statusRef.current?.job?.active) refreshStatus()
    }, POLL_INTERVAL_MS)
    return () => clearInterval(id)
  }, [refreshStatus])

  // Cuantas acciones hay en vuelo. Casi todas son llamadas SERIE BLOQUEANTES
  // de varios segundos (dibujar la linea de calibracion, un ciclo de pluma) y
  // hasta ahora nada lo reflejaba: el boton seguia pulsable, un segundo clic
  // encolaba otro comando en el puerto, y entre medias la interfaz parecia
  // colgada porque no pasaba nada visible. canOperate no sirve para esto —solo
  // cambia cuando vuelve el siguiente /api/status—.
  const [pending, setPending] = useState(0)

  const runAction = useCallback(
    async (fn) => {
      setBanner(null)
      setPending((n) => n + 1)
      try {
        const result = await fn()
        await refreshStatus()
        return result
      } catch (e) {
        setBanner({ type: 'error', text: e.message })
        throw e
      } finally {
        setPending((n) => n - 1)
      }
    },
    [refreshStatus],
  )

  // Cargar otro fichero invalida el recorrido dibujado del anterior: sin esto,
  // el dibujo nuevo apareceria medio pintado de azul nada mas subirlo.
  const resetLive = useCallback(() => setLive(EMPTY_LIVE), [])

  // Arranque de un trabajo: limpia la estela anterior ANTES de lanzarlo, para
  // que el lienzo no mezcle el recorrido viejo con el nuevo.
  const startJob = useCallback(
    async (fn) => {
      setLive({ ...EMPTY_LIVE, active: true })
      try {
        return await runAction(fn)
      } catch (e) {
        setLive(EMPTY_LIVE)
        throw e
      }
    },
    [runAction],
  )

  const connected = !!status?.connected
  const jobActive = !!status?.job?.active
  const commLost = !!status?.comm_lost
  const canOperate = connected && !jobActive && !commLost
  // Hay una llamada bloqueante en vuelo. Los controles que mandan comandos al
  // puerto la usan para deshabilitarse mientras dure.
  const busy = pending > 0

  // La pluma se deriva de la posicion de Z igual que hace el firmware
  // (pen_down_flag = pos_z >= pen_steps). status.pen_down solo se refresca en
  // el polling, que se apaga durante un trabajo: derivandolo aqui el indicador
  // tambien es fiel mientras la maquina dibuja.
  const penDown = useMemo(() => {
    const z = status?.position?.z_steps
    const penSteps = status?.pen_steps
    if (typeof z !== 'number' || typeof penSteps !== 'number') return !!status?.pen_down
    return z >= penSteps
  }, [status])

  // Motivo unico por el que algo esta deshabilitado. Centralizarlo evita que
  // cada panel invente su propia frase (y que alguna se olvide de comprobar
  // comm_lost, que es justo el caso en el que seguir mandando comandos a ciegas
  // hace mas dano).
  const reason = useCallback(
    (kind = 'move') => {
      if (!connected) {
        return kind === 'move'
          ? 'Conectá la máquina para mover los ejes'
          : 'Conectá la máquina primero'
      }
      if (commLost) return 'Se perdió la comunicación con la máquina'
      if (jobActive) return 'Hay un trabajo en curso'
      if (kind === 'run' && !gcode) return 'Subí un archivo G-code primero'
      // El backend tambien lo rechaza (409 en /api/run), pero dejar pulsar
      // Ejecutar para que salte un error no ayuda a nadie: el panel del rail
      // ofrece "Ajustar al area" justo al lado.
      if (kind === 'run' && gcode?.fits_in_area === false) {
        return 'El dibujo se sale del área de trabajo'
      }
      return null
    },
    [connected, commLost, jobActive, gcode],
  )

  // Memoizado. Sin esto se creaba un objeto nuevo en CADA render del proveedor
  // —incluidos los cinco por segundo del progreso— y eso re-renderizaba a
  // todos los consumidores de useStatus() aunque no hubiera cambiado nada de
  // lo que ellos leen: la barra superior, el rail entero, los cuatro paneles y
  // el lienzo.
  const value = useMemo(
    () => ({
      status,
      config,
      banner,
      setBanner,
      gcode,
      setGcode,
      live,
      resetLive,
      zEnergized,
      setZEnergized,
      refreshStatus,
      refreshConfig,
      runAction,
      startJob,
      connected,
      jobActive,
      commLost,
      canOperate,
      busy,
      penDown,
      reason,
    }),
    [status, config, banner, gcode, live, zEnergized, setZEnergized,
     refreshStatus, refreshConfig, runAction, startJob, resetLive,
     connected, jobActive, commLost, canOperate, busy, penDown, reason],
  )

  return <StatusContext.Provider value={value}>{children}</StatusContext.Provider>
}

export function useStatus() {
  const ctx = useContext(StatusContext)
  if (!ctx) throw new Error('useStatus debe usarse dentro de <StatusProvider>')
  return ctx
}
