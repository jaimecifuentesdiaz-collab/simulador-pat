"""PAT 140 g (pedido de Jaime, 17-11-2026): arrastre libre de candidatos en Planta real y Equipos auxiliares, reconexión de bombas y
textos sin referencias al curso en las pantallas de elección."""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
HTML = (RAIZ / "ui" / "componentes" / "lienzo_planta" / "index.html").read_text(encoding="utf-8")


def _sin_comentarios_js(t: str) -> str:
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
    return "\n".join(l.split("// ")[0] if l.lstrip().startswith("//") or " // " in l else l for l in t.splitlines())


def test_lienzo_suelta_en_lugar_libre_y_marca_destinos():
    for f in ("function soltarCandidato", "function destinosDe", "function pintarDestinos", "function parpadear", "function lineaBajo",
              "function controlesAux", 'emitir("conectar_aux"', 'emitir("mover_aux"', "data-linea-aux", "anillo-dest", "trazo-aux"):
        assert f in HTML, f
    assert "Suéltelo sobre ${" not in HTML                     # ya no obliga a soltar exactamente sobre el símbolo
    assert ".toast.ok{background:#1b7a5a}" in HTML              # aviso verde


def test_textos_visibles_sin_referencias_al_curso():
    vis = _sin_comentarios_js(HTML).lower()
    assert "pidió el profesor" not in vis and "profesor torres" not in vis
    from ui import p_seleccion as PS, p_auxiliares as PA
    for t in (PS.AYUDA, PS.AYUDA_LIENZO, PA.AYUDA, PA.AYUDA_LIENZO):
        assert "profesor" not in t.lower() and "memoria" not in t.lower() and "informe" not in t.lower()
    src = (RAIZ / "ui" / "p_seleccion.py").read_text(encoding="utf-8")
    assert '"Fuentes del catálogo: "' not in src                 # la línea de fuentes del catálogo bajo las alternativas se quitó
