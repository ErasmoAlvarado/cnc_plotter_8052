import { useState } from 'react'
import { api } from '../../api'
import { useStatus } from '../../StatusContext.jsx'
import Button from '../ui/Button.jsx'
import Banner from '../ui/Banner.jsx'
import Reveal from '../ui/Reveal.jsx'
import DisabledHint from '../ui/DisabledHint.jsx'

// herramientas de diagnostico.
//
// "volver a sincronizar" es la respuesta cuando sospechas que la pantalla
// y la maquina ya no coinciden: relee del microcontrolador la altura real
// de la pluma, su sentido y las velocidades, en vez de confiar en lo que
// el pc tenia cacheado
export default function UtilitiesSection() {
  const { status, canOperate, runAction, reason } = useStatus()
  const [pingResult, setPingResult] = useState(null)
  const [showRaw, setShowRaw] = useState(false)
  const [raw, setRaw] = useState(null)

  const stats = status?.stats

  async function ping() {
    try {
      setPingResult(await runAction(api.ping))
    } catch {
      setPingResult(null)
    }
  }

  async function loadRaw() {
    try {
      setRaw(await api.getConfig())
      setShowRaw(true)
    } catch {
      /* es una utilidad de diagnostico, no hace falta avisar */
    }
  }

  return (
    <>
      <DisabledHint reason={reason('move')}>
        <div className="row">
          <Button
            variant="tinted"
            icon="resync"
            disabled={!canOperate}
            onClick={() => runAction(api.resync).catch(() => {})}
          >
            Volver a sincronizar
          </Button>
          <Button variant="gray" icon="plug" disabled={!canOperate} onClick={ping}>
            Probar comunicación
          </Button>
        </div>
      </DisabledHint>

      <Reveal when={pingResult}>
        {(r) => (
          <Banner tone={r.ok === false ? 'error' : 'success'}>
            {r.ok === false
              ? 'La máquina no contestó al ping.'
              : 'La máquina contestó correctamente.'}
          </Banner>
        )}
      </Reveal>

      <Reveal when={stats} className="result-box">
        {(s) => (
          <>
            <div className="result-box__row">
              <span className="result-box__label">Tramas enviadas</span>
              <span>{s.sent}</span>
            </div>
            <div className="result-box__row">
              <span className="result-box__label">Confirmadas / rechazadas</span>
              <span>
                {s.ack} / {s.nack}
              </span>
            </div>
            <div className="result-box__row">
              <span className="result-box__label">Sin respuesta / reintentos</span>
              <span>
                {s.timeout} / {s.retries}
              </span>
            </div>
          </>
        )}
      </Reveal>

      <hr className="divider" />

      <Button variant="plain" size="sm" onClick={showRaw ? () => setShowRaw(false) : loadRaw}>
        {showRaw ? 'Ocultar configuración guardada' : 'Ver configuración guardada'}
      </Button>
      <Reveal when={showRaw && raw}>
        {(r) => (
          <pre className="result-box" style={{ overflowX: 'auto', margin: 0 }}>
            {JSON.stringify(r, null, 2)}
          </pre>
        )}
      </Reveal>
    </>
  )
}
