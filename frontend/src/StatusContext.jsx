import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { api, openStatusSocket } from './api'

const StatusContext = createContext(null)

const POLL_INTERVAL_MS = 1500
const WS_RETRY_MS = 2000

// estela en memoria, ~5 muestras/seg, sin techo crece para siempre
const MAX_TRAIL_POINTS = 20000

// distancia minima entre muestras, para que la estela no crezca por nada
const TRAIL_MIN_STEP_MM = 0.15

const EMPTY_LIVE = { active: false, line: 0, x: null, y: null, zSteps: null, trail: [] }

const Z_ENERGIZED_KEY = 'cnc.zEnergized'

export function StatusProvider({ children }) {
  const [status, setStatus] = useState(null)
  const [config, setConfig] = useState(null)
  const [banner, setBanner] = useState(null)
  const [gcode, setGcode] = useState(null)
  const [live, setLive] = useState(EMPTY_LIVE)

  // en sessionStorage para no perder el aviso de Z con un F5
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
        // se borra solo cuando vuelve a andar la conexion
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

  // viaja por /api/config, no por /api/status
  const refreshConfig = useCallback(async () => {
    try {
      const cfg = await api.getConfig()
      if (mountedRef.current) setConfig(cfg)
      return cfg
    } catch {
      return null
    }
  }, [])

  // pide el estado inicial sin esperar al websocket
  useEffect(() => {
    mountedRef.current = true
    refreshStatus()
    refreshConfig()
    return () => {
      mountedRef.current = false
    }
  }, [refreshStatus, refreshConfig])

  // websocket con reconexion simple
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
            // posicion real del backend, no interpolada, prueba real de por donde paso
            setLive((prev) => {
              const punto = [msg.pos_x_mm, msg.pos_y_mm, msg.pos_z_steps]
              const ultimo = prev.trail[prev.trail.length - 1]
              // guarda la muestra si se movio o si cambio la pluma, eso corta el trazo
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
            // dejamos el recorrido congelado donde quedo, sirve para ver
            // en que punto se aborto
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

  // polling de respaldo, solo si no hay job activo
  useEffect(() => {
    const id = setInterval(() => {
      if (!statusRef.current?.job?.active) refreshStatus()
    }, POLL_INTERVAL_MS)
    return () => clearInterval(id)
  }, [refreshStatus])

  // cuantas acciones en vuelo, sin esto un segundo click encolaba otro comando
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

  // subir otro archivo invalida el recorrido del anterior
  const resetLive = useCallback(() => setLive(EMPTY_LIVE), [])

  // limpia la estela antes del job para no mezclar el recorrido viejo
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
  // llamada bloqueante en vuelo, los controles se deshabilitan mientras dura
  const busy = pending > 0

  // deriva la pluma de Z, igual que el firmware, sigue correcto durante un job
  const penDown = useMemo(() => {
    const z = status?.position?.z_steps
    const penSteps = status?.pen_steps
    if (typeof z !== 'number' || typeof penSteps !== 'number') return !!status?.pen_down
    return z >= penSteps
  }, [status])

  // motivo unico por el que algo esta deshabilitado, para no repetirlo en cada panel
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
      // el backend igual lo rechaza, dejarlo clickear solo para fallar no sirve
      if (kind === 'run' && gcode?.fits_in_area === false) {
        return 'El dibujo se sale del área de trabajo'
      }
      return null
    },
    [connected, commLost, jobActive, gcode],
  )

  // memoizado, si no cada render del provider vuelve a renderizar todo lo que usa useStatus
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
