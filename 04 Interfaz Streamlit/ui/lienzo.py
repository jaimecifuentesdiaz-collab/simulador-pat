"""Envoltura en Python del componente «lienzo_planta» (simulador de planta de la pestaña Diseño).

El componente es un archivo HTML propio (ui/componentes/lienzo_planta/index.html: HTML, CSS y JavaScript con SVG
nativo, sin internet ni compilación) que habla con Streamlit por postMessage. Recibe la planta y sus resultados y
devuelve {eventos: [{evento, datos, seq}, ...], seq}: todos los eventos que todavía no se han procesado, para que no
se pierda ninguno si llegan dos seguidos mientras Python está calculando.
"""
from __future__ import annotations
from pathlib import Path
import streamlit.components.v1 as components

RUTA = Path(__file__).resolve().parent / "componentes" / "lienzo_planta"
_componente = components.declare_component("lienzo_planta", path=str(RUTA))
CLAVE = "lienzo_planta"


def lienzo(datos: dict, key: str = CLAVE):
    """Dibuja el lienzo. Devuelve el último valor enviado por el navegador (o None)."""
    return _componente(datos=datos, key=key, default=None)


def mostrar_vista(vista: str, key: str, aux: dict | None = None):
    """PAT 138: el mismo lienzo de la Planta ficticia en Planta real («real», clave sel_lienzo) y Equipos auxiliares
    («auxiliares», clave aux_lienzo), de solo lectura: la topología se arma en Diseño. Usa la planta única de la sesión
    (C.planta()); si ya está resuelta no la vuelve a resolver, y si no lo está resuelve la parte alimentada como Diseño."""
    import streamlit as st
    from pat_sim.motor import lienzo as LZ
    from . import comun as C, p_diseno as PD
    pl = C.planta()
    if not pl.equipos:
        st.caption("Lienzo vacío: arme la planta en Planta ficticia (Diseño) y vuelva aquí para verla crecer.")
        return None
    if pl.resuelta and getattr(pl, "salidas", None):
        sol, motivo = pl, None
    else:
        sol, motivo = LZ.resolver_parcial(pl)
    cat = {"todos": dict(nombre="Todos los equipos (ISO 10628)", equipos=[])}     # solo lectura: sin catálogo para arrastrar
    datos = LZ.datos_lienzo(pl, sol, motivo, cat, 0, [], PD._kpis_recuperacion(pl), None, PD._precedencia(), vista=vista, aux=aux)
    return lienzo(datos, key=key)


def mostrar_eleccion(vista: str, key: str, eleccion: dict, ultimo_seq: int = 0, mensajes: list | None = None,
                     historial: dict | None = None, aux: dict | None = None, libre: bool = False, validacion: dict | None = None):
    """PAT 139 (punto 6): el lienzo de la Planta real o de Equipos auxiliares con la elección en vivo. Además de la vista de PAT 138,
    el componente recibe «eleccion» (los candidatos de cada etapa o auxiliar, con C_inv, C_op, C_inef, C, A, η en operación, origen y fuente, y el elegido; PAT 139b: sin
    marca de mejor opción; «paralelo» dibuja n símbolos por auxiliar elegido con n unidades) y
    muestra a la izquierda la lista de candidatos: se arrastran y se sueltan sobre su etapa en el lienzo (o se hace clic en uno para
    aplicarlo a su etapa). Los equipos se pueden mover (cambio del layout) y «Deshacer» o Ctrl+Z vuelve atrás cualquiera de los dos
    cambios. Envía los eventos «elegir», «mover», «deshacer» y «rehacer» con el mismo formato de Diseño.
    PAT 143: libre=True deja soltar un candidato sobre otro equipo de la misma clase aunque no calce (lo marca el validador) y
    validacion (motor/validador.revisar) alimenta el botón «Diagnóstico» del lienzo."""
    import streamlit as st
    from pat_sim.motor import lienzo as LZ
    from . import comun as C, p_diseno as PD
    pl = C.planta()
    if not pl.equipos:
        st.caption("Lienzo vacío: arme la planta en Planta ficticia (Diseño) y vuelva aquí para elegir sus equipos reales.")
        return None
    if pl.resuelta and getattr(pl, "salidas", None):
        sol, motivo = pl, None
    else:
        sol, motivo = LZ.resolver_parcial(pl)
    cat = {"todos": dict(nombre="Todos los equipos (ISO 10628)", equipos=[])}
    datos = LZ.datos_lienzo(pl, sol, motivo, cat, int(ultimo_seq), list(mensajes or []), PD._kpis_recuperacion(pl), historial,
                            PD._precedencia(), vista=vista, aux=aux, libre=libre, validacion=validacion)
    datos["eleccion"] = eleccion
    return lienzo(datos, key=key)


def eventos_nuevos(valor, ultimo_seq: int) -> list[dict]:
    """Eventos del valor del componente que todavía no se han aplicado, en orden."""
    if not isinstance(valor, dict):
        return []
    evs = [e for e in valor.get("eventos", []) if isinstance(e, dict) and int(e.get("seq", 0)) > ultimo_seq]
    return sorted(evs, key=lambda e: int(e["seq"]))
