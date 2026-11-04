"""Pestaña Informe: arma un informe HTML y un JSON con la planta, el diagrama y las cifras; los descarga."""
from __future__ import annotations
import html, json
from datetime import datetime
import streamlit as st
from pat_sim.datos.bd import planta_a_dict, a_json
from pat_sim.motor import economia as eco
from pat_sim.motor.diagrama import planta_svg
from . import comun as C
from . import ayudas_tablas as AT   # PAT 134: «?» de cada tabla
from .p_diseno import tabla_corrientes, COLS_CORRIENTES


def construir_html(pl, r, E, cop) -> str:
    hoy = datetime.now().strftime("%d-%m-%Y")
    h = [f"<!doctype html><html lang='es'><head><meta charset='utf-8'><title>Informe del simulador PAT</title>{C.ESTILO}"
         "<style>body{font-family:Arial,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;color:#222}h1,h2{color:#1b7a5a}"
         "details.ayuda > summary h2{font-size:1.5em;margin:0.6em 0 0.3em 0}</style></head><body>",   # PAT 134: «?» de cada tabla
         f"<h1>Informe del simulador PAT</h1><p>{html.escape(pl.nombre)} · rubro {html.escape(pl.rubro)} · generado el {hoy}</p>"]
    h.append(AT.html("inf_equipos", "Equipos") + C.tabla([dict(id=e.id, n=e.nombre, t=e.nombre_tipo, c=f"{e.iso_categoria} · {e.iso_letra}") for e in pl.equipos.values()],
                                          [("id", "Identificador", "txt", 0), ("n", "Nombre", "txt", 0), ("t", "Tipo", "txt", 0), ("c", "ISO 10628 (categoría · letra)", "txt", 0)]))
    h.append(AT.html("inf_parametros", "Parámetros y su fuente"))
    filas = [dict(eq=e.id, p=p.nombre, v=p.valor, u=p.unidad, c=p.categoria, f=p.fuente) for e in pl.equipos.values() for p in e.params.values()]
    h.append(C.tabla(filas, [("eq", "Equipo", "txt", 0), ("p", "Parámetro", "txt", 0), ("v", "Valor", "num", 3), ("u", "Unidad", "txt", 0), ("c", "Categoría", "txt", 0), ("f", "Fuente", "txt", 0)]))
    try:
        h.append("<h2>Diagrama de flujo</h2><div class='contenedor-svg'>" + planta_svg(pl, tabla=False) + "</div>")
    except Exception:
        pass
    if pl.resuelta:
        h.append(AT.html("inf_corrientes", "Tabla de corrientes") + C.tabla(tabla_corrientes(pl), COLS_CORRIENTES))
        h.append(AT.html("inf_cierres", "Cierres") + C.tabla(pl.cierres(), [("equipo", "Equipo", "txt", 0), ("cierre_masa", "Masa (kg/h)", "num", 6), ("cierre_solidos", "Sólidos (kg/h)", "num", 6), ("cierre_energia", "Energía (kW)", "num", 6)]))
    if pl.instrumentos:
        h.append(AT.html("inf_instrumentos", "Instrumentación (ISA-5.1)") + C.tabla([dict(t=f"{i.letras}-{i.numero}", e=i.equipo, d=i.descripcion, f=i.elemento_final or "—") for i in pl.instrumentos],
                                                              [("t", "Identificación", "txt", 0), ("e", "Equipo", "txt", 0), ("d", "Descripción", "txt", 0), ("f", "Elemento final", "txt", 0)]))
    if not r.get("sin_sumidero") and "cascada" in r:
        h.append(AT.html("inf_recuperacion", "Recuperación de calor") + C.tabla(
            [dict(n="Sumidero", q=r["Qsumidero"], c=None), dict(n="Cascada en serie", q=r["cascada"], c=r["cobertura_cascada"]), dict(n="Objetivo pinch", q=r["pinch"], c=r["cobertura_pinch"]),
             *([dict(n="Solo condensados", q=r["alt2"], c=r["cobertura_alt2"])] if r.get("combustible") != "biomasa" else [])], [("n", "Concepto", "txt", 0), ("q", "Calor (kW)", "num", 1), ("c", "Cobertura del sumidero", "pct", 1)]))
        h.append(f"<p>Aproximación mínima {C.fmt(r['dT_min'], 1)} °C; temperatura final {C.fmt(r['T_final'], 1)} °C; COP {C.fmt(cop, 1)}.</p>")
    if "gas_base" in r:
        des = r["gas_desplazado_cascada"]
        h.append(AT.html("inf_economia", "Economía") + C.tabla([
            dict(n="Gas desplazado por la cascada (MMBtu por temporada)", v=des["MMBtu"]), dict(n="CO2 evitado (t por temporada)", v=des["co2_t"])],
            [("n", "Concepto", "txt", 0), ("v", "Valor", "num", 1)]) + C.tabla(
            [dict(n="Ahorro por temporada (MM$)", v=eco.valor_gas(des["MMBtu"], E["precio_gas"], E["dolar"]))], [("n", "Concepto", "txt", 0), ("v", "Valor", "mm", 1)]))
        h.append(f"<p>Henry Hub {C.fmt(C.HENRY_HUB, 2)} US$/MMBtu ({html.escape(C.FUENTE_HH)}); precio usado {C.fmt(E['precio_gas'], 2)} US$/MMBtu; "
                 f"dólar {C.fmt(E['dolar'], 2)} $/US$ ({html.escape(C.FUENTE_DOLAR)}).</p>")
    if "biomasa_base" in r:
        des = r["biomasa_cascada"]; precio = E.get("precio_biomasa", C.PRECIO_BIOMASA)
        h.append(AT.html("inf_economia_bio", "Economía (biomasa combustible)") + C.tabla([
            dict(n="Biomasa combustible del caso base (t por año)", v=r["biomasa_base"]["t"]),
            dict(n="Biomasa desplazada por la cascada (t por año)", v=des["t"]), dict(n="Volumen desplazado (m³ estéreo por año)", v=des["m3"]),
            dict(n="CO2 biogénico evitado (t por año)", v=des["co2_biogenico_t"])],
            [("n", "Concepto", "txt", 0), ("v", "Valor", "num", 1)]) + C.tabla(
            [dict(n="Ahorro por año (MM$)", v=des["m3"] * precio / 1e6)], [("n", "Concepto", "txt", 0), ("v", "Valor", "mm", 1)]))
        h.append(f"<p>Precio de la biomasa {C.fmt(precio, 0)} $/m³ estéreo ({html.escape(C.FUENTE_BIOMASA)}). "
                 "El CO2 de la biomasa es biogénico: se informa aparte y no suma al inventario nacional (IPCC, 2006, vol. 2, sec. 2.3.3.4).</p>")
    h.append("<p class='nota'>Cifras del Capítulo 1: Modelo_PAT_Agrozzi_v2.xlsx. Símbolos de equipos: ISO 10628; instrumentación: ISA-5.1 y estructura de ISA-5.4.</p></body></html>")
    return "".join(h)


def mostrar():
    ss = st.session_state; pl = C.planta()
    st.subheader("Informe")
    if not C.exigir_resuelta():
        return
    r = C.resumen_actual()
    doc = construir_html(pl, r, ss.economia, ss.cop)
    datos = dict(planta=planta_a_dict(pl), resumen=r, economia=ss.economia, cop=ss.cop, generado=datetime.now().isoformat(timespec="seconds"))
    a, b = st.columns(2)
    a.download_button("Descargar el informe (HTML)", doc, file_name="Informe_simulador_PAT.html", mime="text/html", type="primary")
    b.download_button("Descargar los datos (JSON)", a_json(datos), file_name="Datos_simulador_PAT.json", mime="application/json")
    from . import s_exportar                        # PAT 133, mejora 18: balance a Excel con fórmulas e informe imprimible a PDF
    s_exportar.mostrar(pl, r)
    with st.expander("Vista previa del informe", expanded=True):
        st.html(doc.split("<body>")[1].replace("</body></html>", ""))
