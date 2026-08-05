import { useState } from 'react'
import { api } from '../../api'
import { useStatus } from '../../StatusContext.jsx'
import Toggle from '../ui/Toggle.jsx'
import Banner from '../ui/Banner.jsx'
import ConfirmDialog from '../ui/ConfirmDialog.jsx'

// sentido fisico del porta-pluma.
//
// aparece en 2 lados (paso 3 del wizard y hoja avanzada) a proposito: es
// un ajuste tecnico pero tambien un paso de la calibracion de la pluma, y
// obligar a acordarse en cual de los 2 vive seria peor que repetirlo.
//
// si el firmware no lo soporta no dejamos un toggle apagado sin mas, un
// control disabled sin explicar se lee como que la app esta rota. mejor
// explicar que hace falta y por que
export default function PenHolderSection({ compact = false }) {
  const { status, canOperate, runAction, refreshConfig } = useStatus()
  const [pending, setPending] = useState(null)

  const supported = status?.pen_invert_supported
  const inverted = !!status?.pen_invert

  if (supported === false) {
    return (
      <Banner tone="warn" title="Este ajuste necesita actualizar la máquina">
        El firmware que tiene cargado el microcontrolador no sabe invertir el sentido del eje Z.
        Hay que reprogramarlo con la versión actual de <code>8052_v2.asm</code> (la que incluye
        C_ZDIR) para poder usarlo.
      </Banner>
    )
  }

  if (supported === null || supported === undefined) {
    return (
      <p className="hint">
        Conectá la máquina para saber si admite invertir el porta-pluma: hay que preguntárselo al
        microcontrolador.
      </p>
    )
  }

  async function applyInvert(value) {
    setPending(null)
    await runAction(() => api.penHolder(value)).catch(() => {})
    await refreshConfig()
  }

  return (
    <>
      <Toggle
        id="pen-invert"
        checked={inverted}
        disabled={!canOperate}
        onChange={(value) => setPending(value)}
        label="Porta-pluma montado al revés"
      />
      {!compact && (
        <p className="hint">
          Activalo si al pulsar «Subir» la pluma baja. La inversión la hace el firmware, así que
          «arriba» y «abajo» siguen significando lo mismo en los dos montajes.
        </p>
      )}

      <ConfirmDialog
        open={pending !== null}
        icon="pen-up"
        title={pending ? '¿Invertir el sentido del eje Z?' : '¿Volver al sentido normal?'}
        message="Antes de cambiarlo, la pluma se sube con el sentido actual para dejarla en una posición conocida. Después conviene comprobarlo con el ciclo de prueba."
        confirmLabel="Cambiar sentido"
        onConfirm={() => applyInvert(pending)}
        onCancel={() => setPending(null)}
      />
    </>
  )
}
