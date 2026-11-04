"""Pestaña Instrumentación: lazos ISA-5.1 (validación de letras), símbolos por ubicación y diagrama de lazo con la estructura de ISA-5.4.

PAT 134: muestra también los instrumentos y elementos ISA-5.4 agregados en el lienzo de Diseño, con su símbolo y sus líneas de
señal; el diagrama de lazo se elige por número de lazo (pat_sim.motor.instrumentacion.lazos) y toma la caja de conexiones unida
en el lienzo."""
from __future__ import annotations
import streamlit as st
from pat_sim.motor.planta import Instrumento
from pat_sim.simbolos import isa51, isa54
from pat_sim.motor import instrumentacion as IN
from . import comun as C
from . import ayudas_tablas as AT   # PAT 134: «?» de cada tabla


def mostrar():
    pl = C.planta()
    C.ayuda("Identificación y símbolos según ISA-5.1 (tutorial de Carballo y Romero, 2011: Tablas 3, 4, 15 y 17); "   # PAT 134: ayuda «?»
            "el diagrama de lazo sigue la estructura de ISA-5.4. Ambas normas actuales son pagadas y no están en la carpeta del proyecto: "
            "el diagrama de lazo es una versión simplificada y así se declara.", "Instrumentación", 3)

    AT.tabla("ins_lazos", "Lazos de la planta", 4, antes="Los instrumentos y las líneas de señal también se agregan, mueven y conectan "   # PAT 134
             "en el lienzo de Diseño (catálogo «Instrumentación ISA-5.1 y ISA-5.4»).")
    if pl.instrumentos:
        filas = []
        for i in pl.instrumentos:
            sen = ", ".join(f"{isa51.SENALES.get(x.get('senal'), ('?',))[0].lower()} a {x.get('destino')}" for x in i.conexiones if isinstance(x, dict))
            filas.append(dict(tag=isa51.tag(i.letras, i.numero), sim=isa51.NOMBRE_SIMBOLO.get(i.simbolo, i.simbolo), eq=i.equipo or "—",
                              ub=isa51.UBICACIONES.get(i.ubicacion, i.ubicacion), d=IN.lectura(i),
                              desc=i.descripcion, par=i.parametro or "—", fin=i.elemento_final or "—", sen=sen or "—"))
        C.mostrar_tabla(filas, [("tag", "Identificación", "txt", 0), ("sim", "Símbolo", "txt", 0), ("eq", "Equipo", "txt", 0), ("ub", "Ubicación", "txt", 0),
                                ("d", "Lectura ISA-5.1", "txt", 0), ("desc", "Descripción", "txt", 0), ("par", "Parámetro que gobierna", "txt", 0),
                                ("fin", "Elemento final", "txt", 0), ("sen", "Líneas de señal (lienzo)", "txt", 0)])
    else:
        st.info("La planta no tiene lazos de instrumentación todavía.")

    st.markdown("#### Agregar un lazo")
    with st.form("form_lazo"):
        a, b, c = st.columns(3)
        letras = a.text_input("Letras de identificación (1 a 5)", "TIC", help="Primera letra: variable medida; las siguientes: función (I indicador, C controlador, T transmisor…)")
        numero = b.text_input("Número de lazo", "")
        eqid = c.selectbox("Equipo", list(pl.equipos) or ["—"], format_func=lambda k: f"{k} · {pl.equipos[k].nombre}" if k in pl.equipos else k)
        d, e, f = st.columns(3)
        ub = d.selectbox("Ubicación (símbolo)", list(isa51.UBICACIONES), index=list(isa51.UBICACIONES).index("dcs"), format_func=lambda k: isa51.UBICACIONES[k])
        params = ["—"] + (list(pl.equipos[eqid].params) if eqid in pl.equipos else [])
        par = e.selectbox("Parámetro que gobierna", params)
        fin = f.text_input("Elemento final de control", "", help="Por ejemplo TV-101")
        desc = st.text_input("Descripción", "")
        ok = st.form_submit_button("Agregar lazo", type="primary")
    if letras.strip():
        try:
            st.caption("Lectura: " + isa51.interpretar(letras)["descripcion"])
        except ValueError as ex:
            st.caption(f":red[{ex}]")
    if ok:
        try:
            isa51.interpretar(letras)
            if not numero.strip():
                raise ValueError("Falta el número de lazo")
            if any(i.letras.upper() == letras.strip().upper() and i.numero == numero.strip() for i in pl.instrumentos):
                raise ValueError(f"Ya existe el lazo {isa51.tag(letras, numero.strip())}")
            pl.instrumentos.append(Instrumento(letras.strip().upper(), numero.strip(), eqid, ub, desc, None if par == "—" else par, fin.strip() or None))
            st.success(f"Lazo {isa51.tag(letras, numero.strip())} agregado.")
            st.rerun()
        except ValueError as ex:
            st.error(str(ex))

    if pl.instrumentos:
        q = st.selectbox("Quitar un lazo", range(len(pl.instrumentos)), format_func=lambda i: f"{isa51.tag(pl.instrumentos[i].letras, pl.instrumentos[i].numero)} · {pl.instrumentos[i].equipo}", key="ins_del")
        if st.button("Quitar lazo"):
            IN.quitar(pl, IN.ident(pl.instrumentos[q])); st.rerun()      # PAT 134: también sus líneas de señal

    lz = IN.lazos(pl)
    if lz:
        st.markdown("#### Diagrama de lazo (estructura de ISA-5.4)")
        i = st.selectbox("Lazo", range(len(lz)), key="ins_ver",
                         format_func=lambda k: f"Lazo {lz[k]['numero']} · {IN.ident(lz[k]['representante'])}"
                         + (f" · {lz[k]['representante'].descripcion}" if lz[k]['representante'].descripcion else "")
                         + (f" ({len(lz[k]['miembros'])} instrumentos)" if len(lz[k]['miembros']) > 1 else ""))
        L = lz[i]; ins = L["representante"]
        c1, c2 = st.columns(2)
        caja = c1.text_input("Caja de conexiones", L["caja"] or "JB-1", key=f"ins_caja_{L['numero']}"); senal = c2.text_input("Señal", "4-20 mA")
        try:
            ub = ins.ubicacion if ins.ubicacion in isa51.UBICACIONES else "dcs"
            if ins.simbolo in isa51.FUNCIONES:                 # PAT 134: tipo de burbuja del lienzo → forma del controlador
                ub = {"compartido": "dcs", "plc": "plc", "computador": "computador"}.get(ins.simbolo, ins.ubicacion)
            svg = isa54.lazo_svg(ins.letras, ins.numero, ins.descripcion, ins.equipo, ub, caja, senal)
            st.image(svg)
            st.download_button("Descargar el diagrama de lazo (SVG)", svg, file_name=f"Lazo_ISA54_{ins.letras}{ins.numero}.svg", mime="image/svg+xml")
        except ValueError as ex:
            st.error(str(ex))
        if L["senales"] or len(L["miembros"]) > 1:
            st.caption("Instrumentos del lazo: " + ", ".join(IN.ident(m) for m in L["miembros"]))
            AT.tabla("ins_senales", "Señales del lazo")   # PAT 134: «?» de la tabla
            C.mostrar_tabla([dict(o=x["origen"], s=isa51.SENALES.get(x.get("senal"), ("?",))[0], d=x.get("destino"), p=x.get("parametro") or "—")
                             for x in L["senales"]],
                            [("o", "Desde", "txt", 0), ("s", "Señal ISA-5.1", "txt", 0), ("d", "Hasta", "txt", 0), ("p", "Parámetro", "txt", 0)])

    with st.expander("Referencia ISA-5.1: letras, ubicaciones y líneas de señal"):
        a, b = st.columns(2)
        with a:
            AT.tabla("ins_primera", "Primera letra")   # PAT 134: «?» de la tabla
            C.mostrar_tabla([dict(l=k, d=v) for k, v in isa51.PRIMERA_LETRA.items()], [("l", "Primera letra", "txt", 0), ("d", "Variable medida", "txt", 0)])
        with b:
            AT.tabla("ins_sucesivas", "Letras sucesivas")   # PAT 134: «?» de la tabla
            C.mostrar_tabla([dict(l=k, d=v) for k, v in isa51.LETRAS_SUCESIVAS.items()], [("l", "Letra sucesiva", "txt", 0), ("d", "Función", "txt", 0)])
        st.markdown("**Símbolos por ubicación (Tabla 4)**")
        cols = st.columns(len(isa51.UBICACIONES))
        for col, (k, nombre) in zip(cols, isa51.UBICACIONES.items()):
            svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">{isa51.burbuja("TIC", "101", 32, 32, k, r=20)}</svg>'
            col.image(svg, width=64); col.caption(nombre)
        st.markdown("**Líneas de señal (Tabla 15; la electromagnética o sónica, según ISA-5.1 sin número de tabla)**")
        cols = st.columns(len(isa51.SENALES))
        for col, (k, (nombre, _a, _b)) in zip(cols, isa51.SENALES.items()):
            svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="110" height="24" viewBox="0 0 110 24">{isa51.linea(5, 12, 105, 12, k)}</svg>'
            col.image(svg, width=110); col.caption(nombre)
        st.markdown("**Catálogo del lienzo de Diseño (PAT 134): burbujas, elementos primarios y finales, y elementos de lazo ISA-5.4**")
        cat = IN.catalogo()
        for g in dict.fromkeys(c["grupo"] for c in cat):
            st.caption(g)
            cs = [c for c in cat if c["grupo"] == g]
            for j in range(0, len(cs), 8):
                cols = st.columns(8)
                for col, c in zip(cols, cs[j:j + 8]):
                    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="72" height="80" viewBox="-30 -26 60 66">{c["svg"]}</svg>'
                    col.image(svg, width=64); col.caption(f"{c['letras']} · {c['nombre']}")
