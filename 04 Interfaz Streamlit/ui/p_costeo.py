"""Pantalla Costeo de la planta (PAT 135, tarea T7.1, 04-11-2026): lista completa de equipos con su precio (internet con
Tavily, último precio guardado o bibliografía), escalamiento de Williams, actualización con el CEPCI e inversión total que se
lleva a Economía. Indicación 1 del profesor Torres en la reunión del 04-11-2026. Motor: pat_sim/motor/costeo.py y
pat_sim/datos/precios_web.py.
PAT 136, T24: sistemas de costeo con factores de literatura (factor único, Lang, Hand, módulo desnudo y desglose por ítems),
comparación de métodos y mantención anual con su fuente (motor: pat_sim/motor/factores_costo.py). Claves nuevas con «cos_».
PAT 142 (pedido de Jaime del 19-11-2026): internación de los equipos importados por país de origen (aduana, contenedor,
impuestos), banda de error de la clase de estimación y traspaso a Economía (motor: pat_sim/motor/internacion.py). Claves «cos_int_»."""
from __future__ import annotations
import streamlit as st
from pat_sim.motor import costeo as CT, costos, factores_costo as FC, internacion as INT
from pat_sim.datos import precios_web as PW
from . import comun as C


def _alternativa(pl):
    """PAT 135: la misma alternativa de recuperación que evalúa Economía (la elegida o la ganadora del multicriterio)."""
    try:
        from . import p_alternativas as PA
        r = C.resumen_actual()
        if r.get("sin_sumidero"):
            return None, None
        X = PA.alternativas_sesion(pl, r)
        return X, PA.elegida(X)
    except Exception:
        return None, None


def _tam(v, u, d=1):
    if v is None:
        return "—"
    if u == "mm":
        return f"DN {int(round(v))} ({CT.pulgadas(int(round(v)))}\")"
    return f"{C.fmt(v, d)} {u.replace('m2', 'm²')}"


def _ayuda():
    with st.expander("? Cómo se hace el costeo, para qué y por qué"):
        st.markdown(C.esc(
            "**Cómo.** La lista sale de la planta resuelta: equipos de la línea, recuperadores de calor de la alternativa que evalúa "
            "Economía, caldera o generador a biomasa, una bomba por línea de líquido (potencia de la red hidráulica), una válvula por "
            "lazo de control (Cv por ISA-75.01) y las cañerías por diámetro nominal (largo del layout o 30 m por línea, Supuesto). "
            "El precio viene de internet (Tavily), del último precio guardado o de una correlación de bibliografía. Si el tamaño "
            "encontrado no es el requerido se escala con Williams, C2 = C1·(S2/S1)^n, y si el precio es de otro año se actualiza "
            "con el CEPCI, C = C_año·(CEPCI_hoy/CEPCI_año). La planta instalada sale del costo de los equipos con el sistema de "
            f"costeo elegido: factor único {C.fmt(costos.F_INSTALACION, 1)} de motor/costos.py (por defecto), Lang por tipo de planta, "
            "Hand por tipo de equipo, módulo desnudo de Guthrie y Turton o desglose por ítems de Peters y Timmerhaus, cada uno con "
            "su fuente. La mantención anual y los otros costos fijos salen como porcentaje de la inversión.\n\n"
            "**Para qué.** Es la inversión que entra a la evaluación económica (VAN y TIR).\n\n"
            "**Por qué.** Los precios de equipos industriales casi nunca se publican: se combina lo que hay en internet con "
            "bibliografía, se deja la fuente, la fecha y la URL de cada cifra y se marca su origen. Las referencias marcadas "
            "Supuesto son órdenes de magnitud que se reemplazan con la búsqueda o con una cotización."))


def mostrar():
    ss = st.session_state; pl = C.planta(); E = ss.economia
    st.subheader("Costeo de la planta")
    _ayuda()
    if not pl.equipos:                        # PAT 136: planta vacía (desafío en blanco)
        st.info("La planta está vacía: agregue equipos en Diseño para costearla y comparar los métodos de costeo.")
        return
    if not C.exigir_resuelta():
        return
    P = ss.setdefault("costeo_param", dict(cepci=CT.CEPCI_HOY, anio=CT.ANIO_CEPCI_HOY))
    with st.form("cst_form"):
        a, b, c = st.columns(3)
        cepci = a.number_input("CEPCI actual", 100.0, 5000.0, float(P["cepci"]), 0.1, key="cst_cepci",
                               help=C.esc(f"Por defecto 797,9, promedio anual 2023 ({CT.FUENTE_CEPCI_ANUAL}). El promedio 2025 subió 1,6 % "
                                          "sobre el de 2024 (Chemical Engineering, 02-04-2026), pero su valor solo se publica con suscripción."))
        anio = b.number_input("Año del CEPCI", 2000, 2100, int(P["anio"]), 1, key="cst_anio")
        dolar = c.number_input(C.esc("Dólar observado ($/US$)"), 1.0, 5000.0, float(E["dolar"]), 1.0, key="cst_dolar", help=C.FUENTE_DOLAR)
        if st.form_submit_button("Aplicar", type="primary"):
            P.update(cepci=float(cepci), anio=int(anio)); E["dolar"] = float(dolar)
    clave = PW.obtener_clave()
    buscar = st.button("Buscar precios en internet", key="cst_buscar", disabled=not clave,
                       help="Una búsqueda de Tavily por equipo (plan gratuito: 1.000 al mes). Cada precio queda guardado en la base con su fecha.")
    if not clave:
        st.caption("Sin clave de Tavily: se usan los precios guardados y la bibliografía. La clave va en `.streamlit/secrets.toml` "
                   "(TAVILY_API_KEY) o en la variable de entorno TAVILY_API_KEY.")
    X, k_alt = _alternativa(pl)
    lay = C.layout_vigente(pl) or {}          # PAT 137 (estado único): largos al día con la planta, no de una versión anterior
    longitudes = lay.get("longitudes_m") if isinstance(lay, dict) else None
    cables_m = lay.get("cables_m") if isinstance(lay, dict) else None   # PAT 135, T14: red eléctrica del layout (equipo S)
    try:
        bd = C.obtener_bd()
    except Exception:
        bd = None
    M = _opciones_metodo()                    # PAT 136, T24: sistema de costeo y costos fijos de operación
    try:
        res = CT.costear(pl, cepci_hoy=float(P["cepci"]), anio_cepci=int(P["anio"]), dolar=float(E["dolar"]), bd=bd,
                         buscar=bool(buscar and clave), clave=clave, longitudes=longitudes, alternativa=k_alt, X=X,
                         cables_m=cables_m if isinstance(cables_m, dict) else None, metodo=M["metodo"],
                         mantencion_pct=M["om"]["mantencion"], opciones_metodo=M["opciones"])
    except Exception as e:                    # el costeo nunca debe botar la aplicación
        st.error(f"No se pudo costear la planta: {e}")
        return
    IC = _cfg_internacion(ss)                 # PAT 142: internación guardada (se cambia en su sección, más abajo)
    res0 = res
    res = INT.agregar(res, IC, pl)
    t = res["totales"]; mc = res["metodo_costeo"]
    op = FC.operacion_fija(t["total_usd"], **{f"{k}_pct": v for k, v in M["om"].items()})
    ss["costeo"] = {"version": C.version_planta(), "total_clp": t["total_clp"], "filas": res["filas"], "totales": t, "metodo": M["metodo"],
                    "metodo_nombre": mc["nombre"], "fuente_metodo": mc["fuente"], "om_anual_clp": op["total"] * float(E["dolar"]),
                    "mantencion_clp": op["mantencion"] * float(E["dolar"])}
    if k_alt:
        st.caption(f"Recuperadores de la alternativa {k_alt}, la que evalúa Economía (se cambia en Alternativas).")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Equipos", C.esc("$" + C.fmt(t["equipos_clp"] / 1e6, 1) + " M"), f"US$ {C.fmt(t['equipos_usd'] / 1e6, 2)} M", delta_color="off")
    m2.metric(f"Instalación (factor {C.fmt(t['f_inst'], 2 if M['metodo'] != 'factor_unico' else 1)})",
              C.esc("$" + C.fmt(t["instalacion_clp"] / 1e6, 1) + " M"))
    m3.metric("Total planta", C.esc("$" + C.fmt(t["total_clp"] / 1e6, 1) + " M"), f"US$ {C.fmt(t['total_usd'] / 1e6, 2)} M", delta_color="off")
    m4.metric("Origen de los precios", f"{res['n_internet']} de internet", f"{res['n_bibliografia']} de bibliografía", delta_color="off")
    _banda(t["total_clp"], res)               # PAT 142: banda de error de la clase de estimación
    filas = [dict(f, nombre_txt=f"{f['equipo']} · {f['nombre']}", req=_tam(f["tamano"], f["unidad"]) + (f" × {C.fmt(f['cantidad'], 0)} m" if f["unidad"] in ("mm", "mm2") else "")
                  + (f" × {f['unidades']} unidades" if f.get("unidades") else ""),   # PAT 135, T14: unidades en paralelo
                  ref=_tam(f["tamano_ref"], f["unidad"]), anio_txt=str(f["anio"] or "—"), url_txt=f["url"] or "—") for f in res["filas"]]
    C.mostrar_tabla(filas, [("nombre_txt", "Equipo", "txt", 0), ("tipo", "Tipo", "txt", 0), ("req", "Tamaño requerido", "cen", 0),
                            ("ref", "Tamaño de referencia", "cen", 0), ("precio_ref_usd", "Precio de referencia (US$)", "mm", 0),
                            ("anio_txt", "Año", "cen", 0), ("n", "Williams n", "num", 2), ("factor_cepci", "Factor CEPCI", "num", 3),
                            ("costo_usd", "Costo actualizado (US$)", "mm", 0), ("costo_clp", "Costo actualizado ($)", "clp", 0),
                            ("fuente", "Fuente", "txt", 0), ("fecha", "Fecha", "txt", 0), ("url_txt", "URL", "txt", 0), ("origen", "Origen", "txt", 0)])
    notas = [f"{f['equipo']}: {f['nota']}" for f in res["filas"] if f.get("nota")] + res["avisos"]
    if notas:
        with st.expander(f"Notas y supuestos de cada fila ({len(notas)})"):
            st.markdown(C.esc("\n".join(f"- {n}" for n in notas)))
    _internacion(pl, res0, res, IC, float(E["dolar"]))   # PAT 142
    _desglose(mc, float(E["dolar"]))
    _comparacion(pl, res0, M, float(E["dolar"]))
    _operacion(op, M, float(E["dolar"]))
    st.markdown("#### Llevar a Economía")
    que = st.radio("Inversión que se lleva", ["Planta completa", "Solo recuperación de calor"], horizontal=True, key="cst_que",
                   help="Economía evalúa el ahorro de la recuperación de calor: para ese VAN corresponde la inversión de los recuperadores.")
    total = t["total_clp"] if que == "Planta completa" else t["recuperacion_clp"]
    lleva = INT.resumen_llevar(res, "planta" if que == "Planta completa" else "recuperacion")   # PAT 142: internación e IVA
    ter = next((d["usd"] for d in mc.get("desglose", []) if d.get("clave") == "terreno"), 0.0) if que == "Planta completa" else 0.0
    op_llevar = FC.operacion_fija(total, **{f"{k}_pct": v for k, v in M["om"].items()})   # costos fijos sobre la inversión que se lleva
    st.caption(C.esc(f"Método: {mc['nombre']}. Se escribirá ${C.fmt(total / 1e6, 1)} M como inversión (M$) y se desmarcará «Usar la "
                     "inversión estimada de la alternativa evaluada». La mantención y los costos fijos de esa inversión suman "
                     f"${C.fmt(op_llevar['total'] / 1e6, 1)} M por año."
                     + (f" La inversión incluye ${C.fmt(lleva['extra_m'], 1)} M de internación de {lleva['n_importados']} equipos importados."
                        if lleva["extra_m"] > 0 else "")))
    a, b = st.columns(2)
    if a.button("Llevar a Economía", key="cst_llevar", type="primary"):
        E["inversion"] = round(total / 1e6, 1); E["inv_auto"] = False
        E["metodo_costeo"] = mc["nombre"]; E["fuente_metodo_costeo"] = mc["fuente"]     # PAT 136: trazabilidad del método
        # PAT 142: lo que el flujo de caja con impuestos de Economía necesita de esta inversión (campos nuevos con valor por defecto)
        E.update(inv_costeo_m=E["inversion"], internacion_m=round(lleva["extra_m"], 3), arancel_m=round(lleva["arancel_m"], 3),
                 iva_internacion_m=round(lleva["iva_internacion_m"], 3), terreno_m=round(ter * float(E["dolar"]) / 1e6, 3),
                 clase_estimacion=ss["costeo_param"].get("clase", INT.CLASE_DEF))
        ss["eco_inv_auto"] = False; ss["eco_inv_auto_b"] = False      # las casillas de Economía muestran lo mismo
        ss["costeo"]["llevado_mmclp"] = E["inversion"]
        st.success(C.esc(f"Inversión de ${C.fmt(E['inversion'], 1)} M llevada a Economía ({mc['nombre']})."))
    if b.button("Llevar la mantención y los costos fijos a Economía", key="cos_llevar_om",
                help="Escribe la suma anual en «Costo anual de operación y mantención (M$)» de Economía."):
        E["costo_anual"] = round(op_llevar["total"] / 1e6, 1)
        ss["costeo"]["om_llevado_mmclp"] = E["costo_anual"]
        st.success(C.esc(f"Costo anual de ${C.fmt(E['costo_anual'], 1)} M llevado a Economía."))


# ---------------------------------------------------------------- PAT 136, T24: sistemas de costeo
_NOMBRES = {k: v["nombre"] for k, v in FC.METODOS.items()}
_TIPOS = {"auto": "Automático (según los equipos)", **FC.TIPOS_PLANTA}


def _opciones_metodo() -> dict:
    """Selector del sistema de costeo, sus opciones y los porcentajes de mantención y costos fijos (claves «cos_»)."""
    st.markdown("#### Sistema de costeo")
    C.ayuda(C.esc("Factor único: costo de equipos por 2,5 (Supuesto de motor/costos.py). Lang: un factor por tipo de planta. Hand: un "
                  "factor por tipo de equipo. Módulo desnudo: costo base por F_BM = B1 + B2·FM·FP de cada familia, más 18 % de "
                  "contingencias y honorarios y 50 % de instalaciones auxiliares en una planta nueva. Desglose: cada ítem de la planta "
                  "como porcentaje de los equipos. Los cuatro métodos de literatura ya incluyen cañerías y sistema eléctrico, por eso "
                  "dejan fuera de la base la cañería y el cable de la lista. Cada factor muestra su fuente; los marcados Supuesto no "
                  "se pudieron verificar."), "Cómo se elige")
    a, b = st.columns(2)
    metodo = a.selectbox("Método", list(_NOMBRES), format_func=lambda k: _NOMBRES[k], key="cos_metodo",
                         help="El factor único es el de siempre; los demás llevan factores de literatura con su fuente.")
    tipo = b.selectbox("Tipo de planta (Lang y desglose)", list(_TIPOS), format_func=lambda k: _TIPOS[k], key="cos_tipo",
                       help="Automático: fluidos si 70 % o más del costo de los equipos de proceso maneja fluidos, sólidos si es 30 % "
                            "o menos y mixta entre ambos (Supuesto de T24).")
    opc = dict(tipo=None if tipo == "auto" else tipo)
    if metodo == "lang":
        opc["lang_fuente"] = st.selectbox("Juego de factores de Lang", list(FC.LANG), format_func=lambda k: FC.LANG[k]["nombre"],
                                          key="cos_lang_fuente", help=FC.LANG["original"]["fuente"])
    elif metodo == "modulo_desnudo":
        c1, c2, c3 = st.columns(3)
        opc["material"] = c1.radio("Material", list(FC.MATERIALES), format_func=lambda k: FC.MATERIALES[k], index=1,
                                   horizontal=True, key="cos_material")
        opc["P_barg"] = float(c2.number_input("Presión de diseño (barg)", 0.0, 200.0, 0.0, 1.0, key="cos_presion",
                                              help="Bajo el rango de cada correlación el factor de presión es 1."))
        opc["precio_en_material"] = bool(c3.checkbox("Los precios ya son del material elegido", value=True, key="cos_precio_material",
                                                     help="Supuesto: los precios de la aplicación son de equipos de acero inoxidable; "
                                                          "entonces Cp0 = Cp/(FM·FP)."))
        opc["ampliacion"] = bool(st.checkbox("Ampliación en un sitio existente (sin instalaciones auxiliares)", value=False,
                                             key="cos_ampliacion"))
    elif metodo == "desglose":
        opc["incluir_terreno"] = bool(st.checkbox("Incluir la compra del terreno (6 %)", value=True, key="cos_terreno"))
    with st.expander("Mantención y costos fijos de operación (% de la inversión)"):
        cols = st.columns(4); om = {}
        for col, k in zip(cols, ("mantencion", "suministros", "seguros", "impuestos")):
            d, rango, base, fuente, _cat = FC.OM[k]
            om[k] = float(col.number_input(f"{FC.OM_NOMBRES[k]} (% de {base})", 0.0, 50.0, float(d), 0.5, key=f"cos_om_{k}",
                                           help=C.esc(f"Rango de literatura {C.fmt(rango[0], 1)} a {C.fmt(rango[1], 1)} %. {fuente}")))
    return dict(metodo=metodo, opciones=opc, om=om)


def _desglose(mc: dict, dolar: float):
    st.markdown(f"#### Desglose: {mc['nombre']}")
    st.caption(C.esc(f"{mc['tipo_planta']['nombre']} ({mc['tipo_planta']['justificacion']}). Fuente del método: {mc['fuente']} "
                     f"({mc['categoria']})."))
    filas = []
    for d in mc["desglose"]:
        fac = d.get("porcentaje")
        filas.append(dict(item=d["item"], fac=(C.fmt(fac, 0) + " %") if fac is not None else C.fmt(d.get("factor"), 2),
                          usd=d["usd"], clp=d["usd"] * dolar, fuente=d.get("fuente", "") + (f" ({d['categoria']})" if d.get("categoria") else "")))
    filas.append(dict(item="Total de la planta", fac=C.fmt(mc["factor_efectivo"], 2), usd=mc["total_usd"], clp=mc["total_usd"] * dolar,
                      fuente="Suma"))
    C.mostrar_tabla(filas, [("item", "Ítem", "txt", 0), ("fac", "Porcentaje o factor", "cen", 0), ("usd", "US$", "mm", 0),
                            ("clp", "$", "clp", 0), ("fuente", "Fuente", "txt", 0)])
    if mc["avisos"]:
        st.caption(C.esc(" ".join(mc["avisos"][:4])))


def _comparacion(pl, res: dict, M: dict, dolar: float):
    st.markdown("#### Comparación de métodos para la misma planta")
    try:
        cmp_ = CT.comparar_metodos(pl, opciones_metodo=M["opciones"], mantencion_pct=M["om"]["mantencion"], res=res)
    except Exception as e:
        st.warning(f"No se pudo comparar los métodos: {e}")
        return
    for a in cmp_["avisos"]:
        if "vacía" in a or "Resuelva" in a:
            st.info(a)
    filas = [dict(r, elegido="●" if r["metodo"] == M["metodo"] else "", tot_m=r["total_usd"] * dolar / 1e6,
                  man_m=r["mantencion_usd"] * dolar / 1e6, dif=("—" if r["diferencia_pct"] is None else C.fmt(r["diferencia_pct"], 1) + " %"),
                  fuente_txt=f"{r['fuente']} ({r['categoria']})") for r in cmp_["filas"]]
    C.mostrar_tabla(filas, [("elegido", "", "cen", 0), ("nombre", "Método", "txt", 0), ("factor_efectivo", "Factor sobre equipos", "num", 2),
                            ("total_usd", "Inversión total (US$)", "mm", 0), ("tot_m", "Inversión total (M$)", "mm", 1),
                            ("dif", "Diferencia con el factor único", "cen", 0), ("man_m", "Mantención anual (M$)", "mm", 1),
                            ("fuente_txt", "Fuente", "txt", 0)])


def _operacion(op: dict, M: dict, dolar: float):
    st.markdown("#### Mantención anual y costos fijos de operación")
    filas = [dict(f, pct_txt=C.fmt(f["pct"], 1) + " % de " + f["base"], rango_txt=f"{C.fmt(f['rango'][0], 1)} a {C.fmt(f['rango'][1], 1)} %",
                  usd=f["monto"], clp=f["monto"] * dolar, cat=f["categoria"] + (" (fuera del rango)" if f["fuera_de_rango"] else ""))
             for f in op["filas"]]
    filas.append(dict(item="Total anual", pct_txt="", rango_txt="", usd=op["total"], clp=op["total"] * dolar, fuente="Suma", cat=""))
    C.mostrar_tabla(filas, [("item", "Costo", "txt", 0), ("pct_txt", "Porcentaje", "cen", 0), ("rango_txt", "Rango de literatura", "cen", 0),
                            ("usd", "US$ por año", "mm", 0), ("clp", "$ por año", "clp", 0), ("fuente", "Fuente", "txt", 0),
                            ("cat", "Categoría", "txt", 0)])


# ---------------------------------------------------------------- PAT 142: internación y clase de estimación
_PAISES = list(INT.PAISES)


def _acuerdos() -> dict:
    """Acuerdo comercial → países que cubre (para la ayuda, sin repetir el mismo acuerdo)."""
    out = {}
    for p, (ac, _r) in INT.PAISES.items():
        if ac:
            out.setdefault(ac, []).append(p)
    return out


def _cfg_internacion(ss) -> dict:
    """Configuración de la internación guardada con el proyecto (costeo_param), con sus valores por defecto si falta."""
    P = ss.setdefault("costeo_param", dict(cepci=CT.CEPCI_HOY, anio=CT.ANIO_CEPCI_HOY))
    IC = P.setdefault("internacion", {})
    for k, v in (("activa", False), ("sumar_montaje", False), ("parametros", {}), ("equipos", {})):
        IC.setdefault(k, v)
    return IC


def _banda(total_clp: float, res: dict):
    """Banda de error de la clase de estimación de la AACE sobre el total de la planta."""
    P = st.session_state["costeo_param"]
    claves = list(INT.CLASES)
    a, b = st.columns([1, 3])
    clase = a.selectbox("Clase de estimación", claves, index=claves.index(P.get("clase", INT.CLASE_DEF)) if P.get("clase", INT.CLASE_DEF) in claves else 1,
                        format_func=lambda k: f"{INT.CLASES[k][0]} ({C.fmt(INT.CLASES[k][1] * 100, 0)} a {C.fmt(INT.CLASES[k][2] * 100, 0)} %)",
                        key="cos_clase", help=C.esc(f"{INT.FUENTE_CLASES}. Por defecto: {INT.JUST_CLASE}."))
    P["clase"] = clase
    bd = INT.banda(total_clp, clase)
    b.markdown(C.esc(f"**Banda de error ({bd['nombre'].lower()}, ± {C.fmt(bd['error_max'] * 100, 0)} %):** el total de la planta queda "
                     f"entre ${C.fmt(bd['bajo'] / 1e6, 1)} M y ${C.fmt(bd['alto'] / 1e6, 1)} M"
                     + (f"; incluye ${C.fmt(res['totales']['internacion_clp'] / 1e6, 1)} M de internación." if res.get("internacion") else ".")))


def _fila_editor(f, cfg):
    return {"Equipo": f["equipo"], "Nombre": f["nombre"], "País de origen": cfg["pais"], "Incoterm": cfg["incoterm"], "Carga": cfg["carga"],
            "Contenedores": int(cfg["n_cont"]), "Peso (t)": float(cfg["peso_t"]), "Gastos en origen (US$)": float(cfg.get("gastos_origen_usd") or 0.0),
            "Flete cotizado (US$)": cfg.get("flete_usd"), "Prueba de origen": bool(cfg["prueba_origen"]),
            "Bien de capital (Ley 18.634)": bool(cfg["bien_capital"]), "Usado": bool(cfg["usado"])}


_COLS_EDITOR = {"País de origen": "pais", "Incoterm": "incoterm", "Carga": "carga", "Contenedores": "n_cont", "Peso (t)": "peso_t",
                "Gastos en origen (US$)": "gastos_origen_usd", "Flete cotizado (US$)": "flete_usd", "Prueba de origen": "prueba_origen",
                "Bien de capital (Ley 18.634)": "bien_capital", "Usado": "usado"}


def _desde_editor(filas_df: list[dict], defectos: dict) -> dict:
    """Configuración por equipo desde las filas del editor: solo se guarda lo que difiere del valor por defecto."""
    out = {}
    for r in filas_df:
        eid = str(r.get("Equipo")); d = defectos.get(eid, {})
        cfg = {}
        for col, k in _COLS_EDITOR.items():
            v = r.get(col)
            try:
                if v is not None and isinstance(v, float) and v != v:      # NaN de una celda vacía
                    v = None
            except Exception:
                pass
            if k in ("n_cont",):
                v = int(v) if v is not None else 1
            elif k in ("peso_t", "gastos_origen_usd"):
                v = float(v) if v is not None else 0.0
            elif k == "flete_usd":
                v = float(v) if v is not None else None
            elif k in ("prueba_origen", "bien_capital", "usado"):
                v = bool(v)
            if v != d.get(k):
                cfg[k] = v
        if cfg:
            out[eid] = cfg
    return out


def _internacion(pl, res0: dict, res: dict, IC: dict, dolar: float):
    """Sección Internación: país de origen e Incoterm por equipo, parámetros con su fuente y tabla del costo puesto en planta."""
    import pandas as pd
    ss = st.session_state
    C.ayuda(C.esc(
        "**Cómo.** Para cada equipo importado: CIF = FOB + flete + seguro; derechos = arancel × CIF (0 % con tratado y prueba de "
        "origen, o con bien de capital de la Ley 18.634; 6 % sin ellos); IVA de importación = 19 % × (CIF + derechos), que se paga "
        "en la aduana y se recupera como crédito fiscal, por eso no entra al costo del activo; gastos de internación = agente de "
        "aduana + puerto (DHC, CMD, *gate in* y *gate out*, almacenaje) + transporte de San Antonio a Teno. Costo puesto en planta = "
        "CIF + derechos + gastos. El precio de cada equipo se toma como precio en el Incoterm elegido. Los equipos de origen Chile "
        "no tienen internación.\n\n"
        "**Cómo entra al total.** Lo que la internación agrega sobre el precio se suma una vez a la inversión de la planta, fuera "
        "del factor de instalación: el factor ya incluye el montaje y la internación reemplaza solo el flete y la entrega. El "
        "montaje de Loh et al. (2002) se suma solo si se marca la casilla.\n\n"
        "**País por defecto.** El del fabricante que ya traen los datos del equipo (por ejemplo los evaporadores de CFT, Italia); "
        "si no hay, Chile. Equipos de gran tamaño, fuera de contenedor (*break bulk*), con el flete presunto de 5 % del FOB.\n\n"
        "**Acuerdos con arancel 0 % y prueba de origen.** " + " ".join(f"{', '.join(ps)}: {ac}." for ac, ps in _acuerdos().items())),
        "Internación de los equipos importados")
    filas = res0["filas"]
    defectos = {}
    for f in filas:
        eq = pl.equipos.get(str(f["equipo"])) if getattr(pl, "equipos", None) else None
        d = INT.config_por_defecto(f, eq); defectos[str(f["equipo"])] = d
    with st.form("cos_int_form"):
        a, b = st.columns(2)
        activa = a.checkbox("Sumar la internación a la inversión", value=bool(IC["activa"]), key="cos_int_activa")
        montaje = b.checkbox("Sumar el montaje sobre el costo puesto en planta", value=bool(IC["sumar_montaje"]), key="cos_int_montaje",
                             help=C.esc(INT.FUENTE_MONTAJE + ". Desmarcado por defecto: el factor de instalación del sistema de costeo ya incluye el montaje."))
        filas_ed = []
        for f in filas:
            cfg = dict(defectos[str(f["equipo"])]); cfg.update(IC["equipos"].get(str(f["equipo"]), {}))
            filas_ed.append(_fila_editor(f, cfg))
        df0 = pd.DataFrame(filas_ed)
        if len(df0):
            df0["Flete cotizado (US$)"] = pd.to_numeric(df0["Flete cotizado (US$)"], errors="coerce").astype(float)
        CC = st.column_config
        df = st.data_editor(df0, key=f"cos_int_tabla_{C.version_planta()}", width="stretch", hide_index=True, num_rows="fixed",
                            disabled=["Equipo", "Nombre"],
                            column_config={"País de origen": CC.SelectboxColumn("País de origen", options=_PAISES, required=True,
                                                                                help="Chile: compra nacional, sin internación"),
                                           "Incoterm": CC.SelectboxColumn("Incoterm", options=list(INT.INCOTERMS), required=True,
                                                                          help="Condición del precio cotizado (Incoterms 2020)"),
                                           "Carga": CC.SelectboxColumn("Carga", options=list(INT.CARGAS), required=True),
                                           "Contenedores": CC.NumberColumn("Contenedores", min_value=1, step=1, format="%d", alignment="center"),
                                           "Peso (t)": CC.NumberColumn("Peso (t)", min_value=0.0, format="localized", alignment="center"),
                                           "Gastos en origen (US$)": CC.NumberColumn("Gastos en origen (US$)", min_value=0.0, format="localized", alignment="right",
                                                                                     help="Solo EXW o FCA: transporte y despacho en el país de origen"),
                                           "Flete cotizado (US$)": CC.NumberColumn("Flete cotizado (US$)", min_value=0.0, format="localized", alignment="right",
                                                                                   help="Vacío: tarifa por contenedor o flete presunto"),
                                           "Prueba de origen": CC.CheckboxColumn("Prueba de origen", help="Certificado o declaración de origen del tratado"),
                                           "Bien de capital (Ley 18.634)": CC.CheckboxColumn("Bien de capital (Ley 18.634)"),
                                           "Usado": CC.CheckboxColumn("Usado", help="Recargo de 50 % sobre el derecho ad valorem")})
        st.caption(C.esc(INT.JUST_EQUIPO + "."))
        with st.expander("Parámetros de la internación"):
            cols = st.columns(3); nuevos = {}
            for i, (k, p) in enumerate(INT.PARAMETROS.items()):
                fr = p["unidad"].startswith("fracción")
                v = float(IC["parametros"].get(k, p["valor"]))
                et = f"{p['nombre']} ({'%' + p['unidad'][8:] if fr else p['unidad']})"
                x = cols[i % 3].number_input(C.esc(et), 0.0, 1e7, v * 100 if fr else v, 0.1 if fr else 1.0, key=f"cos_int_p_{k}",
                                             format="%.2f" if fr or v < 1000 else "%.0f", help=C.esc(f"{p['fuente']}. Estado: {p['estado']}."))
                nuevos[k] = float(x) / 100 if fr else float(x)
        if st.form_submit_button("Aplicar la internación", type="primary"):
            IC["activa"] = bool(activa); IC["sumar_montaje"] = bool(montaje)
            IC["parametros"] = {k: v for k, v in nuevos.items() if abs(v - INT.PARAMETROS[k]["valor"]) > 1e-12}
            if df is not None:
                IC["equipos"] = _desde_editor(df.to_dict("records"), defectos)
            st.rerun()
    I = res.get("internacion")
    if not I:
        st.caption("La internación no se suma a la inversión: marque la casilla y aplique.")
        I = INT.internacion(filas, IC["equipos"], IC["parametros"], bool(IC["sumar_montaje"]), pl)
    imp = [r for r in I["filas"] if r["importado"]]
    if not imp:
        st.info("Todos los equipos tienen origen Chile: no hay internación. Cambie el país de origen en la tabla de arriba.")
        return
    filas_t = [dict(eq=f"{r['equipo']} · {r['nombre']}", pais=r["pais"], inc=r["incoterm"], fob=r["fob"], fs=r["flete"] + r["seguro"],
                    cif=r["cif"], der=r["arancel"], iva=r["iva_importacion"] + r["iva_locales"], gas=r["gastos"], mon=r["montaje"],
                    pp=r["activo"], pp_clp=r["activo"] * dolar, razon=r["razon_arancel"]) for r in imp]
    T = {k: sum(r[k] for r in imp) for k in INT.SUMAS}
    filas_t.append(dict(eq="Total de los importados", pais="", inc="", fob=T["fob"], fs=T["flete"] + T["seguro"], cif=T["cif"], der=T["arancel"],
                        iva=T["iva_importacion"] + T["iva_locales"], gas=T["gastos"], mon=T["montaje"], pp=T["activo"], pp_clp=T["activo"] * dolar, razon=""))
    cols = [("eq", "Equipo", "txt", 0), ("pais", "País", "txt", 0), ("inc", "Incoterm", "txt", 0), ("fob", "FOB (US$)", "mm", 0),
            ("fs", "Flete y seguro (US$)", "mm", 0), ("cif", "CIF (US$)", "mm", 0), ("der", "Derechos (US$)", "mm", 0),
            ("iva", "IVA, crédito fiscal (US$)", "mm", 0), ("gas", "Gastos de internación (US$)", "mm", 0)]
    if I["sumar_montaje"]:
        cols.append(("mon", "Montaje (US$)", "mm", 0))
    cols += [("pp", "Costo puesto en planta (US$)", "mm", 0), ("pp_clp", "Costo puesto en planta ($)", "clp", 0), ("razon", "Arancel", "txt", 0)]
    C.mostrar_tabla(filas_t, cols)
    st.caption(C.esc(f"La internación agrega ${C.fmt(T['extra'] * dolar / 1e6, 1)} M sobre el precio de los {len(imp)} equipos importados. "
                     f"El IVA de ${C.fmt((T['iva_importacion'] + T['iva_locales']) * dolar / 1e6, 1)} M se paga al internar y se recupera "
                     "como crédito fiscal (D.L. 825, art. 23 N.º 1): entra al flujo de caja de Economía, no al costo del activo."))
    if I["avisos"]:
        with st.expander(f"Avisos de la internación ({len(I['avisos'])})"):
            st.markdown(C.esc("\n".join(f"- {a}" for a in I["avisos"])))
