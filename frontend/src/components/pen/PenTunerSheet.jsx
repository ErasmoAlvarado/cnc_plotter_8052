import { useStatus } from '../../StatusContext.jsx'
import Sheet from '../ui/Sheet.jsx'
import Banner from '../ui/Banner.jsx'
import Button from '../ui/Button.jsx'
import PenTuner from './PenTuner.jsx'

// el ajuste fino de la pluma como su propia hoja.
//
// se abre desde el rail y desde ajustes avanzados, el paso 3 del wizard
// monta el mismo PenTuner incrustado. un solo control con 3 puertas, igual
// que PenHolderSection -- obligar a acordarse en cual de los 3 vive el
// ajuste seria peor que repetir la puerta
export default function PenTunerSheet({ open, onClose }) {
  const { connected, canOperate } = useStatus()

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title="Ajuste fino de la pluma"
      description="Buscá la presión con la que el trazo sale marcado sin hundir la punta en el papel."
      footer={
        <Button variant="filled" size="lg" block onClick={onClose}>
          Listo
        </Button>
      }
    >
      {!connected && (
        <Banner tone="warn" title="La máquina no está conectada">
          Ajustar la pluma requiere moverla de verdad. Conectá la máquina para continuar.
        </Banner>
      )}
      {connected && !canOperate && (
        <Banner tone="warn">Esperá a que termine el trabajo en curso.</Banner>
      )}
      <PenTuner />
    </Sheet>
  )
}
