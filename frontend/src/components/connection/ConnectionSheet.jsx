import { useCallback, useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { api } from '../../api'
import { useStatus } from '../../StatusContext.jsx'
import { spring, useMotionPrefs } from '../../motion.js'
import Sheet from '../ui/Sheet.jsx'
import Button from '../ui/Button.jsx'
import Field from '../ui/Field.jsx'
import Toggle from '../ui/Toggle.jsx'
import Banner from '../ui/Banner.jsx'

// puerta de entrada a todo lo demas. va en una hoja y no en el dashboard
// porque se usa 2 veces por sesion: al empezar y al terminar
export default function ConnectionSheet({ open, onClose, onRecovery }) {
  const { status, connected, jobActive, runAction, setBanner, refreshConfig } = useStatus()
  const [ports, setPorts] = useState([])
  const [selectedPort, setSelectedPort] = useState('')
  const [simulate, setSimulate] = useState(false)
  const [busy, setBusy] = useState(false)
  const { t } = useMotionPrefs()

  const loadPorts = useCallback(async () => {
    try {
      setPorts(await api.listPorts())
    } catch (e) {
      setBanner({ type: 'error', text: `No se pudieron listar los puertos: ${e.message}` })
    }
  }, [setBanner])

  useEffect(() => {
    if (open && !connected) loadPorts()
  }, [open, connected, loadPorts])

  async function handleConnect() {
    setBusy(true)
    try {
      const result = await runAction(() => api.connect(selectedPort, simulate))
      await refreshConfig()
      // el aviso de firmware viene del propio /api/connect, si la config
      // pide Z invertido y el micro no sabe hacerlo, dibuja al aire
      if (result?.warning) setBanner({ type: 'warn', text: result.warning })
      if (result?.recovery) onRecovery(result.recovery)
      onClose()
    } catch {
      // runAction ya dejo el banner de error ahi
    } finally {
      setBusy(false)
    }
  }

  async function handleDisconnect() {
    setBusy(true)
    try {
      await runAction(api.disconnect)
      onClose()
    } catch {
      // idem
    } finally {
      setBusy(false)
    }
  }

  return (
    <Sheet open={open} onClose={onClose} title="Conexión">
      {/* al conectar la hoja entera pasa de formulario a confirmacion. es
          el unico momento en que el usuario esta mirando fijo esta hoja,
          por eso el cambio se ve y no pasa entre dos frames sin mas */}
      <AnimatePresence mode="wait" initial={false}>
      {connected ? (
        <motion.div
          key="connected"
          className="stack"
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={t(spring.gentle)}
        >
          <Banner tone={status?.simulating ? 'info' : 'success'}>
            {status?.simulating
              ? 'Estás en modo simulación: los movimientos se calculan pero no se envía nada por el puerto serie.'
              : `Conectado a ${status?.port ?? 'la máquina'}.`}
          </Banner>
          <Button variant="destructive-tinted" size="lg" block loading={busy} onClick={handleDisconnect}>
            Desconectar
          </Button>
        </motion.div>
      ) : (
        <motion.div
          key="disconnected"
          className="stack"
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={t(spring.gentle)}
        >
          <Field
            label="Puerto serie"
            hint="Dejalo en automático si no sabés cuál es: se prueba el primero que responda."
          >
            {(id) => (
              <select
                id={id}
                className="field__input"
                value={selectedPort}
                onChange={(e) => setSelectedPort(e.target.value)}
                disabled={simulate}
              >
                <option value="">Detectar automáticamente</option>
                {ports.map((p) => (
                  <option key={p.port} value={p.port}>
                    {p.port}
                    {p.description ? ` — ${p.description}` : ''}
                  </option>
                ))}
              </select>
            )}
          </Field>

          <div className="row">
            <Button variant="gray" size="sm" icon="resync" onClick={loadPorts}>
              Actualizar lista
            </Button>
            <span className="hint">
              {ports.length === 0 ? 'No se detectó ningún puerto' : `${ports.length} puerto(s)`}
            </span>
          </div>

          <hr className="divider" />

          <div className="row">
            <Toggle
              id="simulate-toggle"
              checked={simulate}
              onChange={setSimulate}
              label="Modo simulación"
            />
          </div>
          <p className="hint">
            Simula la máquina sin tocar el puerto serie. Sirve para probar un G-code, la interfaz o
            un patrón antes de encender nada.
          </p>

          <Button
            variant="filled"
            size="lg"
            block
            icon="plug"
            loading={busy}
            disabled={jobActive}
            onClick={handleConnect}
          >
            Conectar
          </Button>
        </motion.div>
      )}
      </AnimatePresence>
    </Sheet>
  )
}
