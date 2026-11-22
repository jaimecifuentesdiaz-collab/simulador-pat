"""Validador del diseño en la interfaz (PAT 143, tarea 6): advertencia que no deja avanzar y botón «Pista» en los cuatro lienzos
(Planta ficticia, Planta real, Equipos auxiliares y Lazos de control).

Las reglas están en pat_sim/motor/validador.py. Aquí:
- revisar(vista, ...) revisa la pantalla con la planta de la sesión y guarda cuántos errores tiene (st.session_state["validador"]);
- panel(vista, res) dibuja, sobre el lienzo, la advertencia con la lista de errores y el botón «Pista»: cada clic muestra una pista
  más del primer error (general, dónde mirar y qué cambiar en ese punto), sin resolver el diseño;
- bloqueo_etapa(etapa) lo lee la franja del proceso (ui/flujo.py) para no dejar pasar a la etapa siguiente;
- redibujar_si_cambio(vista) vuelve a ejecutar la aplicación cuando la pantalla pasa de bloqueada a libre (o al revés), para que la
  franja, que se dibuja antes que la pantalla, quede al día. Con el sustituto de Streamlit del banco de pruebas o con todas las
  pantallas a la vez (PAT_TODAS_LAS_PAGINAS=1) no se vuelve a ejecutar.
"""
from __future__ import annotations
import os
import streamlit as st
from pat_sim.motor import validador as V
from . import comun as C

CLAVE = "validador"
# Pantalla de construcción de cada etapa de la franja (motor/flujo.ETAPAS)
ETAPA_VISTA = {2: "ficticia", 3: "real", 4: "real", 5: "auxiliares", 6: "lazos"}
MAX_LISTA = 8


def _cache() -> dict:
    return st.session_state.setdefault(CLAVE, {})


def _vigente(g, pl) -> bool:
    return isinstance(g, dict) and g.get("pl") == id(pl)


def previas(vista: str) -> dict:
    """Errores de Equipos auxiliares ya revisados con esta planta, para las pantallas que vienen después (los auxiliares necesitan
    sus candidatos y no se recalculan desde otra pantalla). La Planta ficticia y la Planta real las revisa el motor en el momento."""
    pl = C.planta()
    g = _cache().get("auxiliares")
    return {"auxiliares": int(g["errores"])} if "auxiliares" in V.ANTERIORES[vista] and _vigente(g, pl) else {}


def revisar(vista: str, **kw) -> dict:
    """Revisa la pantalla (kw: motivo, precedencia, aux, objetivos) y guarda su número de errores. Nunca bota la pantalla."""
    pl = C.planta()
    try:
        res = V.revisar(pl, vista, previas=previas(vista), **kw)
    except Exception as e:                       # el validador no debe impedir trabajar si falla él mismo
        res = dict(vista=vista, hallazgos=[], errores=[], avisos=[], bloquea=False, falla=str(e))
    c = _cache()
    antes = c.get(vista)
    bloqueada_antes = bool(_vigente(antes, pl) and antes.get("errores"))
    c[vista] = dict(errores=len(res["errores"]), pl=id(pl), cambio=bloqueada_antes != bool(res["errores"]))
    return res


def bloqueo_etapa(etapa) -> tuple[str, int] | None:
    """(pantalla, errores) de la primera pantalla de construcción hasta la etapa dada que tiene errores, o None."""
    if etapa is None:
        return None
    pl = C.planta(); c = _cache()
    for e in sorted(ETAPA_VISTA):
        if e > etapa:
            break
        g = c.get(ETAPA_VISTA[e])
        if _vigente(g, pl) and g.get("errores"):
            return V.NOMBRE_VISTA[ETAPA_VISTA[e]], int(g["errores"])
    return None


def _todas() -> bool:
    return hasattr(st, "REG") or os.environ.get("PAT_TODAS_LAS_PAGINAS") == "1"


def redibujar_si_cambio(vista: str) -> None:
    """Si la pantalla pasó de bloqueada a libre (o al revés) en esta ejecución, la aplicación se vuelve a ejecutar una vez para que
    la franja del proceso, que se dibuja arriba, habilite o bloquee «Etapa siguiente». Se llama al final de la pantalla."""
    g = _cache().get(vista)
    if not isinstance(g, dict) or not g.pop("cambio", False) or _todas():
        return
    st.rerun()


def _subir(vista: str, objetivo: str, total: int) -> None:
    ss = st.session_state; k = f"val_pista_{vista}"
    est = ss.get(k) if isinstance(ss.get(k), dict) else {}
    nivel = int(est.get("nivel", 0)) if est.get("id") == objetivo else 0
    ss[k] = dict(id=objetivo, nivel=min(total, nivel + 1))


def nivel_pista(vista: str, res: dict) -> int:
    """Pistas ya pedidas para el primer error; vuelve a 0 cuando el primer error cambia (se corrigió o apareció otro antes)."""
    e = res.get("errores") or []
    est = st.session_state.get(f"val_pista_{vista}")
    if not e or not isinstance(est, dict) or est.get("id") != e[0]["id"]:
        return 0
    return int(est.get("nivel", 0))


def panel(vista: str, res: dict, avisos: bool = False) -> None:
    """Advertencia con los errores y el botón «Pista», sobre el lienzo. avisos=True: además, los avisos en un desplegable cerrado
    (en la Planta ficticia los avisos ya están en «Diagnóstico» del lienzo y en Lazos de control en la tabla de la revisión)."""
    errores = res.get("errores") or []
    if not errores:
        st.session_state.pop(f"val_pista_{vista}", None)
        if avisos and res.get("avisos"):
            with st.expander(f"Observaciones que no impiden avanzar ({len(res['avisos'])})"):
                st.markdown(C.esc("\n".join(f"- {a['mensaje']}" for a in res["avisos"])))
        return
    n = len(errores)
    lista = "\n".join(f"- {e['mensaje']}" for e in errores[:MAX_LISTA]) + (f"\n- Y {n - MAX_LISTA} más." if n > MAX_LISTA else "")
    with st.container(key=f"val_panel_{vista}"):
        st.error(C.esc(f"**El diseño tiene {n} error{'es' if n > 1 else ''} que no deja{'n' if n > 1 else ''} avanzar a la etapa "
                       f"siguiente:**\n{lista}"))
        p = errores[0]
        tot = len(p["pistas"])
        nivel = nivel_pista(vista, res)
        a, b = st.columns([1, 6])
        a.button("Pista", key=f"val_pista_btn_{vista}", on_click=_subir, args=(vista, p["id"], tot), disabled=nivel >= tot,
                 width="stretch",
                 help=("Ya están todas las pistas de este error." if nivel >= tot else
                       "Cada clic muestra una pista más sobre el primer error de la lista: primero la regla, después dónde mirar y al "
                       "final qué cambiar en ese punto. No cambia el diseño."))
        b.caption(f"Pistas sobre el primer error de la lista: {nivel} de {tot}." if nivel else
                  "«Pista» orienta sobre el primer error de la lista, paso a paso.")
        for i, t in enumerate(p["pistas"][:nivel], 1):
            st.info(C.esc(f"**Pista {i}.** {t}"))
    if avisos and res.get("avisos"):
        with st.expander(f"Observaciones que no impiden avanzar ({len(res['avisos'])})"):
            st.markdown(C.esc("\n".join(f"- {a['mensaje']}" for a in res["avisos"])))
