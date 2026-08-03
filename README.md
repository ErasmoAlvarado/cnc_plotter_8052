# Mini CNC Plotter (AT89S52)

Plotter de escritorio que dibuja sobre papel con una pluma. El movimiento lo controla
un microcontrolador AT89S52 (familia 8051) programado en ensamblador, y desde la PC
se maneja con un backend en Python y una interfaz web hecha en React.

Lo armé como proyecto personal para entender de punta a punta cómo se controla hardware
real: desde los pulsos que mueven los motores paso a paso hasta la pantalla donde subís
un dibujo y le das play. Lo subo por si a alguien le sirve de referencia para algo parecido.

## Qué hace

- Dibuja archivos G-code (líneas y arcos) en un área de trabajo de 100x100 mm.
- Mueve 2 motores paso a paso para los ejes X/Y y uno más para subir/bajar la pluma (eje Z).
- Habla con el microcontrolador por serial (USB), con un protocolo binario propio.
- Tiene un wizard de calibración desde el navegador (pasos por mm, backlash, profundidad
  de la pluma) que no requiere tocar código.
- Jog manual, patrones de prueba, vista previa del dibujo antes de mandarlo a la máquina.
- Límites de software: la máquina no tiene finales de carrera físicos, así que el backend
  bloquea cualquier movimiento que se salga del área para no perder pasos.

## Cómo está armado

```
Navegador (React)  <-- HTTP / WebSocket -->  Backend (FastAPI)  <-- Serial 9600 baud -->  AT89S52
```

- **`8052_v2.asm`** — firmware del microcontrolador. Recibe tramas
  `[0xAA][CMD][PAYLOAD][CHECKSUM]` por UART y mueve los motores (interpolación tipo
  Bresenham para las líneas rectas en X/Y).
- **`python/`** — backend en FastAPI. Convierte el G-code en movimientos, habla el
  protocolo binario por el puerto serie, valida los límites del área y expone todo
  como API REST + WebSocket para el frontend.
- **`frontend/`** — interfaz web en React + Vite: conectar al puerto serie, calibrar,
  subir dibujos, mover la máquina a mano, ver el estado en vivo.

## Hardware usado

- Microcontrolador AT89S52 (8051) a 11.0592 MHz.
- 3 motores paso a paso 28BYJ-48 con drivers ULN2003 (X, Y, Z/pluma).
- Conversor USB-serial para hablarle al micro desde la PC.

Mapa de pines del firmware:

| Función      | Pines           |
|--------------|-----------------|
| Motor X      | P1.0 – P1.3     |
| Motor Y      | P2.0 – P2.3     |
| Motor Z / pluma | P2.4 – P2.7  |
| LED de estado | P3.5 (parpadea con cada trama válida, útil para depurar) |
| UART         | P3.0 RXD / P3.1 TXD |

El área de trabajo por defecto es 40x40 mm, se ajusta en `cnc_config.json` o desde la
calibración.

## Estructura del repo

```
cnc_plotter_8052/
├── 8052_v2.asm           firmware del AT89S52
├── cnc_config.json        configuración persistente (calibración, velocidades, límites)
├── dev.bat                levanta backend + frontend juntos (Windows)
├── python/                 backend FastAPI
│   ├── cnc_api.py           endpoints REST + WebSocket
│   ├── cnc_protocol.py      protocolo binario por serial
│   ├── cnc_plotter.py       lógica de alto nivel: recorre el G-code y llama al protocolo
│   ├── gcode_parse.py       parser de líneas G-code
│   ├── gcode_transform.py   espejo / ajuste del dibujo al área de trabajo
│   ├── gcode_walk.py        recorre el G-code y genera eventos de movimiento
│   ├── soft_limits.py       valida que un movimiento no se salga del área
│   ├── cnc_config.py        carga y guarda cnc_config.json
│   └── tests/                pruebas con pytest
└── frontend/                interfaz web (React + Vite)
    └── src/
```

## Poner esto a andar

### 1. Firmware

Compilá `8052_v2.asm` con cualquier ensamblador para 8051 (por ejemplo ASEM-51 o el que
traiga tu programador) y grabá el `.hex` en el AT89S52. Esto solo hay que hacerlo una vez,
salvo que cambies algo del firmware.

### 2. Backend (Python)

Necesitás Python 3.9 o más nuevo. Desde la carpeta `python/`:

```bash
pip install fastapi uvicorn pyserial pydantic
python cnc_api.py
```

Queda escuchando en `http://127.0.0.1:8000`.

### 3. Frontend (React)

Necesitás Node 18 o más nuevo. Desde la carpeta `frontend/`:

```bash
npm install
npm run dev
```

Queda en `http://localhost:5173` y habla con el backend en el puerto 8000.

### Atajo para Windows

`dev.bat` levanta el backend y el frontend juntos, cada uno en su propia ventana:

```bat
dev.bat
```

## Usar la interfaz

1. Abrí `http://localhost:5173`, elegí el puerto serie de la máquina y conectá.
2. La primera vez, corré el wizard de calibración (pasos/mm, backlash, profundidad de
   pluma). Queda guardado en `cnc_config.json`, no hay que repetirlo cada vez.
3. Subí un archivo `.gcode` (o probá uno de los patrones de prueba) y revisá la vista
   previa antes de mandarlo.
4. Dale play. Se puede pausar o abortar el trabajo en cualquier momento desde la UI.

También hay jog manual (mover los ejes con flechas) para posicionar la pluma o probar
que todo responda bien antes de dibujar algo largo.

## Tests

```bash
cd python
pytest
```

Cubren el recorrido/interpretación del G-code (`gcode_walk`), las transformaciones (espejo,
ajuste al área) y los límites de software.

## Notas / limitaciones

- Los movimientos relativos de X/Y no son idempotentes en el firmware, así que el
  backend limita los reintentos ahí. Los comandos de pluma sí son posición absoluta
  (idempotentes): repetirlos no hace daño.
- La máquina no tiene finales de carrera. La única protección contra salirse del área
  y perder pasos son los límites de software (`enforce_soft_limits` en la config) —
  no los desactives salvo que sepas lo que estás haciendo.
- Es un proyecto para aprender, no algo pensado para producción. El área de dibujo real
  es chica (40x40 mm por defecto).
