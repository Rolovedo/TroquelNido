"""NIDO - interfaz. Uso:
    python app.py            -> modo interactivo por consola (pregunta los datos)
    python app.py --web      -> servidor local en http://localhost:8000 (formulario + vista previa)
    python app.py --demo     -> ejemplo con una taza de cerámica
Genera: nido_troquel.svg, nido_pasos.txt y nido_resultado.json
"""
import json, sys, html
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs
import nido_core as nc
from config import cargar_configuracion


CONFIG = cargar_configuracion()


def elegir(titulo, opciones):
    print(f"\n{titulo}")
    ks = list(opciones)
    for i, k in enumerate(ks, 1):
        print(f"  {i}. {k}")
    while True:
        s = input("Elige número: ").strip()
        if s.isdigit() and 1 <= int(s) <= len(ks):
            return ks[int(s) - 1]
        print("  Opción inválida.")


def numero(txt, opcional=False):
    while True:
        s = input(txt).strip().replace(",", ".")
        if not s and opcional:
            return None
        try:
            return float(s)
        except ValueError:
            print("  Escribe un número.")


def guardar(r, debug=False):
    open("nido_troquel.svg", "w", encoding="utf-8").write(nc.svg(r))
    open("nido_tapa.svg", "w", encoding="utf-8").write(nc.svg_tapa(r))
    json.dump(nc.a_dict(r), open("nido_resultado.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    tapa = nc.calcular_tapa(r)
    json.dump({
        "medidas": nc.asdict(tapa),
        "geometria": nc.geometria_tapa(tapa),
        "pasos": nc.pasos_tapa(r),
        "svg": nc.svg_tapa(r),
    }, open("nido_tapa_resultado.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    if debug:
        open("nido_pasos.txt", "w", encoding="utf-8").write("\n".join(nc.pasos(r)))
        open("nido_tapa_pasos.txt", "w", encoding="utf-8").write("\n".join(nc.pasos_tapa(r)))


def consola():
    print("=== NIDO · generador de troquel a la medida ===")
    tipo = elegir("Tipo de producto:", nc.TIPO_PRODUCTO)
    mat = elegir("Material del producto:", nc.MATERIAL_PRODUCTO)
    print("\nDimensiones del producto en milímetros.")
    L = numero("Largo (mm): "); A = numero("Ancho (mm): "); H = numero("Alto (mm): ")
    p = numero("Peso en kg (Enter si no lo sabes): ", opcional=True)
    r = nc.calcular(nc.Entrada(tipo, mat, L, A, H, p), CONFIG)
    guardar(r, "--debug-coordenadas" in sys.argv)
    print("Troquel y tapa generados.")
    if "--debug-coordenadas" in sys.argv:
        print("\nDepuración de coordenadas:")
        for line in nc.pasos(r): print(line)
    for a in r.advertencias: print("⚠", a)
    print("\nArchivos: nido_troquel.svg, nido_tapa.svg, nido_pasos.txt, "
          "nido_tapa_pasos.txt, nido_resultado.json, nido_tapa_resultado.json")


FORM = """<!doctype html><meta charset=utf-8><title>NIDO</title>
<style>body{{font-family:system-ui;max-width:1000px;margin:24px auto;padding:0 16px}}
label{{display:block;margin:8px 0 2px}}input,select{{padding:6px;width:260px}}button{{margin-top:12px;padding:8px 16px}}
pre{{background:#f6f1e4;padding:12px;white-space:pre-wrap}}.w{{color:#b35c00}}</style>
<h1>NIDO · generador de troquel</h1>
<form method=post>
<label>Tipo de producto<select name=tipo>{tipos}</select></label>
<label>Material<select name=material>{mats}</select></label>
<label>Unidad<select name=unidad><option value="mm">Milímetros (mm)</option><option value="cm">Centímetros (cm)</option></select></label>
<label>Largo<input name=largo type=number step=any required value="{largo}"></label>
<label>Ancho<input name=ancho type=number step=any required value="{ancho}"></label>
<label>Alto<input name=alto type=number step=any required value="{alto}"></label>
<label>Peso (kg, opcional)<input name=peso type=number step=any value="{peso}"></label>
<label>Holgura g (mm, opcional)<input name=g type=number min=0 step=any value="{g}"></label>
<label>Profundidad d del panal (mm, opcional)<input name=d type=number min=0 step=any value="{d}"></label>
<label>Flauta (opcional)<select name=flauta><option value="">Automática según peso</option>{flautas}</select></label>
<label>Ancho disponible de hoja (mm, opcional)<input name=ancho_hoja type=number min=1 step=any value="{ancho_hoja}"></label>
<label>Alto disponible de hoja (mm, opcional)<input name=alto_hoja type=number min=1 step=any value="{alto_hoja}"></label>
<button>Generar troquel</button></form>{resultado}"""


def pagina(v=None, resultado=""):
    v = v or {}
    opt = lambda d, sel: "".join(f'<option{" selected" if k == sel else ""}>{html.escape(k)}</option>' for k in d)
    flautas = "".join(f'<option{" selected" if f[0] == v.get("flauta") else ""}>{f[0]}</option>'
                      for f in CONFIG.flautas)
    return FORM.format(tipos=opt(nc.TIPO_PRODUCTO, v.get("tipo")), mats=opt(nc.MATERIAL_PRODUCTO, v.get("material")),
                       largo=v.get("largo", ""), ancho=v.get("ancho", ""), alto=v.get("alto", ""),
                       peso=v.get("peso", ""), g=v.get("g", ""), d=v.get("d", ""),
                       ancho_hoja=v.get("ancho_hoja", ""), alto_hoja=v.get("alto_hoja", ""),
                       flautas=flautas, resultado=resultado)


class H(BaseHTTPRequestHandler):
    def _send(self, body):
        b = body.encode("utf-8")
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self): self._send(pagina())

    def do_POST(self):
        q = parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
        v = {k: x[0] for k, x in q.items()}
        try:
            unidad = v.get("unidad", "mm")
            peso = float(v["peso"]) if v.get("peso") else None
            def convertir(valor):
                if valor is None or valor == "":
                    return None
                return nc.convertir_a_mm(float(valor), unidad)
            r = nc.calcular(nc.Entrada(v["tipo"], v["material"],
                                        convertir(v["largo"]), convertir(v["ancho"]), convertir(v["alto"]),
                                        peso, v.get("flauta") or None, convertir(v.get("g")), convertir(v.get("d")),
                                        True, convertir(v.get("ancho_hoja")), convertir(v.get("alto_hoja"))), CONFIG)
            res = nc.svg(r, 0.5)
            if "--debug-coordenadas" in sys.argv:
                res += "<pre>" + html.escape("\n".join(nc.pasos(r))) + "</pre>"
            res += "".join(f'<p class=w>⚠ {html.escape(a)}</p>' for a in r.advertencias)
        except Exception as ex:
            res = f'<p class=w>Error: {html.escape(str(ex))}</p>'
        self._send(pagina(v, res))


if __name__ == "__main__":
    if "--web" in sys.argv:
        print("http://localhost:8000"); HTTPServer(("", 8000), H).serve_forever()
    elif "--demo" in sys.argv:
        r = nc.calcular(nc.Entrada("vidrio / cristal", "vidrio", 48, 50, 80, 0.4), CONFIG)
        guardar(r, "--debug-coordenadas" in sys.argv)
        print("Troquel generado: 48×50×80 mm, vidrio.")
        if "--debug-coordenadas" in sys.argv:
            print("\nDepuración de coordenadas:")
            print("\n".join(nc.pasos(r)))
    elif "--demo120" in sys.argv:
        r = nc.calcular(nc.Entrada("vidrio / cristal", "vidrio", 120, 80, 100, 0.4), CONFIG)
        guardar(r, "--debug-coordenadas" in sys.argv)
        print("Troquel generado: 120×80×100 mm, vidrio.")
    else:
        consola()
