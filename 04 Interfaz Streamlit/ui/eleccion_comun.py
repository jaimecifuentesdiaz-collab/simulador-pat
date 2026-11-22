"""Piezas comunes de la elección en vivo de la Planta real y de Equipos auxiliares (PAT 139, punto 6 de los comentarios del profesor
Torres del 14-11-2026): estado de Tavily, pila de deshacer compartida con la Planta ficticia, eventos del lienzo, botones y tabla de
candidatos. La lógica de la elección está en el motor (pat_sim/motor/eleccion_viva.py y eleccion_auxiliares.py)."""
from __future__ import annotations
import streamlit as st
from . import comun as C, lienzo as LV

COLS_CAND = [("et", "Candidato", "txt", 0), ("fab", "Fabricante", "txt", 0), ("n", "Unidades (n)", "num", 0), ("k", "Necesarias (k)", "num", 0),
             ("org", "Origen", "cen", 0), ("ci", "C_inv (US$/año)", "mm", 0), ("co", "C_op (US$/año)", "mm", 0), ("cf", "C_inef (US$/año)", "mm", 0),
             ("c", "C (US$/año)", "mm", 0), ("a", "A", "pct", 2), ("eta", "η en operación", "pct", 1), ("el", "Elegido", "cen", 0)]
# PAT 139b (pedido de Jaime, 14-11-2026): sin marca de «mejor opción»; el estudiante ordena la lista por la columna que quiera y decide
ORDENES = {"C": ("C, menor primero", "C", False), "C_inv": ("C_inv, menor primero", "C_inv", False),
           "C_op": ("C_op, menor primero", "C_op", False), "C_inef": ("C_inef, menor primero", "C_inef", False),
           "A": ("A, mayor primero", "A", True), "eta": ("η en operación, mayor primero", "eta_operacion", True),
           "origen": ("Origen", "origen", False)}


def estado_tavily() -> dict:
    """{en_linea, motivo, fuente}: datos.referencia_equipos.estado_tavily si existe (equipo E2); si no, la clave de precios_web."""
    try:
        from pat_sim.datos import referencia_equipos as RE
        f = getattr(RE, "estado_tavily", None)
    except Exception:
        f = None
    if f is not None:
        try:
            r = f() or {}
            return dict(en_linea=bool(r.get("en_linea")), motivo=str(r.get("motivo") or ""), fuente="referencia_equipos")
        except Exception as e:
            return dict(en_linea=False, motivo=f"No se pudo revisar Tavily ({type(e).__name__}).", fuente="referencia_equipos")
    try:
        from pat_sim.datos import precios_web as PW
        clave = PW.obtener_clave()
    except Exception:
        clave = None
    return dict(en_linea=bool(clave), fuente="precios_web",
                motivo="Clave de Tavily encontrada." if clave else
                "Sin clave de Tavily (TAVILY_API_KEY en .streamlit/secrets.toml o en el entorno): los candidatos salen de la base de respaldo "
                "y del índice de Williams.")


def mostrar_estado_tavily() -> dict:
    t = estado_tavily()
    if t["en_linea"]:
        st.success(C.esc("Tavily en línea: cada etapa busca su equipo real en internet. " + t["motivo"]).strip())
    else:
        st.info(C.esc("Tavily fuera de línea: " + (t["motivo"] or "sin motivo informado") +
                      " Los candidatos salen de la base de respaldo y, si no hay, del índice de Williams."))
    return t


def historial(pl):
    """La misma pila de deshacer de la Planta ficticia (st.session_state.lienzo_historial), para que el orden de los cambios se
    respete entre las tres pantallas de construcción."""
    from . import p_diseno as PD
    return PD._historial(pl)


def resolver_si_hace_falta(pl) -> None:
    """Después de deshacer, la planta queda sin resolver (motor/lienzo.restaurar): se resuelve aquí, como en Diseño."""
    if pl.equipos and not pl.resuelta:
        try:
            pl.resolver()
            st.session_state.error_resolucion = None
        except Exception as e:
            pl.resuelta = False
            st.session_state.error_resolucion = str(e)


def limpiar_formulario_diseno(pl, ids=None) -> None:
    """El formulario de la Planta ficticia guarda sus valores en la sesión (par_, nom_, x_, y_): después de deshacer (ids=None) o de
    mover un equipo aquí, se borran para que Diseño muestre la planta tal como quedó (lo mismo que hace Diseño con sus eventos)."""
    ss = st.session_state
    for k in [k for k in list(ss.keys()) if isinstance(k, str) and k.startswith(("par_", "nom_", "x_", "y_"))]:
        if k == "par_eq":
            continue
        if ids is None or any(k.startswith(f"{p}_{i}") for i in ids for p in ("par", "nom", "x", "y")):
            del ss[k]
    if ss.get("par_eq") is not None and ss.get("par_eq") not in pl.equipos:
        del ss["par_eq"]


def deshacer(pl, motor_deshacer) -> dict:
    """Botón «Deshacer» de la Planta real o de Equipos auxiliares: deshace, resuelve y limpia el formulario de Diseño."""
    r = motor_deshacer(pl, historial(pl))
    if r.get("restaurada"):
        limpiar_formulario_diseno(pl)
    resolver_si_hace_falta(pl)
    C.marcar_cambio()
    return r


def procesar_eventos(pl, clave: str, procesar) -> list[str]:
    """Aplica los eventos del lienzo (clave del componente) que todavía no se han procesado. procesar(ev) -> {ok, mensaje}.
    Devuelve los mensajes; guarda el último número de evento en st.session_state[clave + '_seq']."""
    ss = st.session_state
    evs = LV.eventos_nuevos(ss.get(clave), int(ss.get(clave + "_seq", 0)))
    msgs, cambio = [], False
    for ev in evs:
        try:
            r = procesar(ev) or {}
        except Exception as e:                     # un evento malo no bota la pantalla
            r = dict(ok=False, mensaje=f"No se pudo aplicar «{ev.get('evento')}»: {e}")
        ss[clave + "_seq"] = int(ev["seq"])
        cambio = True
        if r.get("restaurada"):
            limpiar_formulario_diseno(pl)
        elif ev.get("evento") == "mover":
            limpiar_formulario_diseno(pl, [(ev.get("datos") or {}).get("id")])
        if r.get("mensaje"):
            msgs.append(dict(seq=int(ev["seq"]), texto=r["mensaje"], tipo="ok" if r.get("ok") else "error"))
    if cambio:
        resolver_si_hace_falta(pl)
        C.marcar_cambio()
        lst = ss.setdefault(clave + "_mensajes", [])
        lst.extend(msgs); del lst[:-6]
    return [m["texto"] for m in msgs]


def anotar(clave: str, r: dict) -> None:
    """Mensaje de un botón (se muestra en la ejecución siguiente, después del callback)."""
    if r and r.get("mensaje"):
        st.session_state[clave + "_aviso"] = (bool(r.get("ok", True)), r["mensaje"])


def mostrar_aviso(clave: str) -> None:
    a = st.session_state.pop(clave + "_aviso", None)
    if a:
        (st.success if a[0] else st.warning)(C.esc(a[1]))


def usd(v, d: int = 2) -> str:
    """US$ en millones por año (M = millones)."""
    return "—" if v is None else C.esc(f"US$ {C.fmt(v / 1e6, d)} M/año")


def ordenar(cands: list[dict], orden: str = "C") -> list[dict]:
    """Candidatos ordenados por la columna elegida (ORDENES); los que no tienen el dato van al final. No marca ninguno como mejor."""
    _n, campo, desc = ORDENES.get(orden, ORDENES["C"])
    if campo == "origen":
        return sorted(cands, key=lambda c: (str(c.get("origen") or ""), c.get("C") if c.get("C") is not None else float("inf")))
    con = [c for c in cands if c.get(campo) is not None]
    sin = [c for c in cands if c.get(campo) is None]
    return sorted(con, key=lambda c: float(c[campo]), reverse=desc) + sin


def filas_candidatos(cands: list[dict], elegido_id: str | None) -> list[dict]:
    return [dict(et=c.get("etiqueta") or c.get("modelo"), fab=c.get("fabricante") or "sin dato", n=c.get("n"), k=c.get("k"), org=c.get("origen"),
                 ci=c.get("C_inv"), co=c.get("C_op"), cf=c.get("C_inef"), c=c.get("C"), a=c.get("A"), eta=c.get("eta_operacion"),
                 el="Sí" if c["id"] == elegido_id else "", fu=(c.get("fuente") or "sin dato") + (f" ({c['url']})" if c.get("url") else ""))
            for c in cands]


def para_lienzo(c: dict) -> dict:
    """Lo que el componente necesita de un candidato (sin los detalles largos): C_inv, C_op, C_inef, C, A, η en operación, origen y
    fuente, para que el estudiante compare. PAT 139b: sin la clave «mejor» (no se destaca ninguna opción)."""
    num = lambda x: None if x is None else float(x)
    return dict(id=c["id"], etq=c.get("etiqueta") or c.get("modelo"), fab=c.get("fabricante") or "", modelo=c.get("modelo"), n=int(c.get("n") or 0),
                k=int(c.get("k") or 0), org=c.get("origen") or "", C=num(c.get("C")), Ci=num(c.get("C_inv")), Co=num(c.get("C_op")),
                Cf=num(c.get("C_inef")), A=num(c.get("A")), eta=num(c.get("eta_operacion")), fuente=str(c.get("fuente") or "")[:240],
                url=c.get("url") or "", cap=num(c.get("capacidad")))      # PAT 140 g: capacidad por unidad, para ver si calza en otro equipo


def paralelo_elegidos(filas: list[dict], objs: list[dict]) -> dict:
    """PAT 139b: {id dibujado: dibujo de n unidades en paralelo} de los auxiliares elegidos con n > 1 (bombas, válvulas, estanques o
    calderas), para que el lienzo dibuje n símbolos (motor/lienzo.dibujo_paralelo)."""
    from pat_sim.motor import lienzo as LZ
    out = {}
    for f, ob in zip(filas, objs):
        e = f.get("elegido") or {}
        try:
            n, k = int(e.get("n") or 1), int(e.get("k") or e.get("n") or 1)
        except (TypeError, ValueError):
            continue
        if n > 1:
            for d in ob.get("dianas") or []:
                out[d] = LZ.dibujo_paralelo(n, k)
    return out


# ---------------------------------------------------------------- PAT 140 c: 3 opciones por etapa y su ficha comparativa
COLORES_OPCION = ("#2a78d6", "#c98c31", "#1b7a5a")        # azul, dorado y verde: una curva por opción (sin rojo)
FONDO_CONVENIENTE = "#e3f4ec"                               # verde suave: valor más conveniente de cada fila


def _h(t) -> str:
    import html as _html
    return _html.escape(str(t if t is not None else ""), quote=True)


def _alinear(v: str) -> str:
    """Estilo de tablas de Jaime: plata a la derecha, números al centro y texto a la izquierda."""
    t = str(v or "")
    if t.startswith("US$"):
        return "right"
    return "center" if t[:1].isdigit() else "left"


# PAT 140 d (pedido de Jaime, 17-11-2026: «no repetir información que ya se muestra»): la ficha no repite en sus filas lo que ya dice
# el encabezado de cada columna (modelo, fabricante, origen, n y k), da la fuente del precio una sola vez, muestra un solo gráfico de
# curvas. PAT 140 e: la regla y la base de cálculo ya no se muestran (la base pasó a los ⓘ de «Costo total»). Los datos del motor (motor/tres_opciones.comparativa) no cambian.
FILAS_EN_ENCABEZADO = ("Modelo y fabricante", "Origen del dato", "Unidades en paralelo (n)", "Necesarias (k)")
_FRASE_TODAS = " Ordenadas por n; las demás quedan en la tabla «Elegir por etapa»."


def titulo_opcion(o: dict) -> str:
    """Encabezado de una opción que la distingue de otra con el mismo equipo: «1 × Modelo sin reserva» o «2 × Modelo (1 de 2, con
    reserva)». Sin n o k, el título del motor tal cual."""
    tit = str(o.get("titulo") or "")
    try:
        n, k = int(o.get("n") or 0), int(o.get("k") or 0)
    except (TypeError, ValueError):
        return tit
    if n < 1 or k < 1 or "reserva" in tit:
        return tit
    return tit + (f" ({k} de {n}, con reserva)" if n > k else " sin reserva")


def _grupos_iguales(cu: dict) -> list[list[int]]:
    """Grupos (de 2 o más) de opciones cuyas curvas η/η_max y puntos de operación coinciden en todo el eje (diferencia < 0,001)."""
    ss = (cu or {}).get("series") or []
    grupos, usados = [], set()
    for i, a in enumerate(ss):
        if i in usados:
            continue
        g = [i]
        for j in range(i + 1, len(ss)):
            b = ss[j]
            if j not in usados and len(a.get("eta") or []) == len(b.get("eta") or []) and \
                    all(abs(x - y) < 1e-3 for x, y in zip(a["eta"], b["eta"])) and \
                    abs(float(a["op"]["eta"]) - float(b["op"]["eta"])) < 1e-3:
                g.append(j)
        if len(g) > 1:
            usados.update(g); grupos.append(g)
    return grupos


def nota_curvas(comp: dict) -> str:
    """Una línea que explica por qué dos o más curvas de la ficha quedan una sobre otra (si pasa)."""
    cu = (comp or {}).get("curva")
    grupos = _grupos_iguales(cu)
    if not grupos:
        return ""
    n = len(cu["series"])
    u = comp.get("unidad") or ""
    g = grupos[0]
    quien = (f"Las {n} curvas coinciden" if len(g) == n else
             "Las curvas de las opciones " + ", ".join(str(i + 1) for i in g[:-1]) + f" y {g[-1] + 1} coinciden")
    xd = cu["series"][g[0]].get("diseno_x")
    donde = f" ({C.fmt(xd, 1)} {u})" if xd is not None else ""
    return (f"{quien}: en {'las ' + str(n) if len(g) == n else 'esas'} opciones las k unidades en operación llegan a su punto de diseño con la misma producción de la "
            f"etapa{donde} y la curva supuesta tiene la misma forma (Supuesto «a_curva»), así que η/η_max solo depende de la producción; "
            "las curvas se separan cuando el equipo de una opción es más grande que requerida / k.")


def ayuda_curvas(comp: dict) -> str:
    """Texto del «ⓘ Cómo leer el gráfico» de la ficha (el mismo en el diálogo de Streamlit y en el lienzo): qué marcan el círculo y el
    rombo, la fuente de la curva y, si dos o más curvas coinciden, por qué."""
    cu = (comp or {}).get("curva")
    if not cu:
        return ""
    u = comp.get("unidad") or ""
    req = comp.get("requerida")
    donde = f" con la producción requerida ({C.fmt(req, 1)} {u}, línea gris)" if req is not None else ""
    return (f"Círculo: punto de operación de cada opción{donde}; rombo: punto de diseño. {cu.get('fuente') or ''}"
            + (f" {comp['nota_curvas']}" if comp.get("nota_curvas") else "")).strip()


def depurar_ficha(comp: dict | None) -> dict | None:
    """Copia de la ficha del motor sin repeticiones: encabezados que distinguen las opciones (con o sin reserva), sin las filas que
    repiten el encabezado (FILAS_EN_ENCABEZADO), sin la nota «Fuente del precio: en el encabezado» (PAT 140 f: sin fila de fuente del precio, pedido de Jaime) y la
    regla sin la frase de «las demás opciones» (la ficha ya lo dice arriba). Idempotente."""
    if not comp or not comp.get("opciones"):
        return comp
    if comp.get("_depurada"):
        return comp
    out = dict(comp, _depurada=True)
    out["opciones"] = [dict(o, titulo=titulo_opcion(o)) for o in comp["opciones"]]
    secs = []
    cap_u = next((f.get("valores") for s in comp.get("secciones") or [] for f in s.get("filas") or [] if f.get("etq") == "Capacidad por unidad"), None)
    for s in comp.get("secciones") or []:
        s2 = dict(s, filas=[f for f in s.get("filas") or [] if f.get("etq") not in FILAS_EN_ENCABEZADO])
        if str(s2.get("nota") or "").startswith("Fuente del precio"):
            s2["nota"] = ""
        pd_u = next((f for f in s2["filas"] if f.get("etq") == "Punto de diseño por unidad"), None)
        if pd_u is not None and cap_u is not None and list(pd_u.get("valores") or []) == list(cap_u):
            # mismo valor que «Capacidad por unidad» en todas las columnas: se dice una vez, en la nota de la sección
            s2["filas"] = [f for f in s2["filas"] if f is not pd_u]
            s2["nota"] = (str(s2.get("nota") or "") + " El punto de diseño por unidad es la capacidad por unidad (Supuesto «q_peak»).").strip()
        secs.append(s2)
    out["secciones"] = secs
    out["regla"] = str(comp.get("regla") or "").replace(_FRASE_TODAS, " Ordenadas por n.")
    out["nota_curvas"] = nota_curvas(out)
    out["ayuda_curvas"] = ayuda_curvas(out)
    return out


def intro_ficha(req_txt: str, n_todos: int | None, donde: str = "la tabla «Todas las opciones» bajo el lienzo") -> str:
    """Única línea de presentación de la ficha (PAT 140 e: la regla de las 3 opciones ya no se muestra)."""
    return (f"{req_txt}. Compare fila por fila (en verde suave, el valor más conveniente de cada fila) y elija una. Las demás opciones "
            f"están en {donde}" + (f" ({n_todos} en total)." if n_todos else "."))


def _etiqueta_html(f: dict) -> str:
    """Celda de la etiqueta de una fila. Con texto «info», la etiqueta lleva un ⓘ que despliega (clic o toque) el para qué y el por qué
    de la fila, ahí mismo y sin JavaScript (<details>)."""
    if not f.get("info"):
        return _h(f["etq"])
    return ('<details class="ayuda" style="margin:0"><summary style="gap:0.3rem;align-items:flex-start">'
            f'<span>{_h(f["etq"])}</span><span title="Cómo se calcula y para qué sirve: clic para ver u ocultar" '
            'style="color:#4f6f7e;font-size:1.05rem;line-height:1.2;user-select:none;flex:0 0 auto">ⓘ</span></summary>'
            f'<div class="ayuda-txt" style="font-size:0.85rem;font-weight:400">{_h(f["info"])}</div></details>')


def html_comparativa(comp: dict, elegido_id: str | None = None) -> str:
    """Tabla HTML de la ficha comparativa (motor/tres_opciones.comparativa): una columna por opción, filas alineadas para leer de lado
    a lado y, en cada fila, el valor más conveniente con fondo verde suave. La opción aplicada en la planta lleva la marca «Aplicada»."""
    comp = depurar_ficha(comp)
    if not comp or not comp.get("opciones"):
        return ""
    ops = comp["opciones"]
    w = f"{int(66 / len(ops))}%"
    col = '<col style="width:' + w + '">'
    h = ['<div class="tabla-desliz"><table class="pat" style="table-layout:fixed;overflow-wrap:anywhere">',
         '<colgroup><col style="width:34%">' + col * len(ops) + '</colgroup><thead><tr><th></th>']
    for i, o in enumerate(ops):
        url = f'<br><a href="{_h(o["url"])}" target="_blank" rel="noopener">{_h(o["url"][:60])}</a>' if o.get("url") else ""
        apl = ' <span style="background:#dff3ea;color:#1b7a5a;border-radius:8px;padding:0 6px;font-size:0.8rem">Aplicada</span>' if o["id"] == elegido_id else ""
        h.append(f'<th style="border-top:4px solid {COLORES_OPCION[i % 3]};vertical-align:top">Opción {i + 1}: {_h(o["titulo"])}{apl}'
                 f'<br><span style="font-weight:400;font-size:0.85rem">{_h(o["fabricante"])} · {_h(o["origen"])}</span>{url}</th>')
    h.append("</tr></thead><tbody>")
    for s in comp.get("secciones") or []:
        h.append(f'<tr><td colspan="{len(ops) + 1}" style="background:#eef3f0;font-weight:600">{_h(s["titulo"])}</td></tr>')
        for f in s["filas"]:
            tit = f' title="{_h(f["ayuda"])}"' if f.get("ayuda") else ""
            h.append(f"<tr><td{tit}>{_etiqueta_html(f)}</td>")
            for v, c in zip(f["valores"], f["conveniente"]):
                al = _alinear(v)
                est = f' style="text-align:{al};background:{FONDO_CONVENIENTE};font-weight:600"' if c else f' style="text-align:{al}"'
                h.append(f'<td{est}>{_h(v)}</td>')
            h.append("</tr>")
        if s.get("nota"):
            h.append(f'<tr><td colspan="{len(ops) + 1}" class="nota">{_h(s["nota"])}</td></tr>')
    h.append("</tbody></table></div>")
    return "".join(h)


def grafico_comparativa(comp: dict):
    """Único gráfico de la ficha: las curvas η/η_max de las 3 opciones contra la producción de la etapa (misma escala), con el punto de
    operación (círculo) y el punto de diseño (rombo) de cada una; si dos o más curvas coinciden, una línea explica por qué. Sin pandas,
    no dibuja nada."""
    comp = depurar_ficha(comp)
    cu = (comp or {}).get("curva")
    if not cu:
        return
    try:
        import pandas as pd
    except Exception:
        return
    nombres = [f"Opción {i + 1}: {o['titulo']}" for i, o in enumerate(comp["opciones"])]
    filas, pts, dis = [], [], []
    for nom, s in zip(nombres, cu["series"]):
        filas += [dict(Q=x, eta=e, Opcion=nom) for x, e in zip(cu["x"], s["eta"])]
        pts.append(dict(Q=s["op"]["x"], eta=s["op"]["eta"], Opcion=nom, Punto="Operación"))
        if s.get("diseno_x") is not None:
            dis.append(dict(Q=s["diseno_x"], eta=1.0, Opcion=nom, Punto="Diseño"))
    u = comp.get("unidad") or ""
    color = {"field": "Opcion", "type": "nominal", "title": "", "scale": {"domain": nombres, "range": list(COLORES_OPCION[:len(nombres)])},
             "legend": {"orient": "bottom", "labelLimit": 520, "direction": "vertical"}}
    capas = [{"data": {"values": filas}, "mark": {"type": "line", "strokeWidth": 2.5},
              "encoding": {"x": {"field": "Q", "type": "quantitative", "title": f"Producción de la etapa ({u})"},
                           "y": {"field": "eta", "type": "quantitative", "title": "η/η_max", "axis": {"format": "%"},
                                 "scale": {"domain": [cu["y_min"], cu["y_max"]]}},
                           "color": color, "strokeDash": {"field": "Opcion", "type": "nominal", "legend": None}}},
             {"data": {"values": pts}, "mark": {"type": "point", "filled": True, "size": 110, "tooltip": True},
              "encoding": {"x": {"field": "Q", "type": "quantitative"}, "y": {"field": "eta", "type": "quantitative"}, "color": color}}]
    if dis:
        capas.append({"data": {"values": dis}, "mark": {"type": "point", "shape": "diamond", "filled": False, "size": 120, "strokeWidth": 1.6,
                                                        "tooltip": True},
                      "encoding": {"x": {"field": "Q", "type": "quantitative"}, "y": {"field": "eta", "type": "quantitative"}, "color": color}})
    capas.append({"data": {"values": [dict(Q=comp["requerida"])]}, "mark": {"type": "rule", "color": "#5b7280", "strokeDash": [4, 3]},
                  "encoding": {"x": {"field": "Q", "type": "quantitative"}}})
    spec = {"height": 260, "usermeta": {"huella": f"{comp.get('equipo')}|{'|'.join(o['id'] for o in comp['opciones'])}"}, "layer": capas}
    st.markdown(f"**Curva de eficiencia de las {len(nombres)} opciones (misma escala)**")
    with st.expander("ⓘ Cómo leer el gráfico", expanded=False):          # PAT 140 e: el texto explicativo va cerrado por defecto
        st.caption(C.esc(comp.get("ayuda_curvas") or ayuda_curvas(comp)))
    st.vega_lite_chart(pd.DataFrame(filas), spec)


def _elegir_y_cerrar(al_elegir, c: dict, clave_abierta: str | None):
    """«Elegir esta opción» dentro del diálogo: aplica (un paso de «Deshacer») y cierra la ficha para ver la planta al día."""
    if clave_abierta:
        st.session_state.pop(clave_abierta, None)
    al_elegir(c)


def mostrar_comparativa(comp: dict, opciones: list[dict], elegido_id: str | None, al_elegir, prefijo: str, req_txt: str = "",
                        n_todos: int | None = None, donde: str = "la tabla «Todas las opciones» bajo el lienzo",
                        clave_abierta: str | None = None) -> None:
    """Ficha comparativa en Streamlit (la misma del lienzo, cada dato una sola vez): presentación, gráfico con las 3 curvas, tabla de 3
    columnas, «Elegir esta opción» bajo cada columna (al_elegir(candidato), el mismo callback de la lista: mismo estado de sesión y un
    paso de «Deshacer»). PAT 140 e: sin la regla de las 3 opciones ni la base de cálculo; las cifras de la base están en el ⓘ de cada
    ecuación de «Costo total» y la explicación del gráfico, en el «ⓘ Cómo leer el gráfico»."""
    comp = depurar_ficha(comp)
    if not comp or not opciones:
        return
    if req_txt:
        st.caption(C.esc(intro_ficha(req_txt, n_todos, donde)))
    grafico_comparativa(comp)
    st.html(html_comparativa(comp, elegido_id))
    cols = st.columns([0.3] + [0.7 / len(opciones)] * len(opciones))
    cols[0].caption("Aplicar una de las opciones:")
    for i, (col, c) in enumerate(zip(cols[1:], opciones)):
        col.button("Elegir esta opción", key=f"{prefijo}_{i}", on_click=_elegir_y_cerrar, args=(al_elegir, c, clave_abierta),
                   disabled=c["id"] == elegido_id, width="stretch", help=f"Aplica {c.get('etiqueta') or c.get('modelo')} (se puede deshacer).")


def boton_ficha(clave: str, objetivo: str, titulo: str, dibujar) -> None:
    """PAT 140 d: botón «Ver ficha comparativa» bajo «Elegir por etapa» (o por equipo auxiliar) que abre la ficha en un diálogo, en vez
    de repetir la tabla en la página. dibujar(clave_abierta) dibuja el contenido. El diálogo queda abierto mientras
    st.session_state[clave + '_abierta'] sea el objetivo; se cierra con la × o al elegir una opción. Sin st.dialog (banco de pruebas),
    se dibuja en un recuadro."""
    ss = st.session_state
    ka = clave + "_abierta"
    if st.button("Ver ficha comparativa", key=clave + "_ver",
                 help="Abre la ficha con las 3 opciones en columnas (la misma que se abre al pinchar la etapa en el lienzo)."):
        ss[ka] = objetivo
    if ss.get(ka) != objetivo:
        return

    def _cerrar():
        st.session_state.pop(ka, None)

    def _contenido():
        dibujar(ka)

    dlg, deco = getattr(st, "dialog", None), None
    if dlg is not None:
        try:
            deco = dlg(f"Ficha de {titulo}", width="large", on_dismiss=_cerrar)
        except TypeError:
            try:
                deco = dlg(f"Ficha de {titulo}", width="large")
            except Exception:
                deco = None
        except Exception:
            deco = None
    if callable(deco):
        deco(_contenido)()
    else:
        with st.container(border=True):
            _contenido()


def para_lienzo_ficha(comp: dict | None) -> dict | None:
    """Lo que el lienzo necesita para la ficha comparativa (ya viene en textos): encabezados, secciones (con el ⓘ de cada ecuación de costo), curva y el texto del «ⓘ Cómo leer el gráfico». PAT 140 e: sin regla ni base de cálculo."""
    comp = depurar_ficha(comp)
    if not comp:
        return None
    return dict(opciones=comp["opciones"], secciones=comp["secciones"], curva=comp.get("curva"), unidad=comp.get("unidad") or "", requerida=comp.get("requerida"),
                nota_curvas=comp.get("nota_curvas") or "", ayuda_curvas=comp.get("ayuda_curvas") or "")
