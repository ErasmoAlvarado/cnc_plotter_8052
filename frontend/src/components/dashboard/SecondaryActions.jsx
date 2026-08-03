import { useState } from 'react'
import { api } from '../../api'
import { useStatus } from '../../StatusContext.jsx'
import Button from '../ui/Button.jsx'
import Tooltip from '../ui/Tooltip.jsx'
import ConfirmDialog from '../ui/ConfirmDialog.jsx'

// Fila secundaria, separada de los botones de movimiento.
//
// Las etiquetas son cortas porque el rail es estrecho, pero ninguna se queda
// sin explicar: el tooltip dice la frase completa. Acortar sin tooltip seria
// cambiar claridad por espacio, y esta app la usa gente que no sabe lo que hace
// "Home".
//
// "Fijar origen" no mueve nada pero redefine el (0,0) de todo lo que venga
// despues, asi que pregunta antes: pulsarlo por error deja el dibujo desplazado
// sin ningun sintoma visible hasta que ya se dibujo encima.
export default function SecondaryActions({ disabled }) {
  const { runAction } = useStatus()
  const [confirmOrigin, setConfirmOrigin] = useState(false)

  return (
    <>
      <div className="secondary-row">
        <Tooltip label="Llevar la máquina al (0, 0)" side="top">
          <Button
            variant="secondary"
            size="sm"
            icon="house"
            disabled={disabled}
            onClick={() => runAction(api.home).catch(() => {})}
          >
            Ir al 0
          </Button>
        </Tooltip>

        <Tooltip label="Usar la posición actual como nuevo (0, 0)" side="top">
          <Button
            variant="secondary"
            size="sm"
            icon="scope"
            disabled={disabled}
            onClick={() => setConfirmOrigin(true)}
          >
            Fijar 0
          </Button>
        </Tooltip>

        <Tooltip label="Desenergizar los motores X e Y (Z sigue sujeta)" side="top">
          <Button
            variant="secondary"
            size="sm"
            icon="bolt-slash"
            disabled={disabled}
            onClick={() => runAction(api.motorsOff).catch(() => {})}
          >
            Motores
          </Button>
        </Tooltip>
      </div>

      <ConfirmDialog
        open={confirmOrigin}
        icon="scope"
        title="¿Fijar el origen aquí?"
        message="La posición actual pasa a ser el (0, 0) de la máquina. Todo lo que dibujes después se mide desde este punto."
        confirmLabel="Fijar origen"
        onConfirm={() => {
          setConfirmOrigin(false)
          runAction(api.setOrigin).catch(() => {})
        }}
        onCancel={() => setConfirmOrigin(false)}
      />
    </>
  )
}
