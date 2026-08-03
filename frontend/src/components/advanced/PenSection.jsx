import { useState } from 'react'
import { api } from '../../api'
import { useStatus } from '../../StatusContext.jsx'
import Button from '../ui/Button.jsx'
import Banner from '../ui/Banner.jsx'
import ConfirmDialog from '../ui/ConfirmDialog.jsx'
import DisabledHint from '../ui/DisabledHint.jsx'
import PenHolderSection from './PenHolderSection.jsx'
import PenTuner from '../pen/PenTuner.jsx'

// Ajustes del eje Z que no son parte del uso diario.
//
// Apagar Z esta aqui y no en el dashboard a proposito: es la unica accion de
// toda la app que puede estropear la calibracion sin que se note en pantalla
// —la pluma se cae sola por gravedad— asi que confirma antes y deja un aviso
// persistente en la cabecera hasta que se vuelve a fijar el cero.
export default function PenSection() {
  const { canOperate, runAction, setZEnergized, reason } = useStatus()
  const [confirmOff, setConfirmOff] = useState(false)

  async function turnOffZ() {
    setConfirmOff(false)
    await runAction(api.zOff).catch(() => {})
    setZEnergized(false)
  }

  return (
    <>
      <DisabledHint reason={reason('move')}>
        <h3 className="section-title">Sentido del porta-pluma</h3>
        <PenHolderSection />

        <hr className="divider" />

        {/* El mismo control que abre el rail y que monta el paso 3 del
            asistente. Esta aqui porque es donde se busca "todo lo de la
            pluma", no porque sea un ajuste distinto. */}
        <h3 className="section-title">Altura y presión</h3>
        <PenTuner />

        <hr className="divider" />

        <h3 className="section-title">Energía del eje Z</h3>
        <p className="hint">
          Las bobinas del eje Z quedan energizadas para sostener la pluma. Apagarlas evita que el
          motor se caliente en pausas largas, pero la pluma baja sola.
        </p>
        <div>
          <Button variant="destructive-tinted" icon="bolt-slash" disabled={!canOperate} onClick={() => setConfirmOff(true)}>
            Apagar el eje Z
          </Button>
        </div>

        <Banner tone="info">
          «Motores» del panel de posición apaga sólo X e Y. El eje Z se apaga por separado
          justamente porque tiene esta consecuencia.
        </Banner>
      </DisabledHint>

      <ConfirmDialog
        open={confirmOff}
        destructive
        icon="bolt-slash"
        title="¿Apagar el eje Z?"
        message="La pluma va a bajar sola por su propio peso. Después vas a tener que recolocarla y volver a fijar el cero antes de dibujar."
        confirmLabel="Apagar el eje Z"
        onConfirm={turnOffZ}
        onCancel={() => setConfirmOff(false)}
      />
    </>
  )
}
