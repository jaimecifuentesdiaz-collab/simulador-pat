"""Pestaña Operación: planificación y operación por turnos de 8 h (PAT 130).

Como la pestaña «Operación» del simulador del profesor (Scorm_pellet_profesor.html, runShift): meta de utilización,
compra de materia prima, mantenimiento, inventario, producción, producto conforme, demanda variable, fallas y alertas
aleatorias con semilla reproducible y desgaste de los equipos. El motor está en pat_sim.motor.operacion y cada cifra
didáctica es un Supuesto con su justificación (tabla al final de la pestaña).
"""
from __future__ import annotations
import streamlit as st
from pat_sim.motor import operacion as OP
from pat_sim.catalogos import calidad as Q
from . import comun as C
from . import ayudas_tablas as AT   # PAT 134: «?» de cada tabla


def materia(pl) -> str:
    if pl.rubro == "tomate":
        return "tomate fresco"
    al = next((e for e in pl.equipos.values() if e.tipo.startswith("alimentacion")), None)
    return str(al.v("materia")).lower() if al is not None and "materia" in al.params else "materia prima"


def producto(pl) -> str:
    return {"tomate": "pasta de tomate", "pellet": "pellet", "chip": "chip", "lena": "leña"}.get(pl.rubro, "producto")


def ejecutar_turno(op, pl, origen: str = "op"):
    """Ejecuta un turno con los valores de la pestaña Operación (también lo usa Calidad SPC) y vuelve a correr la aplicación."""
    ss = st.session_state
    try:
        reg = OP.correr_turno(op, pl, float(ss.get("op_meta", 90.0)) / 100, ss.get("op_compra"), ss.get("op_mant", "ninguno"), C.resumen_o_nada(),
                               dist_falla_h=ss.get("distribuciones", {}).get("falla_h"))
        ss.aviso_operacion = origen, (f"Turno {reg['turno']} ejecutado: {C.fmt(reg['producido'])} t producidas, {C.fmt(reg['conforme'])} t conformes "
                              f"y {C.fmt(reg['vendido'])} t vendidas.")
    except ValueError as e:
        ss.error_operacion = origen, str(e)
    st.rerun()


def tomar_muestra(op, pl, origen: str = "op"):
    ss = st.session_state
    try:
        tk = OP.tomar_muestra(op, pl)
        ss.aviso_operacion = origen, f"Muestra {tk['id']} enviada al laboratorio: el resultado llega con el turno {tk['entrega']}."
    except ValueError as e:
        ss.error_operacion = origen, str(e)
    st.rerun()


def avisos(origen: str = "op"):
    """Muestra el aviso en la pestaña donde se presionó el botón (Operación o Calidad SPC)."""
    ss = st.session_state
    for clave, fn in (("aviso_operacion", st.success), ("error_operacion", st.error)):
        v = ss.get(clave)
        if v and v[0] == origen:
            fn(ss.pop(clave)[1])


def mostrar():
    ss = st.session_state; pl = C.planta()
    st.subheader("Operación por turnos de 8 h")
    avisos("op")
    if not C.exigir_resuelta():
        return
    op = C.operacion(); ln = OP.linea(pl)
    if ln is None:
        st.warning("La planta no entrega producto: revise en Diseño que la línea llegue hasta el despacho o el llenado.")
        return
    mp, pr = materia(pl), producto(pl)
    if "op_compra" not in ss:
        ss.op_compra = round(OP.compra_sugerida(ln, 0.90), 1)
    ss.setdefault("op_meta", 90.0)
    izq, der = st.columns(2, gap="large")
    with izq:
        C.ayuda("Cada ejecución representa un turno de 8 h. Las decisiones pueden cambiarse antes de cada turno; las "   # PAT 134: ayuda «?»
                "fallas, las alertas y las causas especiales se aplican durante el turno y dependen de la semilla del estudiante.",
                "Planificación y operación")
        a, b, c = st.columns(3)
        a.number_input("Meta de utilización (%)", 0.0, 100.0, step=1.0, key="op_meta")
        b.number_input(f"Compra de {mp} (t)", 0.0, None, step=10.0 if ln["alimentacion"] > 20 else 1.0, key="op_compra",
                       help=(f"Sugerida para la meta de 90 %: {C.fmt(OP.compra_sugerida(ln, 0.90))} t por turno "
                             f"({C.fmt(ln['mp_por_t'], 2)} t de {mp} por t de {pr})."))
        c.selectbox("Mantenimiento", list(OP.MANTENIMIENTOS), format_func=OP.MANTENIMIENTOS.get, key="op_mant")
        b1, b2 = st.columns(2)
        if b1.button("Ejecutar siguiente turno", type="primary", disabled=op.finalizada, key="op_turno", width="stretch"):
            ejecutar_turno(op, pl)
        if b2.button("Solicitar ensayos de laboratorio", disabled=op.finalizada, key="op_muestra", width="stretch"):
            tomar_muestra(op, pl)
        _df = ss.get("distribuciones", {}).get("falla_h")
        if _df:                                  # PAT 134: duración de fallas ajustada en Datos de entrada
            st.info(f"Duración de las fallas con la distribución ajustada `{_df['expresion']}` ({_df.get('origen', 'Datos de entrada')}): "
                    "un turno con falla conserva 1 − duración/8 de su capacidad. Se quita en Datos de entrada.")
        if op.finalizada:
            st.info("La evaluación ya fue finalizada: para seguir practicando, reinicie la práctica en la pestaña Evaluación.")
        T = op.turnos
        k1, k2 = st.columns(2); k3, k4 = st.columns(2)
        k1.metric("Turnos", op.turno)
        k2.metric("Producido", C.fmt(sum(x["producido"] for x in T)) + " t")
        k3.metric("Vendido", C.fmt(sum(x["vendido"] for x in T)) + " t")
        k4.metric("Demanda insatisfecha", C.fmt(sum(x["faltante"] for x in T)) + " t")
        if T:
            AT.tabla("op_turnos", "Turnos ejecutados", 4)   # PAT 134: «?» de la tabla
            filas = [dict(x, mant=OP.MANTENIMIENTOS[x["mantenimiento"]], conf=100 * x["conformidad"],
                          ev="; ".join(e.rstrip(".") for e in x["eventos"]),
                          en=x["gas_evitado_MMBtu"] if x["gas_evitado_MMBtu"] is not None else x["biomasa_evitada_t"]) for x in T]
            cols = [("turno", "Turno", "num", 0), ("producido", "Producción (t)", "num", 1), ("conf", "Conforme (%)", "num", 1),
                    ("vendido", "Ventas (t)", "num", 1), ("demanda", "Demanda (t)", "num", 1), ("faltante", "Faltante (t)", "num", 1)]
            if T[-1]["gas_evitado_MMBtu"] is not None:
                cols.append(("en", "Gas evitado por la cascada (MMBtu)", "num", 1))
            elif T[-1]["biomasa_evitada_t"] is not None:
                cols.append(("en", "Biomasa evitada por la cascada (t)", "num", 2))
            cols += [("mant", "Mantenimiento", "txt", 0), ("ev", "Eventos", "txt", 0)]
            C.mostrar_tabla(filas[::-1], cols)
        else:
            st.markdown("#### Turnos ejecutados")
            st.caption("Todavía no se ejecutan turnos.")
    with der:
        C.ayuda("La calidad y la disponibilidad cambian con el uso; los resultados de laboratorio llegan uno o dos "   # PAT 134
                "turnos después de tomar la muestra.", "Materiales, mantenimiento y perturbaciones")
        i1, i2 = st.columns(2)
        stock = op.stock if op.stock is not None else OP.S["stock_inicial"] * ln["alimentacion"] * OP.S["horas_turno"]
        i1.metric("Materia prima en el patio", C.fmt(stock) + " t")
        i2.metric("Producto conforme en bodega", C.fmt(op.terminado) + " t")
        st.markdown("##### Eventos del turno más reciente")
        if T:
            st.info("\n\n".join(T[-1]["eventos"]))
        else:
            st.info("Ejecute la operación para recibir información de la planta.")
        st.markdown("##### Mediciones disponibles en línea")
        crit = ln["critico"]; est = ln["estados"].get(crit) if crit else None
        m1, m2 = st.columns(2); m3, _m4 = st.columns(2)
        m1.metric("Producción posible", C.fmt(ln["real"], 2) + " t/h", help=f"Planificada: {C.fmt(ln['plan'], 2)} t/h")
        m2.metric("Equipo crítico", f"{crit} · {C.fmt(est, 3)}" if crit else "—",
                  help="Restricción de la teoría de restricciones (capacidades declaradas en Diseño) o, sin capacidades, el equipo más gastado; "
                       "el número es su estado (1 = buen estado).")
        m3.metric("Conformidad esperada", C.pct(OP.conformidad(pl)))
        if not ln["con_capacidades"]:
            st.caption("Sin capacidades declaradas, la producción posible es la planificada por el estado del equipo más gastado. Use «Asignar "
                       "capacidades» en el lienzo de Diseño para que la restricción y el mantenimiento se vean en la teoría de restricciones.")
        vs = Q.variables(pl)
        if vs:
            st.markdown('<span class="nota">' + " · ".join(f"{v.nombre}: <b>{C.fmt(v.media, v.decimales)} {v.unidad}</b>" for v in vs[:3])
                        + "</span>", unsafe_allow_html=True)
        C.ayuda("La demanda varía por turno según la semilla del estudiante; no es un mercado de precios.", "Demanda variable", 5)   # PAT 134
        dem = [OP.demanda(op, op.turno + i, ln["plan"] * OP.S["horas_turno"]) for i in range(1, 13)]
        st.image(OP.grafico_demanda(dem, f"Demanda de {pr} en los próximos 12 turnos (t por turno)"), width="stretch")
        if T and T[-1]["gas_evitado_MMBtu"] is not None:
            g = sum(x["gas_evitado_MMBtu"] or 0 for x in T); co2 = sum(x["co2_evitado_t"] or 0 for x in T)
            precio = ss.economia["precio_gas"]; dolar = ss.economia["dolar"]
            e1, e2 = st.columns(2)
            e1.metric("Gas evitado por la cascada en los turnos", C.fmt(g, 1) + " MMBtu", help="Calor de la cascada × horas de los turnos, a la producción de cada turno")
            e2.metric("Valor del gas evitado", C.esc("$" + C.fmt(g * precio * dolar / 1e6, 2) + " MM"),
                      help=C.esc(f"Al precio de la pestaña Economía: {C.fmt(precio, 2)} US$/MMBtu y {C.fmt(dolar, 2)} $/US$. CO2 evitado: {C.fmt(co2, 1)} t."))
    with st.expander("Estado de los equipos (desgaste y mantenimiento)", expanded=False):
        filas = [dict(eq=k, nombre=pl.equipos[k].nombre, estado=v, util=100 * ln["util"][k]["util_demanda"] if ln["util"].get(k, {}).get("util_demanda") else None)
                 for k, v in ln["estados"].items()]
        AT.tabla("op_estado", "Estado y utilización por equipo")   # PAT 134: «?» de la tabla
        C.mostrar_tabla(filas, [("eq", "Equipo", "txt", 0), ("nombre", "Nombre", "txt", 0), ("estado", "Estado", "num", 3), ("util", "Utilización (%)", "num", 1)])
        st.caption("El estado baja entre 0,002 y 0,004 por turno hasta 0,65; el mantenimiento lo sube en el equipo crítico. Es el mismo estado de la pestaña Diseño.")
    with st.expander("Supuestos de la operación y del laboratorio", expanded=False):
        AT.tabla("op_supuestos", "Supuestos")   # PAT 134: «?» de la tabla
        C.mostrar_tabla([dict(n=s.nombre, v=C.fmt(s.valor, 3).rstrip("0").rstrip(","), u=s.unidad, j=s.justificacion)
                         for s in OP.SUPUESTOS.values()],
                        [("n", "Supuesto", "txt", 0), ("v", "Valor", "cen", 0), ("u", "Unidad", "txt", 0), ("j", "Justificación", "txt", 0)])
