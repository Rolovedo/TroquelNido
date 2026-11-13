# Instrucciones del proyecto: NIDO (generador de troquel de embalaje zero-waste)

## Qué es
Herramienta que pide tipo de producto, material y dimensiones (largo, ancho, alto en mm, peso opcional) y calcula un embalaje de cartón corrugado de UNA pieza (pared doble con panal de cartón, cierre por encastre, sin pegante, cinta, grapas ni relleno sintético ni de cáscaras). Devuelve: (1) medidas del troquel, (2) pasos de trazado numerados con coordenadas X/Y, (3) imagen SVG del troquel (corte continuo, pliegue punteado, cotas en mm).

## Stack
- Núcleo: Python 3.11+, sin dependencias en `nido_core.py` (lógica pura, sin I/O).
- Interfaz: `app.py` (consola y servidor local). Fase 2: FastAPI + HTML/JS con vista previa SVG.
- Pruebas: pytest en `tests/`.

## Reglas de código
- Unidades: milímetros en todo el código. Eje Y hacia abajo, origen (0,0) arriba a la izquierda.
- Separar lógica (`nido_core.py`) de interfaz (`app.py`). El núcleo no hace print ni lee input.
- Tipado y dataclasses; comentarios y nombres de dominio en español (Lb, Wb, Hw, Hs, g, d, t).
- Toda fórmula nueva lleva prueba en `tests/`. No cambies una fórmula sin actualizar su prueba.
- Las tablas HOLGURAS y FLAUTAS son valores iniciales calibrables con la prueba de caída: déjalas como constantes editables al inicio del archivo.
- Cambios pequeños: una tarea por vez, explica qué cambiaste y cómo probarlo.

## Fórmulas (fuente de verdad)
fragilidad = max(f(tipo), f(material)) (1..4); g, d = HOLGURAS[fragilidad]; t = espesor flauta (E 1.5, B 3, C 4)
margen = g + d + 2t
Lb = largo + 2·margen; Wb = ancho + 2·margen; Hw = alto + 2·margen; Hs = Hw − 2t
ancho_total = 2·(Hs + Hw) + Lb; alto_total = tab_l + 2·(Hs + Hw) + Wb

## Distribución del troquel (cruz, una pieza)
Columnas X: 0 · Hs · Hs+Hw · +Lb · +Hw · +Hs. Filas Y: tab_l · +Hs · +Hw · +Wb · +Hw · +Hs.
Zonas: base (Lb×Wb) al centro; paredes izq./der. (Hw×Wb) y solapas interiores (Hs×Wb) a los lados; pared trasera/frontal (Lb×Hw) y solapas (Lb×Hs) arriba y abajo; lengüeta trapezoidal (ancho 25% de Lb, entre 30 y 60 mm, alto 15 mm) sobre la solapa trasera; ranura de corte en la base cerca del pliegue frontal.
Líneas de corte: continuas. Líneas de pliegue: punteadas.

## No hacer
No agregar relleno de cáscara de pomelo ni plásticos. No usar librerías pesadas para el SVG (se escribe como texto).
