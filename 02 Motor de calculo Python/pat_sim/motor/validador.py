"""Validador del diseño en los cuatro lienzos (PAT 143, tarea 6 del plan PAT 141): Planta ficticia, Planta real, Equipos
auxiliares y Lazos de control.

Con la conexión libre el estudiante puede unir lo que quiera en el lienzo; el validador revisa el diseño y, si tiene un error,
la interfaz muestra una advertencia que no deja avanzar a la etapa siguiente y un botón «Pista» con pistas progresivas: la
primera es general (la regla), la segunda dice dónde mirar y la tercera qué cambiar en ese punto, sin armar el diseño por él.

Cada hallazgo es un dict {id, regla, nivel («error» o «aviso»), vista, objeto, mensaje, pistas (lista de tres textos), fuente}.
El mensaje dice qué está mal sin dar la solución. Los avisos no bloquean.

Reúsa lo que ya validan los módulos del motor:
- motor/lienzo.diagnostico (alimentación, repartos, servicios térmicos, calderas sin destino, sobrecarga y cuello de botella,
  precedencia) y motor/precedencia (orden de los estados del material);
- motor/planta.Planta.incompatibles (corrientes de distinto tipo) y Planta.cierres con la tolerancia de motor/itinerario;
- motor/seleccion.requerimientos y seleccion_actual, y motor/eleccion_viva.calza (±20 %, la misma regla del arrastre);
- motor/auxiliares (servicios) y motor/eleccion_auxiliares.elecciones;
- motor/instrumentacion.revisar_lazos (reglas ISA del curso), más las reglas 1, 4, 6, 7, 8, 9, 11, 13 y 15 de la tabla de 15
  reglas (diapositivas ISA del curso, resumen de la tarea 2, sección 2.6). La regla 12 (un diagrama, un lazo) se cumple por
  construcción: el diagrama de lazo ISA-5.4 se dibuja de a un lazo.

Sin Streamlit: la interfaz (ui/validacion.py) dibuja la advertencia, el botón «Pista» y bloquea la franja del proceso.
"""
from __future__ import annotations
from .planta import Planta, TIPOS_SERVICIO
from .corrientes import TIPOS as TIPOS_CORRIENTE
from . import lienzo as LZ
from . import precedencia as PR
from . import instrumentacion as IN
from ..simbolos import isa51

VISTAS = ("ficticia", "real", "auxiliares", "lazos")
NOMBRE_VISTA = {"ficticia": "Planta ficticia", "real": "Planta real", "auxiliares": "Equipos auxiliares", "lazos": "Lazos de control"}
ANTERIORES = {"ficticia": (), "real": ("ficticia",), "auxiliares": ("ficticia", "real"), "lazos": ("ficticia", "real", "auxiliares")}
TOL_CALZA = 0.20            # la misma diferencia que acepta el arrastre (motor/eleccion_viva.CALZA)
N_PISTAS = 3

# Reglas del validador: código, vista, nivel y origen. La tabla se muestra en la ayuda y se documenta en Cambios_PAT143a.
REGLAS = {
    "P00": ("ficticia", "error", "La planta no se puede calcular (motivo del motor que no cubre otra regla)", "motor/planta.resolver"),
    "P01": ("ficticia", "error", "Conexión entre corrientes de distinto tipo", "tipos de corriente de motor/corrientes.py"),
    "P02": ("ficticia", "error", "Conexión que no respeta el orden de los estados del material", "precedencia del mantenedor"),
    "P03": ("ficticia", "error", "Entrada de proceso sin alimentación", "motor/lienzo.diagnostico"),
    "P04": ("ficticia", "error", "Equipo suelto, sin ninguna conexión", "buena práctica del diagrama de flujo"),
    "P05": ("ficticia", "error", "Reparto de un puerto que no suma 100 % (el balance de materia no cierra)", "motor/lienzo.diagnostico"),
    "P06": ("ficticia", "error", "Equipo sin su servicio térmico (vapor o calor)", "motor/lienzo.diagnostico"),
    "P07": ("ficticia", "error", "Servicio auxiliar (caldera o generador) sin destino", "motor/lienzo.diagnostico"),
    "P08": ("ficticia", "error", "Balance de materia o energía de un equipo que no cierra", "motor/planta.cierres e itinerario.TOL_CIERRE"),
    "P09": ("ficticia", "aviso", "Salida de producto libre en un equipo intermedio", "buena práctica del diagrama de flujo"),
    "P11": ("ficticia", "aviso", "Cuello de botella (80 a 100 % de la capacidad efectiva)", "motor/lienzo.diagnostico"),
    "P12": ("ficticia", "aviso", "Sobrecarga o acumulación antes de un equipo", "motor/lienzo.diagnostico"),
    "P13": ("ficticia", "aviso", "Sin salida de producto final", "motor/lienzo.diagnostico"),
    "P14": ("ficticia", "aviso", "Aviso del cálculo de un equipo", "motor/equipos"),
    "P15": ("ficticia", "aviso", "Planta vacía", "motor/lienzo.diagnostico"),
    "R00": ("real", "error", "La Planta ficticia tiene errores", "validador"),
    "R02": ("real", "error", "Capacidad elegida que no alcanza la carga de la etapa (más de 20 % bajo lo requerido)", "motor/eleccion_viva.calza"),
    "R03": ("real", "aviso", "Capacidad elegida algo menor que la carga (hasta 20 %)", "motor/eleccion_viva.calza"),
    "A00": ("auxiliares", "error", "La Planta ficticia o la Planta real tienen errores", "validador"),
    "A01": ("auxiliares", "error", "Auxiliar elegido que no alcanza lo que pide su línea (más de 20 % bajo lo requerido)", "motor/eleccion_viva.calza"),
    "A02": ("auxiliares", "aviso", "Auxiliar elegido algo menor que lo requerido (hasta 20 %)", "motor/eleccion_viva.calza"),
    "A03": ("auxiliares", "error", "Demanda de vapor o calor sin equipo que la genere", "motor/auxiliares.servicios"),
    "A04": ("auxiliares", "error", "Servicio auxiliar sin destino: genera vapor o calor que ningún equipo usa", "motor/auxiliares.servicios"),
    "A05": ("auxiliares", "aviso", "Bomba sobre una línea sin caudal", "motor/auxiliares.bombas"),
    "L00": ("lazos", "error", "Una pantalla anterior tiene errores", "validador"),
    "I01": ("lazos", "error", "Instrumento sin etiqueta válida (letras ISA-5.1 y número de lazo)", "ISA p. 12 (regla 1)"),
    "I04": ("lazos", "error", "Etiqueta de instrumento repetida", "ISA pp. 8, 12 y 13 (reglas 4 y 6)"),
    "I07": ("lazos", "error", "Línea de señal de un tipo que no existe en ISA-5.1", "ISA p. 17 (regla 7)"),
    "I08": ("lazos", "aviso", "Elemento primario sin unión al transmisor por proceso o capilar", "buena práctica, ejemplos ISA pp. 18 y 34 (regla 8)"),
    "I09": ("lazos", "error", "Ubicación del símbolo que no existe en ISA-5.1", "ISA pp. 10 y 11 (regla 9)"),
    "I11": ("lazos", "aviso", "Lazo sin título que describa su función", "ISA p. 32, requisito 2 (regla 11)"),
    "I13": ("lazos", "aviso", "Letra X sin su significado declarado", "ISA p. 15, notas 1 y 2 (regla 13)"),
    "I15": ("lazos", "aviso", "Controlador con más de una medición", "buena práctica (regla 15)"),
    "I16": ("lazos", "error", "Instrumento unido a un equipo que ya no existe", "buena práctica"),
}

# Texto general de cada regla ISA (primera pista de los hallazgos de revisar_lazos y del validador), del resumen de las
# diapositivas ISA del curso (tabla de 15 reglas).
ISA_GENERAL = {
    1: "Cada instrumento lleva su etiqueta: las letras de ISA-5.1 (primera letra = variable medida, siguientes = función) y el "
       "número de lazo (ISA p. 12).",
    2: "La primera letra es la variable medida y es la misma en todos los instrumentos del lazo; la válvula de un controlador de "
       "nivel es LV, no FV (ISA p. 19).",
    4: "El número de lazo es único por lazo y lo comparten todos sus instrumentos, como TT-301, TIC-301 y TV-301 (ISA pp. 8 y 12).",
    5: "Un lazo de control sigue el orden medición, controlador y elemento final de control, y el elemento final actúa sobre la "
       "línea de proceso (ejemplos ISA pp. 18, 34 y 36).",
    7: "Cada línea de señal tiene su tipo y su trazo (ISA p. 17); un actuador neumático que recibe una señal eléctrica necesita "
       "un convertidor I/P (ISA p. 18).",
    8: "La medición se une a proceso: el elemento primario (E) va a la corriente o al equipo y llega al transmisor por una "
       "conexión a proceso o un capilar (ejemplos ISA pp. 18 y 34).",
    9: "La forma y las rayas del globo declaran dónde está el instrumento (campo, panel, detrás del panel) y su tipo (discreto, "
       "DCS, computador o PLC) (ISA pp. 10 y 11).",
    10: "Un lazo declara su fuente de alimentación y la acción en falla de su elemento final (ISA p. 32, requisitos 6 y 7).",
    11: "El título del lazo describe su función, por ejemplo «control de temperatura de salida del hot break» (ISA p. 32, "
        "requisito 2).",
    13: "La letra X y las letras libres se pueden usar, pero su significado se declara fuera del globo (ISA p. 15).",
    14: "El controlador muestra su sentido de acción (directa o inversa) y su punto de consigna (ISA pp. 27 y 28).",
    15: "Un controlador recibe una sola variable medida y un punto de consigna; un elemento final recibe una sola señal de mando "
        "(buena práctica).",
}


def _h(regla: str, mensaje: str, pistas, objeto=None, nivel: str | None = None, fuente: str | None = None, **extra) -> dict:
    vista, nv, _nombre, origen = REGLAS[regla]
    ps = [p for p in (pistas or []) if p][:N_PISTAS]
    d = dict(id=f"{regla}:{objeto or ''}", regla=regla, nivel=nivel or nv, vista=vista, objeto=objeto, mensaje=mensaje,
             pistas=ps, fuente=fuente or origen)
    d.update(extra)
    return d


def _f(v, d: int = 1) -> str:
    """Número en formato chileno (punto de miles, coma decimal)."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _tipo_txt(t: str | None) -> str:
    return TIPOS_CORRIENTE[t][0].lower() if t in TIPOS_CORRIENTE else str(t or "?")


def _eq_txt(pl: Planta, k: str) -> str:
    eq = pl.equipos.get(k)
    return f"{k} ({eq.nombre})" if eq is not None else str(k)


# ---------------------------------------------------------------- Planta ficticia
def _estado_calculo(pl: Planta, motivo=None):
    """(tr, motivo) con la planta como está: si no está resuelta, se resuelve la parte alimentada (como hacen las pantallas)."""
    if pl.resuelta and getattr(pl, "salidas", None):
        return LZ.restricciones(pl, pl), motivo
    sol, m = LZ.resolver_parcial(pl)
    return LZ.restricciones(pl, sol), motivo if motivo is not None else m


def revisar_ficticia(pl: Planta, motivo: str | None = None, precedencia=None) -> list[dict]:
    """Reglas de proceso del diagrama de flujo (P00 a P15)."""
    out: list[dict] = []
    if not pl.equipos:
        return [_h("P15", "La planta está vacía.", ["Arrastre los equipos desde el catálogo del lienzo, en el orden del proceso."])]
    tr, motivo = _estado_calculo(pl, motivo)
    # P01: corrientes de distinto tipo (la conexión libre las acepta)
    for c in pl.incompatibles():
        ts, te = pl.tipo_conexion(c), pl.tipo_entrada(c)
        out.append(_h("P01", f"La corriente {c.nombre or 's/n'} ({c.origen} → {c.destino}) une puertos de distinto tipo de corriente.",
                      ["Cada puerto lleva un tipo de corriente (producto, vapor, condensado, electricidad, aire…), que se ve por su "
                       "color: una salida solo alimenta una entrada del mismo tipo; un subproducto puede volver a proceso.",
                       f"La corriente {c.nombre or 's/n'} sale de {c.origen}.{c.puerto_origen} como {_tipo_txt(ts)} y entra en "
                       f"{c.destino}.{c.puerto_destino}, que espera {_tipo_txt(te)}.",
                       f"Quite esa corriente (clic en la línea y Supr). La entrada {c.destino}.{c.puerto_destino} se alimenta con una "
                       f"salida de {_tipo_txt(te)}, y la salida {c.origen}.{c.puerto_origen} va a una entrada de {_tipo_txt(ts)}."],
                      objeto=LZ._clave_conexion(c)))
    sueltos = set()
    if len(pl.equipos) > 1:
        for k, eq in pl.equipos.items():
            if not any(c.origen == k or c.destino == k for c in pl.conexiones):
                sueltos.add(k)
                ent = sorted({_tipo_txt(p.tipo) for p in eq.entradas}); sal = sorted({_tipo_txt(p.tipo) for p in eq.salidas})
                out.append(_h("P04", f"{_eq_txt(pl, k)} no tiene ninguna conexión.",
                              ["Todo equipo del diagrama forma parte de la línea: recibe material o servicio, lo entrega, o ambas cosas.",
                               f"{k} necesita {', '.join(ent) or 'nada'} y entrega {', '.join(sal) or 'nada'}: busque en la línea qué "
                               "equipo le entrega eso y cuál recibe lo que sale de él.",
                               f"Arrastre desde un puerto de salida del equipo anterior hasta la entrada de {k}, y desde la salida de "
                               f"{k} hasta el equipo siguiente; si {k} sobra, selecciónelo y quítelo con Supr."], objeto=k))
    diag = LZ.diagnostico(pl, motivo, tr, precedencia)
    hay_estructura = bool(out) or any(x.get("regla") == "P03" for x in diag)
    t_prec = PR.regla(pl, precedencia)
    consumidores = [f"{k}.{p.nombre}" for k, e in pl.equipos.items() for p in e.entradas if p.tipo in ("vapor", "calor")]
    for x in diag:
        r = x.get("regla"); k = x.get("equipo")
        if r == "P00":
            if hay_estructura:
                continue                                   # el motivo ya lo explica otra regla (alimentación o corrientes cruzadas)
            out.append(_h("P00", f"La planta no se puede calcular: {motivo}.",
                          ["El cálculo sigue la línea desde la alimentación: cada equipo necesita todas sus entradas y parámetros "
                           "que existan físicamente.",
                           "El motivo del motor nombra el equipo o la especificación que falla; revise el último cambio que hizo ahí.",
                           "Use «Deshacer» (Ctrl+Z) para volver al último diseño que se calculaba y repita el cambio de a poco."]))
        elif r == "P03":
            if k in sueltos:
                continue
            puertos = x.get("puertos") or []
            eq = pl.equipos[k]
            tipos = sorted({_tipo_txt(p.tipo) for p in eq.entradas if p.nombre in puertos})
            out.append(_h("P03", f"{_eq_txt(pl, k)} no recibe material en su entrada {', '.join(puertos)}.",
                          ["Cada entrada de proceso necesita una corriente que llegue desde la salida de un equipo anterior de la línea.",
                           f"{k} espera {', '.join(tipos)} en {', '.join(puertos)}: piense qué operación del proceso va justo antes que la suya.",
                           f"Arrastre desde la salida de {', '.join(tipos)} del equipo anterior hasta {k}.{puertos[0] if puertos else ''}."],
                          objeto=k))
        elif r == "P05":
            p_, tot = x.get("puerto"), float(x.get("total") or 0)
            cs = [c for c in pl.conexiones if c.origen == k and c.puerto_origen == p_]
            out.append(_h("P05", f"El reparto de {k}.{p_} suma {_f(tot, 1)} %: el balance de materia de {k} no cierra.",
                          ["Lo que sale por un puerto se reparte entre sus corrientes y suma 100 %: si suma menos, se pierde "
                           "material; si suma más, se crea.",
                           f"Las corrientes que salen de {k}.{p_} son: " + "; ".join(f"{c.nombre or 's/n'} hacia {c.destino} con {_f(c.reparto, 1)} %" for c in cs) + ".",
                           f"Ajuste en Propiedades de esas corrientes el reparto para que sumen 100 % (" +
                           (f"falta {_f(100 - tot, 1)} %" if tot < 100 else f"sobra {_f(tot - 100, 1)} %") + ")."],
                          objeto=f"{k}.{p_}"))
        elif r == "P06":
            p_, t_ = x.get("puerto"), x.get("tipo")
            out.append(_h("P06", f"{_eq_txt(pl, k)} no recibe {_tipo_txt(t_)} en su entrada {p_}.",
                          ["Los equipos que calientan, evaporan o secan necesitan un servicio térmico: vapor en el tomate y aire "
                           "caliente en la biomasa.",
                           f"Sin esa corriente, la demanda de {_tipo_txt(t_)} de {k} no llega a ningún equipo que la genere y no entra "
                           "en el balance de energía ni en el costeo.",
                           f"Arrastre desde la salida de {_tipo_txt(t_)} de la caldera o del generador de calor hasta {k}.{p_}; si la "
                           "planta no tiene uno, agréguelo desde el catálogo."], objeto=f"{k}.{p_}"))
        elif r == "P07":
            if k in sueltos:
                continue
            sale = sorted({_tipo_txt(p.tipo) for p in pl.equipos[k].salidas if p.tipo in TIPOS_SERVICIO}) or ["su servicio"]
            out.append(_h("P07", f"{_eq_txt(pl, k)} no entrega su servicio a ningún equipo.",
                          ["Un equipo de servicios auxiliares (caldera o generador de calor) existe para abastecer a otros equipos.",
                           "Los equipos que lo necesitan son los que tienen una entrada de vapor o de calor: "
                           + (", ".join(consumidores) if consumidores else "en esta planta no hay ninguno") + ".",
                           f"Una la salida de {', '.join(sale)} de {k} con esas entradas; si ningún equipo la necesita, quite {k}."],
                          objeto=k))
        elif r == "P02":
            m = x.get("motivo") or x.get("texto", "")
            corte = min([i for i in (m.find(" Faltan:"), m.find(" Ese ")) if i > 0] or [len(m)])
            c_ = x.get("conexion") or ""
            cad = t_prec.cadena(pl.rubro) if t_prec is not None else ""
            nivel = "aviso" if (t_prec is not None and t_prec.libre) else "error"
            out.append(_h("P02", f"La conexión {c_.split('>')[0].split('.')[0]} → {k} no respeta el orden del proceso.",
                          ["El material pasa por una cadena de estados en un orden fijo" + (f": {cad}." if cad else ".") +
                           " Cada equipo recibe el estado que deja la etapa anterior.",
                           m[:corte].strip(),
                           m.strip()], objeto=c_, nivel=nivel))
        elif r in ("P11", "P12", "P13", "P14", "P15"):
            pistas = {"P11": ["En la teoría de restricciones, el equipo más exigido fija la producción de la línea.",
                              "Compare su utilización con la de los demás en «Capacidad efectiva y utilización».",
                              "Si se quiere holgura, suba su capacidad nominal o su estado en Propiedades."],
                      "P12": ["Un equipo que recibe más de lo que procesa acumula material antes de él y limita la línea.",
                              "Su capacidad efectiva es capacidad nominal × estado; compárela con lo que recibe.",
                              "Suba su capacidad o su estado, o baje la alimentación."],
                      "P13": ["La línea termina en una salida de producto libre: el producto final de la planta.",
                              "Revise el último equipo de la línea: su salida de producto debe quedar libre.",
                              "Quite la corriente que se lleva el producto final a otro equipo."],
                      "P14": ["Aviso del cálculo del equipo.", "", ""],
                      "P15": ["Arrastre los equipos desde el catálogo del lienzo, en el orden del proceso.", "", ""]}[r]
            out.append(_h(r, x["texto"].rstrip(".") + ".", pistas, objeto=k, nivel="aviso"))
    # P08: balance de materia o energía de cada equipo (misma tolerancia que el itinerario del curso)
    if pl.resuelta and getattr(pl, "salidas", None):
        from .itinerario import TOL_CIERRE
        try:
            filas = pl.cierres()
        except Exception:
            filas = []
        for f in filas:
            for que, d, ent, u in (("materia", f["cierre_masa"], f["masa_entra"], "kg/h"), ("energía", f.get("cierre_energia"), f["energia_entra"], "kW")):
                if d is not None and abs(d) > TOL_CIERRE * max(abs(ent), 1.0):
                    out.append(_h("P08", f"El balance de {que} de {_eq_txt(pl, f['equipo'])} no cierra.",
                                  [f"En cada equipo lo que entra es igual a lo que sale (materia) y la energía también, con sus pérdidas declaradas.",
                                   f"En {f['equipo']} la diferencia es {_f(d, 1)} {u} sobre {_f(ent, 1)} {u} de entrada.",
                                   f"Revise los parámetros de {f['equipo']} que cambió (fracciones, °Brix, humedad o temperaturas) y las "
                                   "corrientes que le llegan."], objeto=f["equipo"]))
    # P09: salida de producto libre en un equipo que entrega producto a otro (el material se va de la planta a medio proceso)
    for k, eq in pl.equipos.items():
        if k in sueltos:
            continue
        sigue = any(c.origen == k and not pl.es_servicio(c) for c in pl.conexiones)
        for p in eq.salidas:
            if p.tipo in PR.PRODUCTO and sigue and not any(c.origen == k and c.puerto_origen == p.nombre for c in pl.conexiones):
                out.append(_h("P09", f"La salida {p.nombre} de {_eq_txt(pl, k)} queda libre: su material sale de la planta a medio proceso.",
                              ["Una salida de producto libre es producto que deja la planta; solo la del último equipo es el producto final.",
                               f"{k} entrega producto por otra salida a la línea; esta queda sin destino.",
                               f"Únala al equipo que sigue o declárela como subproducto en el diseño."], objeto=f"{k}.{p.nombre}"))
    return out


# ---------------------------------------------------------------- Planta real
def revisar_real(pl: Planta) -> list[dict]:
    """Capacidad de los equipos comerciales elegidos frente a la carga de cada etapa (R02 y R03). Una etapa sin elección conserva
    el equipo teórico y no se marca."""
    from . import seleccion as SEL
    out = []
    if not pl.equipos or not pl.resuelta:
        return out
    for r in SEL.requerimientos(pl):
        eid, a = r["equipo"], r["actual"]
        if not a:            # sin elección queda el equipo teórico: no es un error (el indicador «Etapas elegidas» lo muestra)
            continue
        cap, n, k, carga = a.get("capacidad_t_h"), int(a.get("n") or 1), int(a.get("k") or 1), r["carga_t_h"]
        if not cap or not carga:
            continue
        en_op = float(cap) * k / max(n, 1)
        ratio = en_op / float(carga)
        if ratio >= 1 - 1e-9:
            continue
        falta = 100 * (1 - ratio)
        pistas = ["La etapa procesa toda su carga con las unidades que operan (k de n); la reserva no cuenta. Se acepta hasta "
                  f"{_f(100 * TOL_CALZA, 0)} % de diferencia, como al arrastrar un candidato.",
                  f"{eid} recibe {_f(carga, 2)} t/h y " + (f"sus {k} unidades en operación entregan" if k > 1 else "su unidad en operación entrega")
                  + f" {_f(en_op, 2)} t/h: le falta un {_f(falta, 0)} %.",
                  f"Elija en {eid} un modelo de mayor capacidad o más unidades en paralelo; compare las 3 opciones de su ficha comparativa."]
        if ratio < 1 - TOL_CALZA - 1e-9:
            out.append(_h("R02", f"La capacidad elegida en {_eq_txt(pl, eid)} no alcanza su carga.", pistas, objeto=eid))
        else:
            out.append(_h("R03", f"{_eq_txt(pl, eid)} trabaja sobre la capacidad de sus unidades en operación ({_f(100 * ratio, 0)} %).",
                          pistas, objeto=eid))
    return out


# ---------------------------------------------------------------- Equipos auxiliares
def revisar_auxiliares(pl: Planta, aux: dict | None = None, objetivos: list[dict] | None = None) -> list[dict]:
    """Auxiliares elegidos frente a lo que pide su línea y servicios sin destino o sin equipo que los genere (A01 a A05)."""
    out = []
    if not pl.equipos or not aux:
        return out
    from . import eleccion_auxiliares as EA
    el = EA.elecciones(pl)
    for o in objetivos or []:
        g = el.get(o.get("id"))
        req = o.get("requerida")
        if not g or not req:
            continue
        try:
            en_op = float(g.get("capacidad") or 0) * int(g.get("k") or 0)
            ratio = en_op / float(req)
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        if ratio >= 1 - 1e-9:
            continue
        u = o.get("unidad") or ""
        nom = o.get("nombre_largo") or o.get("nombre") or o["id"]
        pistas = ["Cada auxiliar se elige para lo que pide su línea: caudal de la bomba, Cv de la válvula, volumen del estanque o "
                  f"potencia del servicio, con las unidades que operan. Se acepta hasta {_f(100 * TOL_CALZA, 0)} % de diferencia.",
                  f"{o['id']} necesita {_f(req, 1)} {u} y lo elegido entrega {_f(en_op, 1)} {u} en operación: le falta un {_f(100 * (1 - ratio), 0)} %.",
                  f"Elija para {o['id']} una opción de mayor capacidad o con más unidades; si es una bomba que cambió de línea, revise "
                  "la línea que sirve."]
        if ratio < 1 - TOL_CALZA - 1e-9:
            out.append(_h("A01", f"Lo elegido para {nom} no alcanza lo que pide su línea.", pistas, objeto=o["id"]))
        else:
            out.append(_h("A02", f"Lo elegido para {nom} queda algo bajo lo que pide ({_f(100 * ratio, 0)} %).", pistas, objeto=o["id"]))
    serv = {x.get("servicio"): x for x in ((aux.get("servicios") or {}).get("filas") or [])}
    gen = [k for k, e in pl.equipos.items() if e.tipo.startswith("caldera")]
    dem = sum(float((serv.get(s) or {}).get("demanda") or 0) for s in ("Vapor", "Calor (aire caliente)"))
    if dem > 1e-6 and not gen:
        out.append(_h("A03", f"La planta pide {_f(dem, 0)} kW de vapor o calor y no tiene equipo que lo genere.",
                      ["Toda demanda de un servicio auxiliar tiene un equipo que la genera: caldera para el vapor, generador para el aire caliente.",
                       "Los equipos que piden vapor o calor son los que tienen esa entrada en la Planta ficticia.",
                       "Agregue la caldera o el generador en la Planta ficticia y únalo a esas entradas."]))
    for k in gen:
        if dem <= 1e-6:
            out.append(_h("A04", f"{_eq_txt(pl, k)} genera un servicio que ningún equipo usa.",
                          ["Un servicio auxiliar sin destino es inversión y combustible sin uso.",
                           f"La demanda de vapor y de calor de la planta es 0 kW: ningún equipo pide lo que entrega {k}.",
                           f"Una {k} con los equipos que calientan, evaporan o secan en la Planta ficticia, o quítelo si sobra."], objeto=k))
    for b in ((aux.get("bombas") or {}).get("filas") or []):
        q = b.get("Q_m3h")
        if q is not None and float(q) <= 1e-9:
            out.append(_h("A05", f"La bomba {b['id']} de la línea {b.get('linea')} no mueve caudal.",
                          ["Una bomba se justifica en una línea de líquido con caudal.",
                           f"La línea {b.get('linea')} va de {b.get('origen')} a {b.get('destino')} y lleva 0 m³/h.",
                           "Revise el reparto de esa línea en la Planta ficticia o pase la bomba a otra línea."], objeto=b["id"]))
    return out


# ---------------------------------------------------------------- Lazos de control (ISA-5.1 e ISA-5.4)
def _papel(i) -> str:
    if IN.es_controlador(i):
        return "controlador"
    if IN.es_convertidor(i):
        return "convertidor"
    if IN.es_final(i):
        return "elemento final"
    if IN.es_medicion(i):
        return "medición"
    return "auxiliar"


def describir_lazo(pl: Planta, numero) -> str:
    """Segunda pista de un lazo: sus instrumentos con su papel y las líneas de señal que ya tiene (sin decir cuál falta)."""
    L = next((x for x in IN.lazos(pl) if str(x["numero"]) == str(numero)), None)
    if L is None:
        return ""
    ms = ", ".join(f"{IN.ident(m)} ({_papel(m)})" for m in L["miembros"])
    sen = [f"{x['origen']} → {x.get('destino')} ({isa51.SENALES.get(x.get('senal'), ('?',))[0].lower()})" for x in L["senales"]]
    return f"El lazo {numero} tiene {ms}. Líneas de señal: " + ("; ".join(sen) if sen else "ninguna") + "."


def revisar_lazos(pl: Planta) -> list[dict]:
    """instrumentacion.revisar_lazos con pistas progresivas, más las reglas ISA que no revisa (I01 a I16)."""
    out = []
    for r in IN.revisar_lazos(pl):
        n = r.get("regla")
        donde = (describir_lazo(pl, r["lazo"]) if r.get("lazo") else "") or \
            ((f"Revise el lazo {r['lazo']}" if r.get("lazo") else "Revise los lazos") + (f", en el instrumento {r['objeto']}." if r.get("objeto") else "."))
        general = ISA_GENERAL.get(n) or "Revise las reglas de ISA-5.1 e ISA-5.4 del lazo."
        out.append(dict(id=f"ISA{n or 0}:{r.get('lazo') or ''}:{r.get('objeto') or ''}:{r['mensaje'][:30]}", regla=f"ISA{n or ''}",
                        nivel=r["nivel"], vista="lazos", objeto=r.get("objeto"), lazo=r.get("lazo"), mensaje=r["mensaje"],
                        pistas=[general, donde, r.get("pista") or ""], fuente=r.get("fuente") or ""))
    if not pl.instrumentos:
        return out
    ids = [IN.ident(i) for i in pl.instrumentos]
    vistos = set()
    for i, k in zip(pl.instrumentos, ids):
        if isa51.valida_isa51(i.simbolo):
            try:
                isa51.interpretar(i.letras)
                ok_letras = True
            except ValueError as e:
                ok_letras = False
                out.append(_h("I01", f"El instrumento {k} no tiene letras ISA-5.1 válidas ({e}).",
                              [ISA_GENERAL[1], f"Lea las letras de {k} con la tabla «Referencia ISA-5.1»: primera letra y letras sucesivas.",
                               f"Escriba en Propiedades de {k} letras válidas, por ejemplo TT, TIC o TV para un lazo de temperatura."], objeto=k))
            if ok_letras and not str(i.numero or "").strip():
                out.append(_h("I01", f"El instrumento {k} no tiene número de lazo.",
                              [ISA_GENERAL[1], "Los instrumentos de un mismo lazo comparten su número.",
                               f"Escriba en Propiedades de {k} el número del lazo al que pertenece."], objeto=k))
            validas = IN._ubicaciones_validas(i)
            if i.ubicacion not in validas:
                out.append(_h("I09", f"El instrumento {k} tiene una ubicación que no existe en ISA-5.1 ({i.ubicacion}).",
                              [ISA_GENERAL[9], f"Ubicaciones posibles: {', '.join(validas.values())}.",
                               f"Elija en Propiedades de {k} dónde está montado."], objeto=k))
        if k in vistos:
            out.append(_h("I04", f"La etiqueta {k} está repetida.",
                          [ISA_GENERAL[4], "Si un lazo tiene dos instrumentos iguales, cada uno lleva un sufijo (TT-101A y TT-101B) (ISA p. 13).",
                           f"Cambie el número o agregue un sufijo a uno de los dos {k}."], objeto=k))
        vistos.add(k)
        if i.equipo and i.equipo not in pl.equipos:
            out.append(_h("I16", f"El instrumento {k} está unido al equipo {i.equipo}, que ya no existe.",
                          ["Cada instrumento mide o actúa sobre un equipo o una corriente de la planta.",
                           f"{i.equipo} se quitó o cambió de nombre en la Planta ficticia.",
                           f"Una {k} al equipo que corresponde (Propiedades, campo Equipo) o quítelo."], objeto=k))
        for s in i.conexiones:
            if isinstance(s, dict) and s.get("senal") not in isa51.SENALES:
                out.append(_h("I07", f"La línea de {k} a {s.get('destino')} tiene un tipo de señal que no existe en ISA-5.1.",
                              [ISA_GENERAL[7], f"Tipos posibles: {', '.join(v[0].lower() for v in isa51.SENALES.values())}.",
                               "Elija el tipo de la línea en sus Propiedades: eléctrica entre transmisor y controlador, neumática del I/P a la válvula."],
                              objeto=k))
        letras = str(i.letras or "").upper()
        if "X" in letras and not str(i.descripcion or "").strip():
            out.append(_h("I13", f"{k} usa la letra X sin declarar su significado.",
                          [ISA_GENERAL[13], f"{k} no tiene descripción.", f"Escriba en Propiedades de {k} qué significa la X."], objeto=k))
    por_id = {k: i for i, k in zip(pl.instrumentos, ids)}
    for L in IN.lazos(pl):
        ms = L["miembros"]; num = L["numero"]
        if len(ms) > 1 and not any(str(m.descripcion or "").strip() for m in ms):
            out.append(_h("I11", f"El lazo {num} no tiene título que describa su función.",
                          [ISA_GENERAL[11], f"Ningún instrumento del lazo {num} tiene descripción.",
                           f"Escriba en Propiedades del controlador del lazo {num} qué controla y dónde."], objeto=IN.ident(L["representante"]),
                          lazo=num))
        prim = [m for m in ms if "E" in IN._funciones(m.letras) and not IN.es_controlador(m)]
        trans = [m for m in ms if "T" in IN._funciones(m.letras) and not IN.es_controlador(m)]
        for e in prim:
            if not trans:
                continue
            te = {IN.ident(t) for t in trans}
            une = any(isinstance(s, dict) and s.get("tipo") == "instrumento" and s.get("destino") in te and s.get("senal") in ("proceso", "capilar")
                      for s in e.conexiones) or \
                any(isinstance(s, dict) and s.get("tipo") == "instrumento" and s.get("destino") == IN.ident(e) and s.get("senal") in ("proceso", "capilar")
                    for t in trans for s in t.conexiones)
            if not une:
                out.append(_h("I08", f"El elemento primario {IN.ident(e)} no llega al transmisor por una conexión a proceso o un capilar.",
                              [ISA_GENERAL[8], f"En el lazo {num} el transmisor es {', '.join(sorted(te))}.",
                               f"Una {IN.ident(e)} con el transmisor y elija en Propiedades de la línea «capilar» (temperatura) o «conexión a proceso»."],
                              objeto=IN.ident(e), lazo=num))
        ids_l = {IN.ident(m) for m in ms}
        for c in [m for m in ms if IN.es_controlador(m)]:
            kc = IN.ident(c)
            meds = [ko for ko, o in por_id.items() for s in o.conexiones if isinstance(s, dict) and s.get("tipo") == "instrumento"
                    and s.get("destino") == kc and IN.es_medicion(o) and ko in ids_l and not s.get("relacion")]
            if len(meds) > 1:
                out.append(_h("I15", f"El controlador {kc} recibe {len(meds)} mediciones ({', '.join(meds)}).",
                              [ISA_GENERAL[15], "Si una segunda medición corrige al controlador, es otro lazo unido por una relación.",
                               f"Deje una medición en {kc} y pase la otra a su propio lazo, unido en prealimentación o en cascada."],
                              objeto=kc, lazo=num))
    return out


# ---------------------------------------------------------------- revisión de una pantalla
def _resumen_anterior(vista_previa: str, res: dict, codigo: str) -> dict:
    e = res["errores"]
    p = e[0]
    return _h(codigo, f"{NOMBRE_VISTA[vista_previa]} tiene {len(e)} error{'es' if len(e) > 1 else ''} de diseño sin corregir.",
              [f"Las pantallas de construcción van en orden: lo que se arma aquí parte de lo que dejó {NOMBRE_VISTA[vista_previa]}.",
               f"El primero: {p['mensaje']}",
               f"Vuelva a {NOMBRE_VISTA[vista_previa]}; su botón «Pista» lo orienta sobre ese error."], objeto=vista_previa)


def revisar(pl: Planta, vista: str, motivo: str | None = None, precedencia=None, aux: dict | None = None,
            objetivos: list[dict] | None = None, previas: dict | None = None) -> dict:
    """Revisión de una pantalla. previas: {vista: resultado o número de errores} de las pantallas anteriores ya revisadas (la
    interfaz pasa lo último que calculó); sin ese dato, la Planta ficticia y la Planta real se revisan aquí (no piden internet) y
    Equipos auxiliares no se cuenta. Devuelve {vista, hallazgos, errores, avisos, bloquea}."""
    if vista not in VISTAS:
        raise ValueError(f"Vista desconocida: {vista}. Use {', '.join(VISTAS)}")
    previas = dict(previas or {})
    hs: list[dict] = []
    codigo = {"real": "R00", "auxiliares": "A00", "lazos": "L00"}.get(vista)
    for v in ANTERIORES[vista]:
        res_v = previas.get(v)
        if res_v is None and v in ("ficticia", "real"):
            res_v = revisar(pl, v, motivo, precedencia, previas={"ficticia": previas.get("ficticia")} if v == "real" else None)
            previas[v] = res_v
        if isinstance(res_v, dict) and res_v.get("errores"):
            hs.append(_resumen_anterior(v, res_v, codigo))
        elif isinstance(res_v, int) and res_v > 0:
            hs.append(_h(codigo, f"{NOMBRE_VISTA[v]} tiene {res_v} error{'es' if res_v > 1 else ''} de diseño sin corregir.",
                         [f"Las pantallas de construcción van en orden: lo que se arma aquí parte de lo que dejó {NOMBRE_VISTA[v]}.",
                          f"Vuelva a {NOMBRE_VISTA[v]}: la advertencia de esa pantalla dice qué falla.",
                          f"Use el botón «Pista» de {NOMBRE_VISTA[v]}."], objeto=v))
    if vista == "ficticia":
        hs += revisar_ficticia(pl, motivo, precedencia)
    elif vista == "real":
        hs += revisar_real(pl)
    elif vista == "auxiliares":
        hs += revisar_auxiliares(pl, aux, objetivos)
    else:
        hs += revisar_lazos(pl)
    errores = [h for h in hs if h["nivel"] == "error"]
    avisos = [h for h in hs if h["nivel"] != "error"]
    return dict(vista=vista, hallazgos=hs, errores=errores, avisos=avisos, bloquea=bool(errores))


def pista(res: dict, nivel: int) -> dict | None:
    """Las pistas del primer error hasta el nivel pedido (1 a 3). Devuelve {objetivo (id del error), mensaje, pistas, nivel, total}
    o None si no hay errores. Nunca más de las tres pistas del error: la última dice qué cambiar en ese punto, no el diseño entero."""
    e = (res or {}).get("errores") or []
    if not e:
        return None
    p = e[0]
    tot = len(p["pistas"])
    n = max(0, min(int(nivel or 0), tot))
    return dict(objetivo=p["id"], mensaje=p["mensaje"], pistas=p["pistas"][:n], nivel=n, total=tot)


def para_lienzo(res: dict) -> list[dict]:
    """Lista del botón «Diagnóstico» del lienzo: una línea que remite a la advertencia si hay errores, y los avisos."""
    out = []
    n = len(res.get("errores") or [])
    if n:
        out.append(dict(nivel="error", texto=f"{n} error{'es' if n > 1 else ''} de diseño impide{'n' if n > 1 else ''} avanzar: "
                                             "vea la advertencia sobre el lienzo y su botón «Pista»."))
    for a in res.get("avisos") or []:
        k = a.get("objeto")
        d = dict(nivel="aviso", texto=a["mensaje"])
        if isinstance(k, str) and k:
            d["equipo"] = k.split(".")[0]          # el lienzo selecciona el equipo al hacer clic, si existe
        out.append(d)
    if not out:
        out.append(dict(nivel="ok", texto="Sin observaciones: el validador no encontró errores ni avisos en esta pantalla."))
    return out
