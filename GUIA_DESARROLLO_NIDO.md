# Guía de desarrollo – Generador de troquel NIDO

Objetivo: una herramienta que pida **tipo de producto, material y dimensiones**, calcule un embalaje de cartón a la medida (sin relleno de pomelo) y devuelva **las medidas del troquel paso a paso + una imagen** (SVG/PNG/PDF).

## 1. Lenguaje y stack recomendado

| Capa | Recomendación | Por qué |
|---|---|---|
| Núcleo de cálculo | **Python 3.11+** (sin librerías) | Es lógica matemática pura; fácil de probar y de explicar en la sustentación. Ya existe en `nido_core.py`. |
| Interfaz (fase 2) | **HTML + JavaScript** (formulario y vista previa SVG) llamando al núcleo vía **FastAPI** | Lo que describe tu documento: formulario, vista previa y descarga. |
| Imagen | **SVG** (nativo) → PNG con Playwright/CairoSVG y PDF a escala 1:1 | El SVG es el formato que aceptan las cortadoras láser/plotters y las troqueladoras. |
| Pruebas | **pytest** | Valida fórmulas con casos conocidos. |
| Control de versiones | **Git + GitHub** | Reparto de trabajo entre las 3 disciplinas del equipo. |

Alternativa si el tiempo aprieta (sustentación 24 de noviembre): todo en JavaScript en el navegador (se publica gratis en GitHub Pages, sin servidor). Las fórmulas son las mismas.

## 2. Qué debe implementar (módulos)

1. **Entradas y validación**: tipo de producto, material, largo, ancho, alto (mm), peso opcional. Rechazar valores fuera de rango.
2. **Clasificación de fragilidad** (1–4): sale del tipo y del material (se toma el mayor).
3. **Parámetros por fragilidad**: holgura `g` (producto–pared interior) y profundidad de panal `d`.
4. **Selección de cartón**: flauta E/B/C según peso → espesor `t`.
5. **Cálculo del troquel** (ver fórmulas).
6. **Pasos de trazado**: lista numerada con coordenadas X/Y de columnas, filas, cortes y pliegues.
7. **Generador de imagen**: SVG con corte continuo, pliegue punteado, cotas en mm.
8. **Lista de tiras de panal** (el "relleno" estructural de cartón).
9. **Advertencias**: peso excesivo, troquel que no cabe en la hoja de la troqueladora.
10. **Exportación**: SVG, JSON, TXT; luego PDF a escala 1:1 y QR (opcional).

## 3. Fórmulas (mm)

```
fragilidad = max(f(tipo), f(material))          # 1..4
g, d       = tabla[fragilidad]                  # holgura y panal
t          = espesor de la flauta (E 1.5 · B 3 · C 4)

margen = g + d + 2t
Lb = largo + 2·margen        # base exterior
Wb = ancho + 2·margen
Hw = alto  + 2·margen        # altura de pared
Hs = Hw − 2t                 # solapa interior (2ª pared, entra doblada)

ancho_total = 2·(Hs + Hw) + Lb
alto_total  = tab_l + 2·(Hs + Hw) + Wb
```

Distribución (coincide con la Figura B): columnas X = 0 · Hs · Hs+Hw · +Lb · +Hw · +Hs; filas Y = tab_l · +Hs · +Hw · +Wb · +Hw · +Hs. Lengüeta centrada en la solapa trasera; ranura en la base cerca del pliegue frontal.

## 4. Cómo empezar (orden de trabajo)

**Día 1–2 · Núcleo.**
`python app.py --demo` ya genera `nido_troquel.svg`, `nido_pasos.txt` y `nido_resultado.json`. Léelo, cambia las dimensiones y comprueba que entiendes cada número.

**Día 3 · Prototipo físico.**
Corta en cartón el troquel de una taza o frasco con las medidas generadas (Fase 4 del documento) y haz la prueba de caída de 1 m. **Esto es lo más importante:** con los resultados ajustas las tablas `HOLGURAS`, `FLAUTAS` y el cierre (ranura/lengüeta), que son hipótesis iniciales, no valores validados.

**Día 4–5 · Pruebas automáticas.** Añade `pytest`: p. ej. para 100×100×100 mm la base debe ser `100+2·margen`; ancho_total debe ser la suma de columnas; ningún valor negativo.

**Día 6–7 · Web.** `python app.py --web` ya sirve un formulario con vista previa. Para la versión final: FastAPI (`POST /troquel` devuelve JSON + SVG) y una página HTML con formulario, vista previa y botón de descarga.

**Día 8+ · Extras.** PDF a escala 1:1 para imprimir/cortar, código QR con instrucciones de apertura y reciclaje, panal dibujado en la vista, varias unidades (cm/mm), historial de diseños.

## 5. Estructura de carpetas sugerida

```
nido/
├─ nido_core.py     # lógica (Ing. de Software)
├─ app.py           # consola / servidor (Tecnología en Desarrollo)
├─ tests/           # pytest y casos de la prueba de caída (Mantenimiento Aeronáutico: tolerancias)
├─ web/             # index.html, estilos, JS
└─ README.md
```

## 6. Limitaciones a declarar en la sustentación

- Las holguras y el espesor son **valores de partida**; se validan con prueba de caída.
- No se modela el pliegue real del cartón (compensación por espesor) más allá de `Hs = Hw − 2t`.
- El cierre sigue la Figura B (una ranura + una lengüeta); si en el prototipo no sostiene, se prueba con dos ranuras.
- Peso > 15 kg requiere cartón de pared doble: fuera del alcance actual.
- Sin relleno de pomelo: el amortiguamiento viene solo del panal de cartón y de la zona de deformación.

## 7. Comandos

```
python app.py          # modo consola (pregunta los datos)
python app.py --web    # http://localhost:8000
python app.py --demo   # ejemplo: taza de cerámica 120×95×100 mm
```
