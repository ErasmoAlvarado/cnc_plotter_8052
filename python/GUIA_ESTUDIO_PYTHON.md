# Guía de estudio — la parte en Python del CNC Plotter

Este documento explica **todo** lo que hace el software en Python del proyecto: los ocho
archivos de `python/`, cómo se conectan entre sí, y por qué cada decisión de diseño es como es.
Está escrito para que, ante cualquier pregunta sobre esta parte del sistema, la respuesta ya esté
aquí — con el argumento, el número concreto y el archivo donde comprobarlo.

No hace falta memorizar código de memoria. Hace falta entender **la idea detrás de cada
archivo** y poder seguir el hilo de "si pasa esto, entonces el sistema hace aquello". Por eso
cada sección tiene: qué problema resuelve, cómo lo resuelve, un ejemplo con números reales, y
las preguntas que un tribunal haría sobre ese punto exacto.

> Existe un documento hermano, `presentacion/05-PREGUNTAS-PROFESOR.md`, centrado en hardware y
> firmware. Esta guía cubre la otra mitad: el software que corre en la computadora.

---

## 1. El panorama completo en 90 segundos

El software en Python tiene **una sola tarea**: tomar un archivo de G-code (o una orden de la
interfaz) y convertirla en una secuencia de bytes que un microcontrolador AT89S52 entienda,
respetando el área física de la máquina y sin perder nunca la posición real del cabezal.

```
 archivo .gcode (texto)
        │
        ▼
 gcode_parse.py       — convierte cada línea de texto en {letra: número}, y descompone arcos
        │                (G2/G3) en una lista de puntos rectos
        ▼
 gcode_transform.py   — aplica, si el usuario lo pidió, un espejo en Y y/o un escalado para
        │                ajustar el dibujo al área (una transformación afín congelada)
        ▼
 gcode_walk.py         — EL intérprete: recorre las líneas y genera eventos ya resueltos
        │                (moverse a X,Y; bajar/subir pluma; esperar N segundos)
        ▼
 soft_limits.py        — antes de mover nada, comprueba si esos eventos caben en el área física
        │
        ▼
 cnc_plotter.py        — traduce cada evento en movimiento real: milímetros → pasos de motor,
        │                Bresenham para las diagonales, caché de velocidad y de pluma
        ▼
 cnc_protocol.py        — arma las tramas binarias, las manda por el puerto serie, espera ACK,
        │                 reintenta lo que se puede reintentar sin peligro
        ▼
 UART 9600 baudios  →  AT89S52 (firmware, fuera del alcance de esta guía)
```

`cnc_config.py` no está en esta cadena: vive al lado, y es quien guarda en disco (`cnc_config.json`)
todos los números que los demás archivos necesitan (pasos por milímetro, velocidades, área útil...).

`cnc_api.py` tampoco es un eslabón más: es una **capa por encima de todo lo anterior**. Envuelve
`CNCPlotter` y `CNCProtocol` en una API web (FastAPI) para que el frontend en React pueda
conectarse, subir un G-code, ver una vista previa, y lanzar el trabajo — todo sin usar la
terminal.

| Archivo | Una frase |
|---|---|
| `cnc_config.py` | Lee y escribe `cnc_config.json` de forma seguros: valores por defecto, rangos válidos, escritura atómica. |
| `gcode_parse.py` | El léxico: texto de G-code → diccionario de parámetros. También descompone arcos en segmentos rectos. |
| `gcode_transform.py` | Una transformación afín (espejo Y + escala + traslación) que se aplica a la geometría ya resuelta. |
| `gcode_walk.py` | El único intérprete de G-code del proyecto. Convierte líneas en eventos: `MoveEvent`, `ArcEvent`, `PenEvent`, `DwellEvent`. |
| `soft_limits.py` | Compara una coordenada o una caja delimitadora contra el área útil de la máquina. |
| `cnc_plotter.py` | El cerebro: convierte eventos en movimiento real (mm → pasos, Bresenham, caché de pluma/velocidad). |
| `cnc_protocol.py` | La capa de comunicación: arma tramas binarias, habla por el puerto serie, reintenta con criterio. |
| `cnc_api.py` | La API web (FastAPI): expone todo lo anterior como endpoints HTTP y un WebSocket de progreso. |

---

## 2. Los seis conceptos que sostienen todo lo demás

Antes de entrar módulo por módulo, conviene tener clarísimas estas seis ideas. Casi cualquier
pregunta difícil del tribunal es, en el fondo, una variación de una de ellas.

### 2.1 Tres lenguajes de coordenadas, y quién habla cada uno

El sistema nunca confunde estas tres representaciones de "dónde está o adónde va la pluma":

1. **Milímetros** — el lenguaje del G-code y del usuario. Números de punto flotante.
2. **Pasos de motor** — el lenguaje de la máquina real. Números enteros, siempre positivos
   (nunca hay pasos negativos: el espacio de trabajo vive en `[0, max]`).
3. **Eventos** (`MoveEvent`, `ArcEvent`, `PenEvent`, `DwellEvent`) — el lenguaje intermedio que
   produce `gcode_walk.py`: geometría ya resuelta en milímetros absolutos, con la transformación
   ya aplicada, sin nada de estado modal (`G90`/`G91`) ni relatividad.

La conversión milímetros → pasos ocurre en un único lugar: `CNCPlotter.mm_to_steps_x/_y`
(`cnc_plotter.py:204-208`), y **siempre** convierte la coordenada absoluta de destino, nunca un
delta acumulado. Esto es una decisión de precisión, no de estilo:

```
steps_per_mm = 170.67 (valor por defecto)
G1 X0.3  →  round(0.3 * 170.67) = 51
G1 X0.6  →  round(0.6 * 170.67) = 102   (avanza 51)
G1 X0.9  →  round(0.9 * 170.67) = 154   (avanza 52)  ← hace falta este paso de más
G1 X1.2  →  round(1.2 * 170.67) = 205   (avanza 51)
```

Si en cambio se convirtiera el delta de 0.3 mm cuatro veces por separado, cada conversión
redondearía a 51 pasos y el total sería 204 en vez de 205: un paso perdido por acumulación de
redondeo. Convertir siempre la posición absoluta hace que el error de redondeo nunca se acumule
más allá de medio paso.

> **Pregunta típica:** *¿por qué no simplemente sumar los pasos de cada movimiento relativo?*
> Porque el redondeo de cada segmento se acumula. Convirtiendo siempre la coordenada absoluta,
> el error máximo total es de medio paso (unas 3 micras), sin importar cuántos segmentos tenga
> el dibujo.

### 2.2 Z es absoluto, X/Y son relativos — y por qué eso no es arbitrario

Esta es la decisión de diseño más importante de todo el proyecto (marcada en el código como
`[SW-1]`).

- **La pluma (eje Z)** se mueve con comandos absolutos: "sube a la posición 0" (`CMD_PEN_UP`) o
  "baja a la posición `PEN_N`" (`CMD_PEN_DOWN`). El firmware calcula el recorrido real. Repetir
  el comando, o reintentarlo porque se perdió la confirmación, **no hace daño**: si ya estaba
  arriba, "subir" no mueve nada. Es **idempotente**.
- **Los motores X/Y** se mueven con comandos relativos: "da 50 pasos hacia la derecha". Si se
  pierde la confirmación (ACK) y el comando se reintenta, el motor **se mueve otra vez**, y ahora
  la posición cacheada en la computadora ya no coincide con la posición real. No es idempotente.

Esa asimetría explica una regla muy concreta del código: `CNCProtocol.send_command` usa
`retries=1` para los movimientos de X/Y/Z relativos y `retries=3` para pluma arriba/abajo
(`cnc_protocol.py:544-559`). No es un descuido — es la única política de reintento coherente con
la física de cada comando.

`pen_down_flag` tampoco es una variable independiente: es una **propiedad derivada**
(`cnc_protocol.py:161-166`):

```python
@property
def pen_down_flag(self):
    return self.pos_z >= max(1, self.pen_steps)
```

Antes de esta versión existían dos fuentes de verdad sobre si la pluma estaba arriba o abajo (un
booleano cacheado y la posición real de Z), y podían discrepar: el sistema decía "pluma abajo"
mientras el papel seguía en blanco. Al derivar el estado siempre de `pos_z`, solo puede haber una
verdad, y esa verdad se puede **releer del microcontrolador en cualquier momento** con
`get_state()` — nunca hay que confiar ciegamente en lo que el software cree recordar.

> **Pregunta típica:** *¿qué pasa si se pierde el ACK de un movimiento de pluma?* Nada grave: se
> reintenta hasta 3 veces porque volver a pedir "sube a 0" cuando ya está en 0 no mueve nada.
>
> **Pregunta típica:** *¿y si se pierde el ACK de un paso de X?* Ahí NO se reintenta más que una
> vez, porque reintentar movería el eje una segunda vez y desincronizaría la posición cacheada de
> la real — ese es justamente el motivo de que XY sea de un solo intento con temporizador amplio,
> en vez de "reintentar hasta que funcione".

### 2.3 Un solo intérprete de G-code — la lección del bug de los tres caminos

Antes de la reescritura, había **tres** trozos de código que leían G-code por separado: el que
ejecutaba de verdad, el que calculaba la caja delimitadora para los límites, y el que generaba la
vista previa del frontend. Con el tiempo divergieron: la vista previa y los límites no
contemplaban el viaje de vuelta al origen que hacen `G28`/`M2`/`M30`, y la vista previa ignoraba
el estado de la pluma que deja un `G0`.

La consecuencia era grave: el límite blando —lo único que evita que el carro choque contra el
tope mecánico— estaba validando una geometría **que no era la que realmente se iba a dibujar**.
Un archivo podía pasar la validación y aun así estrellarse.

La solución fue `gcode_walk.walk()` (`gcode_walk.py:83`): un único generador que recorre las
líneas y produce eventos con la geometría ya resuelta. Los tres consumidores —ejecución
(`CNCPlotter.exec_event`), límites (`bounds_of`) y vista previa (`cnc_api._gcode_payload`)—
consumen exactamente la misma secuencia de eventos. Por construcción, ya no pueden ver cosas
distintas.

Hay un test que existe únicamente para vigilar que esto no vuelva a romperse:
`test_lo_que_se_ejecuta_es_lo_que_se_valida` (`python/tests/test_gcode_walk.py:150`). Ejecuta un
G-code contra un `CNCPlotter` simulado, anota cada coordenada por la que pasa de verdad, y
comprueba que coincide con lo que calcula `bounds_of()` sobre el mismo archivo. Si alguien
reintrodujera un cuarto camino de lectura de G-code, ese test fallaría.

> **Pregunta típica:** *¿cómo se garantiza que la vista previa que ve el usuario es fiel a lo que
> se va a dibujar?* Porque no hay dos lecturas del archivo: la vista previa y la ejecución llaman
> a la misma función `walk()` con los mismos parámetros de la máquina (umbral de pluma,
> tolerancia de cuerda). La única diferencia permitida y explícita es el estado inicial de la
> pluma (`initial_pen_down`): la ejecución pasa el estado real de la máquina; la vista previa y
> los límites pasan `False`, porque describen el archivo en abstracto, no el instante actual.

### 2.4 Límites blandos: bloquean, no avisan

La máquina **no tiene finales de carrera** (sensores de fin de carrera). Si un movimiento la
lleva más allá del área física, el motor sigue intentando girar contra un tope mecánico, se
pierden pasos silenciosamente, y la posición que la computadora cree tener deja de coincidir con
la real. Recuperarse de eso implica volver a calibrar con una regla.

Por eso, `soft_limits.py` no es un sistema de avisos: es un bloqueo con dos niveles.

1. **Preventivo** (`check_bounds`): antes de mover un solo paso, se calcula la caja delimitadora
   de *todo* el trabajo (con `bounds_of`, que usa el mismo intérprete de la sección anterior) y se
   compara contra el área. Si no cabe, se rechaza con un mensaje accionable — cuánto mide el
   dibujo, cuánto mide el área, cuánto se pasa — y no sale ni un byte por el puerto serie.
2. **Última red** (`check_point`, usado en `CNCPlotter._check_area`): se comprueba cada punto
   justo antes de moverse. Si el paso preventivo funcionó, esto no debería dispararse nunca —
   salvo que alguien haya movido el origen a mano entre medias, que es precisamente el caso que
   el paso preventivo no puede prever.

Ambos usan una tolerancia de 0.5 mm (`TOLERANCE_MM`) porque el redondeo mm→pasos y el último
punto de un arco pueden quedar unas décimas fuera sin que eso signifique nada mecánicamente.

> **Pregunta típica:** *¿por qué dos comprobaciones y no solo una?* Porque cada una cubre un
> fallo distinto. La preventiva es la que de verdad protege (evita mover nada), pero solo conoce
> el archivo tal como es al empezar. La de último recurso cubre el caso en que la máquina se
> desincroniza *durante* el trabajo (alguien tocó el jog manual entre medias).

### 2.5 El protocolo binario y por qué cada byte importa

`cnc_protocol.py` habla con el microcontrolador con una trama fija:

```
[0xAA][CMD][PAYLOAD][CHK]  →  el firmware responde 0x06 (ACK) o 0x15 (NACK)
CHK = HEADER ^ CMD ^ PAYLOAD   (XOR de todos los bytes anteriores)
```

Y una trama extendida solo para `CMD_LINE` (0x08), que manda una línea diagonal entera en un solo
viaje de ida y vuelta en vez de un mensaje por paso:

```
[0xAA][0x08][DX][DY][FLAGS][CHK]
```

`DX`/`DY` son magnitudes sin signo, acotadas a 255 (un byte), y `FLAGS` lleva el signo de cada
eje en un bit. El firmware ejecuta el algoritmo de Bresenham él mismo con esos dos valores. Si la
línea real mide más de 255 pasos en el eje mayor, `CNCPlotter._draw_line_chunked` la reparte en
varios segmentos, usando un acumulador entero para que la suma de los trozos dé exactamente la
longitud original sin desviarse (ver §4.6).

Los valores de comando concretos (`CMD_Z_POS = 0x0A`, no `0x05` o `0x06`) están elegidos a
propósito para no coincidir nunca con `0xAA` (cabecera), `0x06` (ACK) o `0x15` (NACK). Antes de
esta versión, el comando de bajar Z valía `0x06` — el mismo valor que la confirmación — y el
firmware podía confundir una cosa con otra.

> **Pregunta típica:** *¿qué pasa si se corrompe un byte a mitad de una trama?* El firmware
> espera cada byte con un tiempo máximo; si se agota, descarta la trama entera y vuelve a buscar
> el siguiente `0xAA`. Del lado de Python, `send_command` calcula su propio tiempo de espera
> dinámico según el comando y el tamaño del payload (`cnc_protocol.py:349-359`), para no disparar
> reintentos por un simple movimiento largo que tarda más en ejecutarse.

### 2.6 Concurrencia: un cerrojo para el puerto, otro para "¿hay trabajo en curso?"

El puerto serie es un recurso compartido: la interfaz web puede pedir un jog manual mientras, en
teoría, un hilo en segundo plano está dibujando un G-code completo. Sin cuidado, los bytes de dos
tramas distintas se entremezclarían en el cable.

Hay **dos candados**, cada uno resolviendo un problema distinto:

1. `CNCProtocol._lock` (un `threading.RLock`): protege *cada* acceso al puerto serie. Todo
   método que escribe o lee de `self.ser` lo toma. Esto evita que dos tramas se intercalen
   byte a byte.
2. `job_lock` en `cnc_api.py`: protege la decisión de "¿puedo empezar un trabajo nuevo?".
   `_claim_job()` (`cnc_api.py:167-181`) toma este candado, comprueba `job_state["active"]`, y si
   está libre lo marca **como ocupado antes de devolver el control** — todo de forma atómica.

El segundo candado existe porque `_require_idle()` sola no basta: hay una ventana de tiempo entre
"comprobar que no hay trabajo" y "arrancar el hilo que hace el trabajo", y dos peticiones
`/api/run` simultáneas podían pasar las dos esa comprobación antes de que la primera llegara a
marcar el estado como ocupado. Con `_claim_job()`, la comprobación y la reserva son una sola
operación atómica bajo el mismo candado.

> **Pregunta típica:** *¿por qué no basta con comprobar `job_state["active"]` al principio del
> endpoint?* Porque entre esa comprobación y el arranque real del hilo hay una ventana de tiempo
> en la que una segunda petición ve exactamente el mismo estado "libre". Se necesita que
> "comprobar" y "reservar" ocurran como una sola operación indivisible, protegida por un candado.

---

## 3. Módulo por módulo

### 3.1 `cnc_config.py` — la configuración persistente

**Qué hace:** lee y escribe `cnc_config.json` (en la raíz del repositorio, un nivel por encima de
`python/`). Es el único archivo del proyecto que sabe leer o escribir ese JSON.

**Valores importantes de `DEFAULT_CONFIG`:**

| Clave | Valor por defecto | Significado |
|---|---|---|
| `steps_per_mm_x` / `_y` | 170.67 | 4096 pasos por vuelta del motor ÷ 24 mm de circunferencia de la polea |
| `steps_per_mm_z` | 100.0 | El mecanismo de Z casi nunca comparte escala con X/Y |
| `speed_draw` / `speed_rapid` / `speed_z` | 5 / 6 / 8 | Milisegundos entre medios pasos (a más número, más lento) |
| `max_x_mm` / `max_y_mm` | 40.0 | Área útil por defecto |
| `pen_steps` | 100 | Profundidad de Z entre "arriba" y "abajo" |
| `z_pen_down_threshold` | 0.0 | En el G-code, `Z <= umbral` significa pluma abajo |
| `pen_invert` | `False` | Sentido físico del eje Z según cómo quedó montado el portapluma |
| `invert_x` / `invert_y` | `False` / `True` | Perspectiva del usuario (no cambia la cinemática, ver §4 de `CLAUDE.md`) |
| `enforce_soft_limits` | `True` | Si los límites bloquean el trabajo o no |

La máquina real de este proyecto, sin embargo, tiene otros valores guardados en
`cnc_config.json` tras calibrarla con una regla: `steps_per_mm_x = 79.0`,
`steps_per_mm_y = 82.76` (X e Y son mecanismos distintos, con escalas distintas —
ver §4.6), `max_x_mm = max_y_mm = 100.0`, `pen_steps = 153`, `pen_invert = true`. Esa es la
diferencia entre el valor **teórico** de fábrica (170.67, calculado de la geometría del motor) y
el valor **medido** después de calibrar (79.0 / 82.76): el mecanismo real nunca es exactamente el
ideal en el papel.

**Funciones clave:**

- **`_to_bool(val, default)`** (`cnc_config.py:114`): un booleano de Python no sirve para leer
  JSON escrito a mano, porque `bool("false")` es `True` (una cadena no vacía siempre es "verdadera"
  en Python). Esta función interpreta explícitamente cadenas como `"true"`/`"false"`/`"si"`/`"no"`
  antes de convertir. Sin esto, alguien editando el JSON a mano con `"pen_invert": "false"` habría
  invertido el sentido del eje Z exactamente al revés de lo que pedía.
- **`_validate(cfg)`** (`cnc_config.py:131`): recorre `DEFAULT_CONFIG`, y para cada clave conocida
  fuerza el tipo correcto y la recorta a un rango válido (`_RANGES`). Un valor corrupto o fuera de
  rango vuelve a su valor por defecto en vez de propagarse hasta el firmware.
- **`load_config()`** (`cnc_config.py:155`): si el archivo no existe, lo crea con los valores por
  defecto. Si existe pero está corrupto (JSON inválido), **no lo descarta en silencio**: guarda el
  motivo del error en `last_error` y renombra el archivo a `cnc_config.json.corrupto`, para poder
  recuperar los valores a mano después.
- **`save_config(config)`** (`cnc_config.py:181`): fusiona lo nuevo sobre lo que ya había en disco
  (no sobrescribe todo el archivo con solo las claves que cambiaron) y escribe de forma **atómica**:
  escribe primero a un archivo temporal, hace `fsync` para forzar la escritura física, y solo
  entonces usa `os.replace()` para sustituir el archivo real. Esto garantiza que un corte de luz o
  un cierre abrupto a mitad de la escritura nunca deje un JSON truncado — o se ve el archivo viejo
  completo, o se ve el nuevo completo, nunca una mezcla.

> **Pregunta típica:** *¿qué pasa si `cnc_config.json` se corrompe mientras la máquina está
> conectada?* Nada catastrófico: `load_config()` detecta que no es JSON válido, guarda una copia
> con extensión `.corrupto` para poder inspeccionarla, y el sistema sigue funcionando con los
> valores por defecto de fábrica.
>
> **Pregunta típica:** *¿por qué escritura atómica y no simplemente `json.dump` sobre el archivo?*
> Porque escribir "in situ" dejaría el archivo a medio escribir si el proceso se interrumpe en ese
> instante exacto (cierre del programa, corte eléctrico). `os.replace()` es una operación atómica
> del sistema de archivos: nunca deja un estado intermedio visible.

### 3.2 `gcode_parse.py` — el léxico y la geometría de los arcos

**Qué hace:** dos responsabilidades muy separadas que viven juntas por necesidad técnica
(evitar una importación circular entre `cnc_plotter.py` y `gcode_walk.py`).

**`parse_gcode_line(line)`** (`gcode_parse.py:23`): convierte una línea de texto de G-code en un
diccionario `{letra: número}`. Antes de tokenizar, elimina comentarios entre paréntesis, comentarios
con `;`, y líneas de delimitador de programa (`%`). El patrón de expresión regular
(`_GCODE_TOKEN`) acepta números con signo, decimales y notación científica: `X10`, `X-10`,
`X+10`, `X.5`, `X1.5e2` son todos válidos. Si la línea queda vacía tras limpiar comentarios,
devuelve `None`.

```python
parse_gcode_line("G1 X10.5 Y-3 ; ir al punto")
# → {"G": 1.0, "X": 10.5, "Y": -3.0}
```

**`arc_to_segments(x0, y0, x1, y1, i, j, clockwise, chord_tol=0.005)`**
(`gcode_parse.py:43`): convierte un arco `G2`/`G3` en una lista de puntos rectos. Es geometría
pura; conviene entenderla paso a paso:

1. El centro del arco es el punto de inicio más el desplazamiento `(i, j)`: `cx = x0+i`,
   `cy = y0+j`. El radio es `r = hypot(i, j)` (distancia del inicio al centro).
2. **Validación de coherencia** (`[SW-47]`): en un arco válido, el punto final debe estar a la
   misma distancia del centro que el inicio. Si el G-code trae valores de `I`/`J` erróneos (un
   post-procesador roto, o un `G2` que heredó el `I`/`J` de la línea anterior), el arco no cierra
   correctamente. En vez de dibujar una espiral que no llega a ningún sitio con sentido, la
   función cae a una línea recta hasta el destino.
3. Se calculan los ángulos de inicio y fin con `atan2`, y el **barrido angular** (`sweep`) según
   el sentido (horario/antihorario). Si el barrido sale negativo o casi cero, se le suma una
   vuelta completa (2π) — esto cubre el caso de un arco que da toda la vuelta.
4. **Segmentación adaptativa**: el número de segmentos no es fijo. Se calcula a partir de la
   tolerancia de cuerda (`chord_tol`, el error máximo permitido entre la cuerda recta y el arco
   real), con la fórmula `error_cuerda = r * (1 - cos(θ/2))`. Un radio grande necesita más
   segmentos para el mismo error que uno pequeño; un `chord_tol` más fino (más exigente) también
   pide más segmentos. Hay un mínimo de 8 y un techo de seguridad de 2000.
5. El último punto se fuerza a ser exactamente `(x1, y1)`, para cerrar sin arrastrar error de
   coma flotante acumulado por el barrido angular.

> **Pregunta típica:** *¿por qué la cantidad de segmentos de un arco no es fija?* Porque un
> círculo pequeño necesita pocos segmentos rectos para verse suave, y uno grande necesita muchos
> más para el mismo error visual. La fórmula deriva el número exacto de segmentos necesarios para
> no superar un error de cuerda dado, en vez de adivinar un número fijo que sería demasiado para
> arcos pequeños y demasiado poco para arcos grandes.
>
> **Pregunta típica:** *¿qué tolerancia de cuerda usa este proyecto?* `CNCPlotter.chord_tol`
> (`cnc_plotter.py:343-347`) devuelve `min(1/steps_per_mm_x, 1/steps_per_mm_y)`: el error máximo
> permitido es de **un solo paso de motor**. Afinar más no tiene sentido porque la máquina no
> puede imprimir con más resolución que eso, y solo multiplicaría el número de segmentos sin
> ninguna mejora visible.

### 3.3 `gcode_transform.py` — espejo y ajuste al área

**Qué hace:** aplica, sobre la geometría ya resuelta (en milímetros), una transformación afín
opcional: espejo en Y y/o escalado con centrado. Existe para dos funciones de la interfaz sobre
un archivo **ya cargado**, sin reescribirlo ni volver a subirlo:

- **"Voltear Y"**: el G-code estándar asume que Y crece hacia arriba, con el origen abajo a la
  izquierda. Esta máquina tiene el origen arriba a la izquierda, así que un archivo salido de un
  programa CAM genérico se dibuja al revés si no se corrige.
- **"Ajustar al área"**: si el dibujo no cabe, en vez de bloquear el trabajo se ofrece escalarlo
  (nunca agrandarlo) y centrarlo dentro de los límites.

**`Bounds`** y **`GcodeTransform`** son ambos `@dataclass(frozen=True)` — **inmutables**. Cada
vez que hace falta una caja delimitadora o una transformación distinta, se crea una instancia
nueva; nunca se modifica una existente. Esto es consistente con la idea de que la geometría, una
vez calculada, no cambia bajo los pies de quien la está usando.

`GcodeTransform.apply(x, y)` (`gcode_transform.py:76`) aplica, en este orden fijo:

```python
if self.flip_y:
    y = self.flip_axis - y
return (x * self.scale + self.offset_x,
        y * self.scale + self.offset_y)
```

Ese orden — primero espejo, después escala, después traslación — es lo que permite componer
"voltear" y "ajustar al área" en una sola instancia, que es justo lo que hace falta cuando el
usuario marca ambas casillas a la vez.

**Por qué el espejo es seguro aquí y sería peligroso reescribiendo el texto del G-code:** el error
clásico al voltear Y es olvidar que un arco también cambia: `G2` (horario) pasa a ser `G3`
(antihorario), y el signo de `J` se invierte. Quien reescribe texto de G-code tiene que acordarse
de las tres cosas a la vez, y si falla una, el arco sale como un reflejo cóncavo sin que nadie lo
note hasta ver el papel dibujado. Aquí eso no puede pasar, porque `gcode_walk.walk()` **primero**
descompone el arco en puntos rectos (`arc_to_segments`) y **después** pasa cada punto por
`transform.apply()`. Espejar una polilínea de puntos no tiene casos especiales; por eso este
módulo ni siquiera necesita saber que existen los arcos.

**`flip_y_about(bounds)`** (`gcode_transform.py:96`): espeja alrededor del centro de la **propia**
caja del dibujo, no de `max_y_mm`. Esto es deliberado: así el dibujo se queda exactamente donde
estaba (no se desplaza fuera del área por voltear), y la caja delimitadora resultante es idéntica
a la original — lo que permite calcular el ajuste al área sin que importe si hay espejo activo o
no.

**`fit_to_area(bounds, max_x, max_y, margin_mm=1.0, base=IDENTITY)`**
(`gcode_transform.py:107`): calcula una escala que **solo encoge, nunca amplía**
(`scale = min(scale_x, scale_y, 1.0)`) y centra el resultado dentro del área útil menos el
margen. El parámetro `base` permite conservar un espejo ya activo, porque como el espejo no
cambia la caja delimitadora, el cálculo de escala/centrado sale idéntico con o sin espejo.

**`build(bounds, max_x, max_y, flip_y, fit, margin_mm=1.0)`** (`gcode_transform.py:135`): el
único punto de construcción que usa la API. Siempre parte de la caja **original** del archivo, no
de una transformación previa encadenada — si se encadenara, pulsar "Ajustar al área" dos veces
encogería el dibujo dos veces.

> **Pregunta típica:** *¿por qué no simplemente reescribir el archivo de G-code al aplicar el
> espejo?* Porque reescribir obliga a acordarse de invertir `G2`↔`G3` y el signo de `J` en cada
> arco, y un solo descuido produce un arco con la curvatura al revés sin ningún error visible
> hasta imprimir. Aplicar la transformación **después** de descomponer el arco en puntos elimina
> ese caso especial por completo.
>
> **Pregunta típica:** *¿por qué "ajustar al área" siempre parte de la caja original?* Porque si
> partiera de la transformación anterior, aplicar el ajuste dos veces seguidas encogería el
> dibujo dos veces en vez de dejarlo igual la segunda vez.

### 3.4 `gcode_walk.py` — el intérprete único

Ya se explicó el porqué en el §2.3. Aquí va el cómo, con detalle de línea.

**Los cuatro eventos** (todos `@dataclass(frozen=True)`, todos con un campo `line` que es el
índice de la línea del archivo que los originó):

- `PenEvent(line, down)` — cambio explícito de pluma.
- `MoveEvent(line, x, y, draw)` — movimiento recto hasta `(x, y)` absolutos en mm, ya
  transformados; `draw` dice si es con la pluma abajo.
- `ArcEvent(line, points, draw)` — un arco entero ya descompuesto en una tupla de puntos. Se
  emite completo, no punto por punto, para que quien ejecuta pueda fijar la velocidad **una sola
  vez** por arco en vez de una vez por segmento (`[SW-19]`) — un círculo entero podía mandar
  cientos de tramas de velocidad idénticas si no fuera así.
- `DwellEvent(line, seconds)` — pausa, acotada a un máximo de 5 segundos.

**El generador `walk(lines, z_pen_down_threshold, chord_tol, transform, initial_pen_down)`**
(`gcode_walk.py:83`) mantiene un estado interno mínimo mientras recorre línea por línea:
`abs_mode` (¿`G90` o `G91`?), `gx`/`gy` (posición del intérprete, **sin transformar**) y
`pen_down`.

Reglas de orden que hay que saber explicar con seguridad:

- **`M3`/`M4`/`M5` se aplican ANTES del movimiento de su propia línea** (`[SW-42]`): si una línea
  trae `M3 G1 X10`, la pluma baja *antes* de que se emita el movimiento, así que ese movimiento
  ya se marca como `draw=True`. El estado de pluma de una línea manda sobre el trazo de esa misma
  línea.
- **En `G0` (rápido), el viaje va primero y la Z de esa misma línea se aplica después**
  (`[SW-40]`): si la línea es `G0 X10 Y10 Z-1`, primero se emite el `MoveEvent` con `draw=False`
  (un rápido nunca dibuja) y solo entonces se interpreta la `Z-1` como orden de bajar la pluma.
  Sin este orden, el código anterior bajaba la pluma primero y el `rapid_to()` la volvía a subir
  inmediatamente después — la pluma daba un golpe físico contra el papel en cada rápido de ese
  estilo. Y un `G0 Z-1` *sin* `X`/`Y` no genera ningún `MoveEvent`: es solo una orden de pluma, no
  un viaje.
- **`G1` y los arcos (`G2`/`G3`) aplican la Z primero y luego respetan el estado de pluma
  resultante** para decidir si el trazo dibuja o no (`[SW-41]`). Antes, cualquier arco dibujaba
  sin importar si la pluma estaba arriba, ignorando lo que pedía el propio archivo.
- **`G28` (home) y `M2`/`M30` (fin de programa) viajan de vuelta al origen como un rápido normal**,
  y ese viaje se emite como un `MoveEvent` que sí cuenta para la caja delimitadora. Los
  intérpretes anteriores se saltaban ese viaje al calcular límites o vista previa, pero el carro
  lo hace de verdad y puede chocar contra el tope sin que nada lo hubiera detectado.
- **El estado interno (`gx`, `gy`) se lleva SIN transformar.** Los movimientos relativos de `G91`
  y los offsets `I`/`J` de los arcos son relativos a la coordenada original del archivo, no a la
  transformada. La transformación (espejo/escala) se aplica solo al emitir el evento, con
  `t.apply(x, y)`. Si se transformara el estado acumulado, cada línea en modo relativo arrastraría
  la escala otra vez y el resultado saldría mal.

**`_apply_z(params, idx, pen_down, threshold)`** (`gcode_walk.py:192`): traduce la `Z` del G-code
a arriba/abajo con un umbral configurable (`z <= threshold` ⇒ pluma abajo), no con un `z < 0`
fijo (`[SW-11]`). Muchos post-procesadores generan `Z0`/`Z5` en vez de valores negativos; con la
regla vieja, el dibujo salía completamente en blanco porque nunca se cumplía `z < 0`.

**`bounds_of(lines, ...)`** (`gcode_walk.py:207`): recorre el mismo `walk()` y va acumulando el
mínimo y máximo de X e Y sobre **todos** los puntos de `MoveEvent` y `ArcEvent` — incluidos los
rápidos, porque el carro viaja igual y puede chocar aunque no esté dibujando.

> **Pregunta típica:** *si un archivo repite la misma `Z` en cada línea, ¿se manda un comando de
> pluma por cada una?* A nivel del intérprete (`gcode_walk.py`), sí: se emite un `PenEvent` en
> cada línea que trae `Z`, aunque el estado no cambie — el propio intérprete no filtra nada. El
> filtrado ocurre más abajo, en `CNCPlotter._set_pen` (ver §3.6), que sí recuerda el último
> comando realmente enviado y no repite la trama si la pluma ya está donde se pide.
>
> **Pregunta típica:** *¿por qué el estado del intérprete no se transforma, solo la salida?*
> Porque si se transformara el estado acumulado, un archivo en `G91` (relativo) arrastraría la
> escala en cada línea sucesiva, multiplicando el efecto de la transformación en vez de aplicarla
> una sola vez sobre la geometría final.

### 3.5 `soft_limits.py` — el guardián del área física

Ya se explicó el "por qué" en el §2.4. El detalle:

**`Violation`** (`@dataclass(frozen=True)`, `soft_limits.py:34`): guarda qué eje se salió
(`'x'`/`'y'`), qué valor se pidió, y qué límite se superó. Es una estructura de datos, no un texto
libre, precisamente para que la API pueda devolvérsela al frontend como JSON y que este pinte el
aviso sin tener que analizar una cadena de texto. `message()` la formatea a texto legible solo
cuando hace falta mostrarla.

**`LimitExceeded`**: una excepción que envuelve una `Violation`. Es lo que
`CNCPlotter._check_area` lanza cuando un punto no cabe.

**`check_point(x_mm, y_mm, max_x, max_y, tolerance=0.5)`** (`soft_limits.py:66`): la comprobación
de un solo punto. Compara contra `-tolerance` y `max + tolerance` en cada eje, devolviendo la
**primera** violación encontrada (o `None`).

**`check_bounds(bounds, max_x, max_y, tolerance=0.5)`** (`soft_limits.py:79`): igual, pero sobre
una caja completa. Solo hace falta comprobar las cuatro esquinas extremas (`min_x`, `max_x`,
`min_y`, `max_y`), porque son las únicas que pueden violar un rectángulo alineado con los ejes.

**`remaining_mm(position_mm, direction, max_mm, tolerance=0.5)`** (`soft_limits.py:99`): calcula
cuánto espacio queda hasta el tope en un sentido dado. La usa `/api/jog` para poder decir "en ese
sentido quedan 3.2 mm" en vez de simplemente rechazar la petición sin más información.

> **Pregunta típica:** *¿por qué 0.5 mm de tolerancia y no cero?* Porque el redondeo mm→pasos y
> el último punto de un arco descompuesto pueden quedar unas décimas de milímetro fuera del
> límite exacto sin que eso implique ningún riesgo mecánico real. Sin tolerancia, un archivo
> perfectamente válido se rechazaría por un error de redondeo de centésimas de milímetro.

### 3.6 `cnc_plotter.py` — el cerebro que mueve la máquina

Es el archivo más grande de lógica de movimiento. La clase `CNCPlotter` traduce eventos de
`gcode_walk` en movimiento real, y también contiene los patrones de prueba y los flujos de
calibración interactivos de la CLI.

**`bresenham_steps(x0, y0, x1, y1)`** (`cnc_plotter.py:73`): el algoritmo de Bresenham en enteros
puros — sin ningún cálculo en punto flotante — para decidir, paso a paso, si conviene avanzar en
X, en Y, o en ambos a la vez, de forma que la trayectoria en pasos discretos se aproxime lo más
posible a la línea recta ideal. Se conserva para el modo interactivo y para los tests, pero **no**
es el camino normal de dibujo: ese usa `CMD_LINE`, donde el firmware ejecuta su propio Bresenham
dentro del microcontrolador (ver §2.5) para no pagar el costo de un mensaje por paso.

**`CNCPlotter.__init__`** (`cnc_plotter.py:115`) guarda los parámetros de la máquina (pasos por
milímetro, área máxima, velocidades, umbral de pluma, si se aplican límites blandos) y el estado
del intérprete de G-code (`abs_mode`, `gc_x`/`gc_y`, `feedrate`). También guarda `abort_check`:
una función opcional que, si existe y devuelve `True`, permite cancelar el trabajo **entre
segmentos** de una línea larga, no solo entre líneas completas de G-code.

**`from_config(cls, proto, cfg)`** (`cnc_plotter.py:167`): construye el plotter a partir del
diccionario de configuración, y además **empuja al firmware** lo que le corresponde al firmware
(profundidad y velocidad de pluma, sentido del eje Z) llamando a `proto.sync_firmware()`. Antes de
esta versión, `pen_steps` se guardaba en el JSON pero nunca llegaba de verdad al
microcontrolador — el firmware seguía usando un valor fijo (`[SW-5]`).

**Conversión mm → pasos** (`mm_to_steps_x`/`_y`, `cnc_plotter.py:204-208`): ya explicada en el
§2.1. Solo dos líneas de código, pero es la que garantiza que no se acumule error de redondeo.

**`move_to_steps(target_x, target_y, draw)`** (`cnc_plotter.py:212`): calcula el delta en pasos
respecto a la posición actual real (`self.proto.pos_x/pos_y`, no la posición "creída") y decide
entre `_rapid_move` (sin dibujar) o `_draw_line` (dibujando).

- **`_rapid_move(dx, dy)`**: fija la velocidad rápida, y mueve X y luego Y de forma secuencial
  (no diagonal): dos comandos independientes, cada uno con su propio conteo de pasos.
- **`_draw_line(tx, ty, dx, dy)`**: fija la velocidad de dibujo. Los movimientos puramente
  horizontales o verticales usan `step_x`/`step_y` directamente. Los movimientos **diagonales**
  usan `send_line_segment` (la trama extendida `CMD_LINE`) si caben en 255 pasos, o
  `_draw_line_chunked` si son más largos.

**`_draw_line_chunked(abs_dx, abs_dy, dir_x, dir_y)`** (`cnc_plotter.py:264`) merece un ejemplo
concreto, porque es la pieza que garantiza que una línea larga no se desvíe por redondeo
acumulado. Supongamos una diagonal de 790 pasos en X y 331 en Y (el ejemplo real usado en la
presentación del proyecto). El eje mayor es X (790), y se reparte en `ceil(790/255) = 4`
segmentos: 255, 255, 255 y 25 pasos de X. Para cada corte, el eje menor (Y) se calcula así:

```python
cur_minor_acc = round(seg_end * minor_total / major)   # posición acumulada teórica en Y
seg_minor = cur_minor_acc - prev_minor_acc               # lo que toca a ESTE segmento
```

Es decir: en cada segmento se calcula dónde *debería* estar el eje menor si el reparto fuera
perfecto, y se manda solo la diferencia con el segmento anterior. Esto garantiza que la suma de
los cuatro trozos en Y da **exactamente** 331, nunca 330 ni 332 por acumulación de redondeos
independientes. Si cada segmento redondeara su propia fracción de 331/4 por separado, los cuatro
redondeos se sumarían con un error propio, y la línea llegaría torcida a un destino distinto del
real.

Nótese además que esta función **no recibe el destino final como parámetro**: `pos_x`/`pos_y` se
van acumulando segmento a segmento, y solo con lo que el microcontrolador confirmó por ACK. Si el
trabajo se cancela o falla la comunicación a mitad, forzar la posición final haría creer que el
carro llegó a un sitio donde en realidad no llegó.

**`_check_area(x_mm, y_mm)`** (`cnc_plotter.py:305`): la última red de seguridad — ver §2.4. Lanza
`LimitExceeded` si `enforce_soft_limits` está activo y el punto no cabe.

**`line_to`/`rapid_to`** (`cnc_plotter.py:328-341`): la API de alto nivel en milímetros. Ambas
comprueban el área antes de mover, y actualizan `gc_x`/`gc_y` (la posición del intérprete en mm).
`rapid_to` además fuerza la pluma arriba antes de moverse.

**`trace_points(points, draw)`** (`cnc_plotter.py:357`): recorre una lista ya calculada de puntos
(los de un arco, por ejemplo) fijando la velocidad **una sola vez** al principio, no en cada
punto — la razón de ser del `ArcEvent` completo del §3.4.

**El caché de pluma — `_set_pen(down)`** (`cnc_plotter.py:533`): el punto único por el que pasan
todos los cambios de pluma.

```python
if self._pen_cmd_sent is down:
    return True
ok = self.proto.pen_down() if down else self.proto.pen_up()
self._pen_cmd_sent = down if ok else None
return ok
```

Aunque `pen_up`/`pen_down` son idempotentes en el firmware (repetirlos no rompe nada), cada uno
cuesta un viaje completo de UART más el movimiento físico de Z (unos 5 ms como mínimo). Hay
post-procesadores de G-code que repiten la misma `Z` en cada una de miles de líneas de un
archivo; sin este caché, cada línea gastaría un viaje completo aunque la pluma ya estuviera donde
tenía que estar. `_pen_cmd_sent` se reinicia a `None` al empezar cada trabajo nuevo
(`invalidate_pen_cache()`, dentro de `begin_job()`), de modo que la **primera** orden de pluma de
cada trabajo siempre se envía de verdad y reafirma el estado real de la máquina; a partir de ahí,
el caché solo avanza cuando el microcontrolador confirma con ACK, así que nunca puede quedarse
"mintiendo" sin que `comm_lost` se entere.

**`begin_job()`** (`cnc_plotter.py:421`): deja el intérprete en un estado limpio antes de cada
trabajo. Reinicia `abs_mode = True` y `feedrate` (si el trabajo anterior terminó en `G91`, el
siguiente no debía heredar el modo relativo — `[SW-43]`), invalida el caché de pluma, y
**re-deriva `gc_x`/`gc_y` de los pasos reales** (`_sync_gc_from_steps`) — porque si la máquina
recibió un jog manual entre trabajos, la posición que el intérprete cree tener y la posición real
del motor podrían no coincidir, y el primer arco del trabajo (que usa `gc_x`/`gc_y` como
referencia del centro) saldría desplazado (`[SW-44]`).

**`events(lines, transform)`** (`cnc_plotter.py:450`): un envoltorio de una sola línea sobre
`gcode_walk.walk()`, pero es un envoltorio importante — es el **único** lugar donde se decide qué
umbral de pluma, qué tolerancia de cuerda y qué estado inicial de pluma usar para *esta* máquina
en concreto. Tanto la vista previa como el pre-vuelo de límites llaman a esta misma función (o a
una equivalente con los mismos parámetros), para no poder pedir un recorrido distinto por
accidente.

**`plot_gcode_lines(lines, transform)`** (`cnc_plotter.py:462`): el punto de entrada de la CLI.
Primero valida el área completa con `bounds_of` + `check_bounds` — si no cabe, no mueve nada y
devuelve `False` con un mensaje. Si cabe, recorre los eventos con `exec_event`, comprobando en
cada iteración si hay que abortar o si se perdió la comunicación.

**`exec_event(ev)`** (`cnc_plotter.py:513`): el traductor final. Toda la interpretación del
G-code ya la hizo `gcode_walk`; aquí solo queda `if isinstance(...)` y llamar al método de
movimiento correspondiente. Esta separación de responsabilidades es la razón de ser de todo el
diseño del walker: la vista previa y el pre-vuelo consumen la misma lista de eventos y no pueden
ver una geometría distinta de la que finalmente se ejecuta aquí.

**Patrones de prueba** (`draw_square`, `draw_triangle`, `draw_circle`, `draw_star`,
`draw_calibration_grid`): dibujos fijos usados para verificar la máquina sin necesidad de un
archivo de G-code. Nótese que `size_mm` significa cosas distintas según el patrón — lado del
cuadrado, pero **radio** en el círculo y **espaciado de celda** en la rejilla — algo que
`cnc_api.py` tiene que tener en cuenta al calcular límites (ver §3.8).

**Flujos de calibración de la CLI** (`calibrate_steps`, `calibrate_backlash`, `calibrate_pen`):
menús interactivos por teclado. `calibrate_pen` es el más elaborado: guía al usuario por el orden
recomendado `V → U/J → Z → N → T` (invertir sentido si hace falta, subir/bajar a mano hasta la
altura segura, fijar el cero, fijar la profundidad, probar el ciclo completo).

> **Pregunta típica:** *¿por qué `_draw_line_chunked` no recibe el punto de destino como
> parámetro?* Porque la posición se debe actualizar únicamente con lo que el microcontrolador
> confirmó, segmento a segmento. Si se le pasara el destino y se forzara `pos_x`/`pos_y` a ese
> valor al final, un fallo de comunicación o una cancelación a mitad de camino haría que el
> software creyera que el carro llegó a un punto al que en realidad nunca llegó.
>
> **Pregunta típica:** *¿por qué `begin_job()` es necesario si cada movimiento ya se valida por
> separado?* Porque hay estado que persiste **entre** movimientos dentro del mismo trabajo (el
> modo `G90`/`G91`, la posición de referencia para arcos, el caché de pluma), y ese estado no se
> reinicia solo. Sin `begin_job()`, un segundo trabajo lanzado en la misma sesión heredaría el
> modo relativo o la posición de referencia del trabajo anterior.

### 3.7 `cnc_protocol.py` — la capa de comunicación serie

Ya se cubrió el diseño del protocolo en el §2.5 y §2.2. Aquí, el recorrido por las funciones.

**`CNCProtocol.__init__`** (`cnc_protocol.py:122`): guarda el candado (`_lock`), la posición en
pasos enteros (`pos_x`, `pos_y`, `pos_z`), la profundidad de pluma, la velocidad de Z, el sentido
del eje Z (`z_invert`), el backlash por eje, y un diccionario `stats` de contadores
(`sent`/`ack`/`nack`/`timeout`/`retries`) útil para diagnóstico.

**`connect()`** (`cnc_protocol.py:170`): en modo simulación, no hace nada más que devolver
`True`. En modo real, abre el puerto serie (capturando explícitamente los errores de puerto
ocupado, inexistente o sin permisos — `[SW-33]` — para devolver `False` en vez de propagar una
excepción hasta un error 500 en la API web), lee de forma **no bloqueante** un posible mensaje de
bienvenida del microcontrolador, y **siempre** llama a `sync_firmware()` al final. Esto último es
clave: el AT89S52 no se reinicia solo porque se abra el puerto serie desde la computadora, así que
conserva su estado entre ejecuciones del programa — hay que **leerlo**, nunca asumirlo.

**`sync_firmware()`** (`cnc_protocol.py:254`): el orden importa. Primero **empuja** lo que la
computadora quiere que el firmware tenga (velocidad de Z, profundidad de pluma, sentido de Z), y
**después** lee el estado resultante con `get_state()`. Así, los valores que quedan cacheados en
Python son los que el microcontrolador **confirmó**, no los que la computadora creía tener antes
de preguntar.

**`get_state()`** (`cnc_protocol.py:281`): manda `CMD_GET_STATE` y lee la respuesta:
`ACK + Z_POS + PEN_N + VEL + VEL_Z + Z_DIR` (6 bytes). Los primeros 5 son obligatorios; el sexto
(`Z_DIR`) es opcional a propósito, para poder hablar con un firmware anterior a la función de
inversión de Z. Si no llega ese sexto byte, `z_invert_supported` queda en `False`, y la interfaz
puede decir "hace falta reprogramar el microcontrolador" en vez de fingir silenciosamente que el
ajuste se aplicó.

**`send_command(cmd, payload, retries, timeout)`** (`cnc_protocol.py:334`): construye la trama,
calcula el checksum XOR, y entra en un bucle de hasta `retries` intentos. El tiempo de espera, si
no se especifica, se calcula dinámicamente según el tipo de comando y el tamaño del payload
(`cnc_protocol.py:349-359`) — esto evita falsos tiempos agotados que dispararían reintentos
innecesarios (y, en un comando no idempotente, un doble movimiento).

**`send_line_segment(abs_dx, abs_dy, dir_x, dir_y)`** (`cnc_protocol.py:404`): la trama extendida
`CMD_LINE`. Solo se intenta **una vez** (`[SW-4]`): reintentar redibujaría el segmento entero, que
no es idempotente.

**`step_x`/`step_y`/`step_z`** (`cnc_protocol.py:470-542`): tres funciones muy parecidas.
Normalizan la dirección a `±1` con `_sign()` (`[SW-35]`: pasar `direction=2` habría duplicado el
avance de la posición cacheada respecto al motor real), reparten el conteo en trozos de máximo
255 pasos, y **solo actualizan la posición cacheada con los pasos realmente ejecutados y
confirmados** — si `send_command` falla a mitad, la posición no avanza más de lo que de verdad
se movió. Si `count <= 0`, no se manda nada ni se dispara compensación de backlash
(`[SW-36]`) — no tiene sentido compensar un movimiento que no existe.

**`pen_up()`/`pen_down()`** (`cnc_protocol.py:544-559`): comandos absolutos e idempotentes, con
`retries=3` (frente a `retries=1` de los movimientos relativos — ver §2.2).

**`set_z_invert(invert, move_pen=True)`** (`cnc_protocol.py:586`): merece explicación aparte
porque resuelve un problema físico real del montaje. El mecanismo del eje Z se puede montar de
dos formas, y en una de ellas el giro que debería **subir** la pluma la **baja**. La inversión se
resuelve en el **firmware** (`C_ZDIR`), nunca emulándola en la computadora — si se emulara aquí,
`Z_POS = 0` significaría "arriba" con un montaje y "abajo" con el otro, reintroduciendo
exactamente la doble fuente de verdad que el diseño de Z absoluto (§2.2) eliminó. Antes de cambiar
el sentido, si `move_pen=True`, primero sube la pluma **con el sentido antiguo** (para dejar
`Z_POS` en 0 de forma inequívoca) y solo entonces manda el cambio.

**`set_speed(ms)`** (`cnc_protocol.py:667`): cachea la última velocidad **confirmada** por ACK
(`_last_speed_ok`), y no reenvía la misma velocidad si ya es la vigente. Un círculo de cientos de
segmentos habría mandado cientos de tramas de velocidad idénticas sin este caché. El caché se
invalida ante cualquier fallo de comunicación, para que nunca pueda "mentir" sobre lo que el
microcontrolador realmente tiene configurado.

**Backlash** (`_backlash_comp`, `cnc_protocol.py:696`): la compensación solo se dispara cuando hay
un **cambio real de sentido** respecto al último movimiento de ese eje — no en cada movimiento.
El backlash es la holgura mecánica de los engranajes: al invertir el sentido de giro, los primeros
pasos del motor no mueven el carro, solo recogen ese juego mecánico.

**Persistencia de posición** (`_save_position`, `_maybe_save_position`, `load_last_position`,
`clear_last_position`, `cnc_protocol.py:741-815`): la posición X/Y se guarda en `.last_position`
(en la raíz del repositorio) cada 100 movimientos —no cada 100 pasos individuales, para no hacer
cientos de escrituras por cada círculo— con escritura atómica igual que `cnc_config.py`
(`[SW-37]`). `load_last_position()` valida el contenido a fondo (`[SW-38]`): si el archivo fue
tocado a mano, o el marcador de tiempo es del futuro (reloj cambiado), o tiene más de dos horas de
antigüedad (`POSITION_MAX_AGE_S = 7200`), lo descarta devolviendo `None` en vez de propagar un
valor corrupto que acabaría siendo la posición asumida del carro entero. La posición de **Z**
nunca se recupera de este archivo — siempre se vuelve a leer del microcontrolador con
`get_state()`, porque el firmware sí la lleva en absoluto y es la única fuente de verdad posible.

> **Pregunta típica:** *¿por qué la posición de Z no se guarda en `.last_position` como X e Y?*
> Porque Z ya vive de forma absoluta dentro del firmware (`Z_POS`), y ese es el único lugar donde
> tiene sentido preguntarla. Guardar una copia en un archivo del lado de la computadora
> reintroduciría una segunda fuente de verdad que podría desincronizarse — exactamente lo que el
> diseño de Z absoluto existe para evitar.
>
> **Pregunta típica:** *¿por qué el archivo de posición solo se confía si tiene menos de dos
> horas?* Porque pasado ese tiempo es razonable asumir que alguien movió los ejes a mano (por
> ejemplo, recolocando la máquina), y confiar en una posición vieja sin verificar sería peor que
> no tener ninguna: movería la máquina asumiendo un punto de partida falso.

### 3.8 `cnc_api.py` — la API web

Envuelve todo lo anterior en una aplicación FastAPI. Es el archivo más largo, pero conceptualmente
es "un endpoint HTTP por cada acción que ya sabía hacer `CNCPlotter`/`CNCProtocol`", más la
gestión de un trabajo en segundo plano y un WebSocket de progreso.

**Estado global del módulo** (`cnc_api.py:90-117`): `proto`/`plotter` (instancias activas, o
`None` si no hay conexión), `job_state` (diccionario con el progreso del trabajo actual),
`loaded_gcode` (las líneas del último archivo subido), `gcode_transform`/`gcode_bounds_raw` (la
transformación vigente y la caja delimitadora **sin** transformar, del archivo original),
`abort_event` (señal de cancelación), `job_lock` (el segundo candado del §2.6).

**Por qué la transformación vive aparte del archivo** (`cnc_api.py:104-108`): el archivo de
G-code subido nunca se reescribe. La transformación (espejo/ajuste) es un dato independiente que
el mismo intérprete consume junto al archivo original. Esto tiene una consecuencia práctica
directa: quitar el espejo después de haberlo aplicado cuesta exactamente lo mismo que ponerlo — no
hay que volver a subir el archivo.

**Los tres candados/guardas de concurrencia** (ya el detalle del §2.6):

- `_require_conn()`: exige que haya una conexión activa.
- `_require_idle()`: exige que no haya un trabajo en curso (`[SW-3b]`) — se usa incluso en
  endpoints que "solo" mueven la pluma o hacen home, porque cualquier movimiento que se inyecte a
  mitad de un trabajo desincroniza el firmware.
- `_claim_job()` / `_release_job()`: la reserva atómica del §2.6, protegida por `job_lock`.
- `_job_aborted()` (`cnc_api.py:189`): `abort_event.is_set()` **solo cuenta si hay un trabajo
  activo** (`[SW-49]`). Antes, `/api/stop` o `/api/disconnect` dejaban la señal de aborto puesta
  indefinidamente, y el siguiente movimiento largo (una calibración, un home) se cancelaba solo,
  en silencio, sin mover un solo paso — un fallo muy difícil de diagnosticar porque no producía
  ningún error visible.

**`_status_dict()`** (`cnc_api.py:218`): la versión **síncrona** del estado completo de la
máquina — posición, velocidades, si hay trabajo activo, estadísticas de comunicación, etc. Es
síncrona a propósito (`[SW-3c]`): los endpoints que mueven motores son bloqueantes (`def`, no
`async def`), porque FastAPI los ejecuta en un grupo de hilos aparte para no congelar el bucle de
eventos (y con él, el WebSocket) durante un movimiento largo. Si `_status_dict` fuera `async`,
obligaría a que quien la llama también lo fuera.

**Ciclo de vida (`lifespan`, `cnc_api.py:120`)**: al apagar la aplicación, se marca el aborto, se
**espera** (con `join(timeout=10.0)`) a que el hilo de trabajo termine, y solo entonces se sube la
pluma, se apagan los motores y se desconecta. Esperar al hilo es necesario para no matar la
conexión serie mientras un hilo todavía la está usando.

**Flujo de subida y vista previa de G-code:**

- `POST /api/upload-gcode`: guarda las líneas (con un límite de 200 000 líneas,
  `MAX_GCODE_LINES`), resetea la transformación a la identidad (archivo nuevo, sin espejo previo),
  calcula la caja delimitadora **sin transformar** (`gcode_bounds_raw`) y devuelve
  `_gcode_payload(...)`.
- `_gcode_payload()` (`cnc_api.py:436`): recorre el G-code cargado **una sola vez** con
  `walk_loaded()` (el mismo intérprete que dibujará), y de esa misma pasada extrae tanto la vista
  previa como la caja delimitadora. Antes eran dos recorridos separados, cada uno con sus propias
  omisiones (ver §2.3). El preview se acota a `MAX_PREVIEW_PATHS = 5000` trazos y
  `MAX_PREVIEW_ARC_POINTS = 64` puntos por arco (`[SW-53]`) — sin este límite, un archivo con
  miles de arcos podía generar cientos de miles de puntos en un solo JSON y colgar el navegador.
  Importante: la caja delimitadora se calcula sobre la geometría **real** completa del arco, no
  sobre la muestra reducida del preview — solo el dibujo visual se recorta, nunca el cálculo de
  límites.
- Cada trazo del preview lleva el **índice de línea** (`ev.line`) que lo originó. El mensaje
  `progress` que el WebSocket manda durante la ejecución real usa exactamente ese mismo índice
  (`ev.line + 1`), sobre la misma lista `loaded_gcode`. Son directamente comparables, y eso es lo
  que permite al frontend pintar en vivo qué trazo ya se dibujó y cuál falta.
- `POST /api/gcode-transform`: recalcula `gcode_transform` con `build_transform(...)`, siempre
  desde `gcode_bounds_raw` (la caja original), nunca encadenando sobre la transformación anterior.

**El pre-vuelo de `/api/run`** (`cnc_api.py:658`): antes de esta versión, la comprobación de
límites solo existía en `plot_gcode_lines()` — el camino de la línea de comandos. Por HTTP nunca
se ejecutaba: un archivo marcado como "no cabe" al subirlo se dibujaba igual, y el carro llegaba
al tope. Ahora `/api/run` calcula la caja delimitadora con la transformación vigente, y si no
cabe, responde **409** con un detalle estructurado (`violation`, `bounds`, `work_area`,
`can_autofit: True`) — el frontend usa ese último campo para ofrecer "Ajustar al área" como acción
inmediata, en vez de solo mostrar un error.

**`run_gcode_thread(lines, abort_evt, pl, pr, transform)`** (`cnc_api.py:579`): el hilo en segundo
plano que ejecuta el trabajo. Nótese que recibe `pl`/`pr` (plotter/proto) **como parámetros**, no
los lee de las variables globales del módulo (`[SW-52]`) — si un `/api/disconnect` concurrente
pone esas globales a `None` a mitad de trabajo, el hilo seguiría operando con sus referencias
locales válidas y terminaría de forma ordenada, en vez de morir con un error dentro de su propio
bloque `finally` (que es precisamente donde se avisa por WebSocket de que el trabajo terminó). El
`finally` de este hilo **siempre** sube la pluma, incluso ante aborto o excepción — nunca debe
quedar clavada en el papel.

**Jog** (`POST /api/jog`, `cnc_api.py:783`): normaliza la dirección a `±1` (`[SW-50]`: con
`direction=2` la posición cacheada habría avanzado el doble que el eje real). El jog de X/Y
respeta `enforce_soft_limits` y, si el destino se sale, responde con `max_allowed_mm` — cuánto
espacio queda en ese sentido — en vez de un simple rechazo sin información útil. El jog de Z usa
su propia escala (`steps_per_mm_z`, no la de X) y su propio límite de `0` a `255` pasos
(`[SW-6]`).

**Endpoints de pluma/Z** (`/api/pen`, `/api/pen-jog`, `/api/pen-holder`, `/api/z-set-zero`,
`/api/z-off`, `/api/pen-test-cycle`, `/api/pen-test-line`, `/api/pen-config`): cada uno delega en
el método equivalente de `CNCPlotter`/`CNCProtocol`, y casi todos invalidan el caché de pluma
(`invalidate_pen_cache()`) porque representan un movimiento de Z hecho "por fuera" del flujo
normal de dibujo — el sistema no puede asumir que su caché sigue siendo válido después de eso.

**Validación de rangos en los modelos de entrada** (`[SW-51]`, por ejemplo `SettingsReq` en
`cnc_api.py:1094` o `JogReq` en `cnc_api.py:776`): Pydantic valida rangos explícitos
(`Field(gt=0.0, le=5000.0)`, etc.) antes de que el valor llegue a ningún cálculo. Antes de esto,
un `steps_per_mm = 0` enviado por error dejaba la API entera respondiendo error 500 por división
por cero en **cada** petición posterior que necesitara convertir pasos a milímetros — un fallo que
no se arreglaba solo, había que reiniciar el proceso.

**Patrones de prueba y su tamaño máximo** (`PATTERN_EXTENTS`, `_pattern_max_size`,
`cnc_api.py:1247-1276`): como `size` no significa lo mismo en cada patrón (lado del cuadrado, pero
radio del círculo, pero espaciado de celda en la rejilla), el tamaño máximo que cabe en el área se
**deriva** matemáticamente de `PATTERN_EXTENTS` (resolviendo la recta afín tamaño→dimensiones)
en vez de mantener una segunda tabla de máximos escrita a mano — dos tablas independientes se
desincronizarían en cuanto alguien cambiara un patrón sin acordarse de actualizar la otra.

**El WebSocket `/ws`** (`cnc_api.py:1488`): al conectar, manda un mensaje `status` inicial; después
solo espera (`receive_text()`) sin hacer nada con lo recibido — es un canal de salida, no de
entrada. Los mensajes de progreso (`send_ws_message`) se generan desde el hilo de trabajo (que
corre en un hilo del sistema operativo, no en el bucle de eventos de asyncio) usando
`asyncio.run_coroutine_threadsafe`, la forma correcta de cruzar de un hilo normal al bucle de
eventos sin corromper su estado interno.

> **Pregunta típica:** *¿por qué `/api/run` no confía en la validación que ya se hizo al subir el
> archivo con `/api/upload-gcode`?* Porque entre subir el archivo y pulsar "ejecutar" puede haber
> pasado un cambio: el usuario pudo aplicar un espejo, un ajuste al área, o cambiar el área
> máxima de la máquina en Ajustes. `/api/run` vuelve a calcular la caja delimitadora con la
> transformación **vigente en ese momento**, no con la que había al subir el archivo.
>
> **Pregunta típica:** *¿por qué el hilo de trabajo recibe `plotter`/`proto` como parámetros en
> vez de leer las variables globales del módulo?* Porque una desconexión concurrente
> (`/api/disconnect`) pone esas variables globales a `None`. Si el hilo las leyera directamente,
> moriría con un error justo dentro de su bloque `finally` — precisamente el bloque que avisa por
> WebSocket de que el trabajo terminó — y el frontend se quedaría esperando un mensaje que nunca
> llega.

---

## 4. Recorrido completo: de "subir un archivo" a "terminó de dibujar"

Tener esta secuencia clara de memoria es la mejor defensa ante la pregunta "explíqueme qué pasa
cuando…". Sigamos un G-code real, paso a paso, por todos los archivos.

**1. El usuario sube un archivo (`POST /api/upload-gcode`).**
`cnc_api.py` decodifica el contenido, comprueba que no supere 200 000 líneas, y lo guarda en
`loaded_gcode`. Resetea la transformación a identidad. Calcula `gcode_bounds_raw` con
`gcode_walk.bounds_of()`. Llama a `_gcode_payload()`, que recorre el archivo **una vez** con
`walk()` y devuelve al frontend: la caja delimitadora, si cabe en el área, y una vista previa (con
puntos de arco muestreados si son muchos).

**2. El usuario marca "Voltear Y" y/o "Ajustar al área" (`POST /api/gcode-transform`).**
`cnc_api.py` llama a `gcode_transform.build()` con la caja **original** (`gcode_bounds_raw`), no
con una transformación anterior. Se construye una nueva instancia inmutable de `GcodeTransform` y
se vuelve a llamar a `_gcode_payload()` para devolver una vista previa actualizada — sin tocar el
archivo en disco ni haberlo vuelto a subir.

**3. El usuario pulsa "Ejecutar" (`POST /api/run`).**
Primero el **pre-vuelo**: `gcode_walk.bounds_of()` se recalcula con la transformación vigente, y
`soft_limits.check_bounds()` compara esa caja contra el área máxima configurada. Si no cabe, la
API responde **409** sin haber tocado el puerto serie, y el frontend puede ofrecer "Ajustar al
área" automáticamente. Si cabe, `cnc_api._claim_job()` marca atómicamente el trabajo como activo
(bajo `job_lock`) y arranca un hilo (`run_gcode_thread`) en segundo plano.

**4. Dentro del hilo (`run_gcode_thread`).**
Se llama a `plotter.begin_job()`: reinicia el modo `G90`, invalida el caché de pluma, y
re-deriva la posición del intérprete desde los pasos reales del motor. Después, un bucle
`for ev in pl.events(lines, transform)` — que por debajo es `gcode_walk.walk()` con los
parámetros de esta máquina concreta — entrega eventos uno a uno.

**5. Cada evento se traduce en movimiento (`plotter.exec_event(ev)`).**
- Un `MoveEvent` con `draw=True` llama a `line_to(x, y)`: comprueba el área (última red), convierte
  mm a pasos con `mm_to_steps_x/_y`, y llama a `move_to_steps()`, que decide entre movimiento recto
  por eje o `CMD_LINE` diagonal (con troceo si supera 255 pasos).
- Un `ArcEvent` llama a `trace_points()`, que fija la velocidad una vez y recorre cada punto del
  arco ya descompuesto con `line_to`/`rapid_to`.
- Un `PenEvent` llama a `_set_pen(down)`, que solo manda la trama si el estado realmente cambia
  respecto al último comando confirmado.
- Un `DwellEvent` simplemente espera con `time.sleep()`.

**6. Cada movimiento real habla con el firmware (`cnc_protocol.py`).**
`step_x`/`step_y`/`send_line_segment` arman la trama binaria correspondiente, la mandan por el
puerto serie protegidos por `_lock`, esperan ACK con un tiempo de espera calculado según el
comando, y solo si llega ACK actualizan la posición cacheada (`pos_x`/`pos_y`). Cada 100
movimientos, la posición se guarda en `.last_position` de forma atómica.

**7. El progreso se transmite en vivo.**
Cada evento procesado actualiza `job_state` y, como máximo cada 0.2 segundos, `run_gcode_thread`
manda un mensaje `progress` por el WebSocket con la línea actual, el porcentaje, la posición en
mm y en pasos de Z, y el tiempo transcurrido — usando el mismo índice de línea que etiquetó cada
trazo del preview en el paso 1, así el frontend puede pintar exactamente lo ya dibujado.

**8. El trabajo termina (o se cancela, o falla).**
El bloque `finally` de `run_gcode_thread` **siempre** sube la pluma y guarda la posición, pase lo
que pase — abortado por el usuario, error de límites, pérdida de comunicación, o final normal.
Libera el candado del trabajo (`_release_job()`) y manda un último mensaje por WebSocket
(`complete` o `error`).

---

## 5. Banco de preguntas relámpago

Repaso rápido en formato pregunta-respuesta corta. Si alguna no sale de memoria en menos de cinco
segundos, es señal de volver a la sección correspondiente.

**¿Cuántos archivos Python tiene el proyecto y qué hace cada uno en una frase?**
Ocho: `cnc_config` (persistencia de ajustes), `gcode_parse` (léxico + arcos), `gcode_transform`
(espejo/escala), `gcode_walk` (el intérprete único), `soft_limits` (validación de área),
`cnc_plotter` (mueve la máquina), `cnc_protocol` (habla por el puerto serie), `cnc_api` (API web).

**¿Cuál es el único intérprete de G-code del proyecto?**
`gcode_walk.walk()`. Antes había tres (ejecución, límites, vista previa) y habían divergido.

**¿Qué produce `walk()` y por qué no ejecuta directamente los movimientos?**
Produce eventos (`MoveEvent`, `ArcEvent`, `PenEvent`, `DwellEvent`) con la geometría ya resuelta.
No ejecuta directamente para que tres consumidores distintos (ejecución, límites, vista previa)
puedan reaccionar exactamente a lo mismo, sin poder divergir.

**¿Qué diferencia legítima existe entre cómo la ejecución y la vista previa llaman a `walk()`?**
El estado inicial de la pluma (`initial_pen_down`): la ejecución pasa el estado real
(`proto.pen_down_flag`); la vista previa y los límites pasan `False`, porque describen el archivo,
no el instante actual de la máquina.

**¿Por qué Z es absoluto y X/Y son relativos?**
Porque eso hace que los comandos de pluma sean idempotentes (repetir "sube a 0" no hace daño) y
permite reintentarlos con seguridad, mientras que los movimientos de X/Y no se pueden reintentar
sin arriesgarse a moverlos dos veces.

**¿De dónde sale `pen_down_flag`?**
Es una propiedad derivada de `pos_z >= max(1, pen_steps)`, nunca una variable booleana
independiente.

**¿Qué pasa si el firmware se apaga y se vuelve a encender entre sesiones?**
Nada especial del lado de la posición Z: al reconectar, `connect()` siempre llama a
`sync_firmware()`, que relee el estado real (`get_state()`) en vez de asumir lo que la
computadora recordaba.

**¿Por qué la máquina no tiene finales de carrera y qué consecuencia de diseño tiene eso?**
Por costo y simplicidad. La consecuencia es que los límites de área **bloquean** el trabajo antes
de empezar, en vez de solo avisar — llegar al tope mecánico pierde pasos silenciosamente y
descalibra la máquina entera.

**¿Cuáles son los dos niveles de comprobación de límites?**
Preventivo (`check_bounds`, sobre la caja completa antes de mover nada) y de último recurso
(`check_point`, en cada movimiento, por si el origen se movió a mano entre medias).

**¿Qué tolerancia usan los límites blandos y por qué?**
0.5 mm, porque el redondeo mm→pasos y el cierre de un arco pueden dejar unas décimas fuera sin
ningún riesgo mecánico real.

**¿Cómo se calcula el número de segmentos de un arco?**
A partir de una tolerancia de cuerda (el error máximo permitido entre la cuerda recta y el arco
real), con la fórmula `error = r * (1 - cos(θ/2))`. Un radio grande necesita más segmentos que uno
pequeño para el mismo error.

**¿Qué tolerancia de cuerda usa este proyecto en concreto?**
Un paso de motor: `min(1/steps_per_mm_x, 1/steps_per_mm_y)`. Afinar más no se puede imprimir.

**¿Qué hace `arc_to_segments` si los valores `I`/`J` son incoherentes con el destino?**
Detecta que el punto final no está a la misma distancia del centro que el inicio, y en vez de
dibujar una espiral, cae a una línea recta hasta el destino.

**¿Por qué el espejo en Y se aplica después de descomponer el arco en puntos, y no reescribiendo
el G-code?**
Porque reescribir un arco espejado obliga a invertir `G2`↔`G3` y el signo de `J`; un descuido
produce una curvatura incorrecta sin ningún síntoma visible hasta imprimir. Espejar una polilínea
de puntos ya resueltos no tiene ese caso especial.

**¿Por qué "ajustar al área" siempre calcula desde la caja original del archivo?**
Para que aplicarlo dos veces seguidas no encoja el dibujo dos veces.

**¿Puede "ajustar al área" agrandar un dibujo pequeño?**
No. La escala es `min(escala_x, escala_y, 1.0)`: solo puede encoger o dejar igual, nunca ampliar.

**¿Por qué X e Y se calibran por separado?**
Porque son mecanismos físicos distintos (cremallera y piñón con relaciones distintas), con
escalas distintas. La máquina real de este proyecto mide 79.0 pasos/mm en X y 82.76 en Y.
Calibrar solo X y aplicarlo también a Y producía un óvalo donde debía haber un círculo.

**¿Qué es el backlash y cuándo se compensa?**
La holgura mecánica de los engranajes. Se compensa solo cuando hay un cambio real de sentido de
giro respecto al último movimiento de ese eje — no en cada movimiento.

**¿Por qué la conversión mm→pasos siempre parte de la coordenada absoluta y no del delta?**
Para no acumular error de redondeo. El error máximo total queda acotado a medio paso sin importar
cuántos segmentos tenga el trabajo.

**¿Qué hace `CMD_LINE` y por qué existe?**
Manda una línea diagonal entera (`DX`, `DY`, signo de cada eje) en una sola trama, y el firmware
ejecuta el Bresenham él mismo. Sin esto, cada paso individual necesitaría su propio mensaje y su
propia confirmación — mucho más lento y con más ruido eléctrico por el cable USB.

**¿Cómo se reparte una línea de más de 255 pasos?**
`_draw_line_chunked` la corta en segmentos de máximo 255 pasos en el eje mayor, y calcula el eje
menor de cada segmento con un acumulador entero (posición teórica acumulada menos la del segmento
anterior), para que la suma total no se desvíe del destino real por redondeos independientes.

**¿Por qué los comandos de movimiento usan `retries=1` y los de pluma `retries=3`?**
Porque los de pluma son absolutos e idempotentes (repetir no hace daño); los de movimiento son
relativos (repetir movería el eje una segunda vez).

**¿Qué invalida el caché de velocidad (`_last_speed_ok`)?**
Cualquier fallo de comunicación. El caché solo puede contener un valor que el firmware haya
confirmado por ACK; nunca puede "mentir" sobre la velocidad real configurada.

**¿Qué invalida el caché de pluma (`_pen_cmd_sent`)?**
Empezar un trabajo nuevo (`begin_job`), o cualquier movimiento de Z hecho por fuera del flujo
normal (jog manual, resincronización, fijar el cero) — situaciones donde el software no puede
asumir que su caché sigue siendo válido.

**¿Cómo se garantiza que un archivo corrupto de configuración no tumbe el sistema?**
`load_config()` detecta el JSON inválido, guarda una copia con extensión `.corrupto` para poder
recuperarla a mano, y sigue funcionando con los valores por defecto.

**¿Por qué la escritura de configuración y de posición son atómicas (archivo temporal +
reemplazo)?**
Para que un corte a mitad de la escritura nunca deje un archivo truncado: o se ve la versión
anterior completa, o la nueva completa, nunca una mezcla.

**¿Por qué no se confía en `.last_position` si tiene más de dos horas?**
Porque pasado ese tiempo es razonable que alguien haya movido los ejes a mano, y usar una posición
vieja sin verificar sería peor que no tener ninguna.

**¿Por qué la posición de Z nunca se recupera de `.last_position`?**
Porque el firmware ya la lleva de forma absoluta; preguntársela al microcontrolador es la única
fuente de verdad posible, y guardar una copia aparte reintroduciría el riesgo de desincronización.

**¿Qué candados de concurrencia hay y qué protege cada uno?**
Uno (`RLock` dentro de `CNCProtocol`) protege cada acceso al puerto serie, para que dos tramas no
se entremezclen byte a byte. Otro (`job_lock` en `cnc_api.py`) protege la decisión atómica de "voy
a reservar este trabajo", para que dos peticiones simultáneas de ejecutar no arranquen dos hilos
sobre el mismo puerto.

**¿Por qué no basta con comprobar "¿hay trabajo activo?" al inicio de un endpoint?**
Porque hay una ventana de tiempo entre esa comprobación y el momento en que el hilo realmente
empieza a trabajar, y una segunda petición podría colarse en esa ventana viendo el mismo estado
"libre".

**¿Por qué `abort_event` solo cuenta mientras hay un trabajo activo?**
Porque antes, un `/api/stop` o una desconexión dejaban la señal de aborto puesta indefinidamente,
y el siguiente movimiento largo (una calibración, un home) se cancelaba solo, sin ningún error
visible que lo explicara.

**¿Por qué los endpoints que mueven motores son `def` y no `async def`?**
Porque FastAPI ejecuta las funciones síncronas en un grupo de hilos aparte, sin bloquear el bucle
de eventos — y con él, el WebSocket — durante un movimiento largo.

**¿Por qué el hilo de trabajo recibe `plotter`/`proto` como parámetros en vez de usar las
variables globales?**
Porque una desconexión concurrente pone esas variables a `None`, y si el hilo las leyera
directamente moriría con un error justo dentro del bloque que avisa al frontend de que el trabajo
terminó.

**¿Por qué `/api/run` vuelve a validar los límites en vez de confiar en la validación de
`/api/upload-gcode`?**
Porque entre subir el archivo y ejecutar puede haber cambiado la transformación aplicada o el área
máxima configurada. Se valida siempre contra el estado vigente en el momento de ejecutar.

**¿Cómo se acota el tamaño de la vista previa que se manda al navegador?**
A un máximo de 5000 trazos y 64 puntos por arco muestreados. La caja delimitadora, sin embargo, se
calcula siempre sobre la geometría real completa, nunca sobre la muestra reducida.

**¿Cómo sabe el frontend qué trazo del dibujo ya se ejecutó?**
Porque tanto la vista previa como los mensajes de progreso del WebSocket usan el mismo índice: el
número de línea del archivo de G-code que originó cada evento.

**¿Qué endpoint hace de "botón de pánico" y qué hace exactamente?**
`/api/resync`, que llama a `sync_firmware()`: relee el estado real del microcontrolador (posición
de Z, profundidad de pluma, velocidades, sentido de Z) y realinea la computadora con lo que el
firmware tiene de verdad.

**¿Por qué `size` en los patrones de prueba necesita una tabla (`PATTERN_EXTENTS`) en vez de
usarse directamente como límite?**
Porque no significa lo mismo en todos los patrones: es el lado en el cuadrado, pero el radio en el
círculo y el espaciado de celda en la rejilla. Sin esa tabla, un valor de `size` que en el círculo
mide el doble de ancho podría aceptarse sin comprobar si realmente cabe.

**¿Qué prueba automática existe para garantizar que la vista previa y la ejecución nunca
diverjan?**
`test_lo_que_se_ejecuta_es_lo_que_se_valida`, en `python/tests/test_gcode_walk.py`. Ejecuta un
G-code contra una máquina simulada, registra cada coordenada real por la que pasa, y comprueba
que coincide exactamente con la caja que calculó el validador de límites sobre el mismo archivo.

---

## 6. Glosario mínimo

- **ACK / NACK** — confirmación positiva (`0x06`) o negativa (`0x15`) que el firmware responde
  tras recibir una trama.
- **Backlash** — holgura mecánica de un engranaje; al invertir el sentido de giro, los primeros
  pasos no mueven nada físicamente.
- **Bresenham** — algoritmo clásico para trazar una línea recta usando solo aritmética entera,
  decidiendo paso a paso si avanzar en un eje, en el otro, o en ambos.
- **Checksum XOR** — verificación de integridad de una trama: el resultado de aplicar XOR a todos
  los bytes anteriores debe dar cero en el receptor.
- **Evento (en este proyecto)** — una de las cuatro estructuras inmutables que produce
  `gcode_walk.walk()`: `MoveEvent`, `ArcEvent`, `PenEvent`, `DwellEvent`.
- **Idempotente** — una operación que, repetida varias veces, produce siempre el mismo resultado
  que aplicarla una sola vez. "Sube la pluma" es idempotente; "avanza 10 pasos" no lo es.
- **Intérprete modal** — un intérprete de G-code que mantiene estado entre líneas (`G90`/`G91`,
  posición actual), en vez de tratar cada línea de forma aislada.
- **Límite blando (soft limit)** — un límite impuesto por software, no por un sensor físico.
- **Pre-vuelo** — la comprobación que ocurre antes de mover un solo paso, sobre la geometría
  completa del trabajo.
- **Transformación afín** — una combinación de espejo, escala y traslación, aplicada como una
  sola operación matemática congelada (`GcodeTransform`).
- **Trama** — un paquete de bytes con un formato fijo que viaja por el puerto serie.
