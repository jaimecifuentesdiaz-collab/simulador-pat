"""Internación de los equipos importados y flujo de caja con impuestos (PAT 142, tarea 7, pedido de Jaime del 19-11-2026).

Base de cálculo: investigación «Costo de internación de equipos importados a Chile y su efecto en el flujo de caja»
(docs/costo_internacion.md, fuentes consultadas el 19-11-2026). No es asesoría tributaria ni aduanera.

1. Costo puesto en planta de cada equipo (costo_equipo), en US$:
     FOB = precio según el Incoterm (+ gastos en origen si es EXW o FCA)
     CIF = FOB + flete + seguro                       (CFR: flete 0; CIF: flete y seguro 0)
     derechos = t_arancel·CIF (·1,5 si es usado)      (0 % con tratado y prueba de origen o bien de capital de la Ley 18.634)
     IVA de importación = 0,19·(CIF + derechos)       (crédito fiscal, no se activa)
     gastos = agente (0,5 % CIF) + puerto (DHC, CMD, gate in y gate out, almacenaje) + transporte a Teno (US$/t)
     puesto en planta = CIF + derechos + gastos ;  montaje = f_montaje·puesto (solo si se pide) ;  activo = puesto + montaje
   Equipo de origen Chile: sin internación (puesto en planta = precio).
2. agregar(res, cfg): suma la internación al resultado de costeo.costear. Con la internación apagada devuelve el mismo
   resultado, sin tocarlo. La internación se suma una vez, fuera del factor de instalación: el factor ya incluye el montaje y
   la internación solo reemplaza el flete y la entrega (regla de la sección 4.1 de la investigación).
3. banda(total, clase): banda de error de la clase de estimación (AACE, apunte DEI_02 Costes del curso, pág. 2.3).
4. flujo_caja(...): flujo anual con inversión (con la internación), IVA pagado y recuperado como crédito fiscal, depreciación,
   impuesto de primera categoría con la gradualidad de la Ley 21.850, valor de desecho contable, VAN y TIR (motor/economia.py).

Cada parámetro lleva su fuente y su estado: «Norma», «Supuesto justificado» (tarifa de mercado que cambia en el tiempo) o
«No verificado» (sin fuente pública; va con su justificación).
"""
from __future__ import annotations
import copy
import math

from . import economia as eco

# ---------------------------------------------------------------- catálogos
PAISES = {   # país → (acuerdo comercial que deja el arancel en 0 % con prueba de origen, o None; región de flete)
    "Chile": (None, "nacional"),
    "China": ("TLC Chile–China (D.S. 317 y D.S. 20, D.O. 03-04-2019; Servicio Nacional de Aduanas, s. f.-b)", "china"),
    "Alemania": ("Acuerdo Interino Comercial Chile–UE, desde 01-02-2025 (Servicio Nacional de Aduanas, 2025a)", "europa_norte"),
    "Italia": ("Acuerdo Interino Comercial Chile–UE, desde 01-02-2025 (Servicio Nacional de Aduanas, 2025a)", "europa_sur"),
    "Otro país de la Unión Europea": ("Acuerdo Interino Comercial Chile–UE, desde 01-02-2025 (Servicio Nacional de Aduanas, 2025a)", "europa_sur"),
    "EE. UU.": ("TLC Chile–EE. UU., 100 % libre desde 01-01-2015 (International Trade Administration, s. f.)", "otro"),
    "Brasil": ("ACE 35 Chile–Mercosur, universo libre desde 01-01-2015 (Governo do Brasil, s. f.)", "otro"),
    "Argentina": ("ACE 35 Chile–Mercosur, universo libre desde 01-01-2015 (Governo do Brasil, s. f.)", "otro"),
    "Otro país sin tratado": (None, "otro"),
}
ACUERDO_CORTO = {"China": "TLC Chile–China", "Alemania": "AIC Chile–UE", "Italia": "AIC Chile–UE",
                 "Otro país de la Unión Europea": "AIC Chile–UE", "EE. UU.": "TLC Chile–EE. UU.", "Brasil": "ACE 35", "Argentina": "ACE 35"}
INCOTERMS = ("EXW", "FCA", "FOB", "CFR", "CIF")
CARGAS = ("20'", "40'", "flat rack", "break bulk")
CONTENEDOR = ("20'", "40'")
NACIONAL = "Chile"

# fabricantes conocidos → país (para el país de origen por defecto). CFT S.p.A., Parma: https://www.cft-group.com (CFT, 2024a).
FABRICANTES = {"CFT": "Italia", "Rossi & Catelli": "Italia", "Bertuzzi": "Italia", "GEA": "Alemania", "Made-in-China": "China"}
MODELOS_FABRICANTE = {"Apollo": "CFT", "ART3MIS": "CFT", "Venus": "CFT"}   # modelos de evaporadores de CFT (CFT, 2024a; s. f.)
# equipos que no caben en un contenedor (Supuesto: evaporadores, secadores y calderas industriales de gran tamaño)
SOBREDIMENSIONADOS = ("evaporador_mvr", "evaporador_multiefecto", "secador_rotatorio", "secador_banda", "caldera_gas",
                      "generador_biomasa")
# factor de mano de obra de montaje sobre el costo del equipo entregado, Loh et al. (2002), tabla 6
MONTAJE = {"intercambiador": 0.20, "bomba_calor": 0.20, "caldera_gas": 0.30, "generador_biomasa": 0.30}
MONTAJE_DEF = 0.20
FUENTE_MONTAJE = ("Loh, Lyons y White (2002), Process equipment cost estimation, DOE/NETL-2002/1169, tabla 6: intercambiador "
                  "y estanque 20 %, horno 30 %, filtro 15 %; el resto, 20 % (Supuesto)")


def _p(valor, fuente, estado, nombre, unidad):
    return dict(valor=valor, fuente=fuente, estado=estado, nombre=nombre, unidad=unidad)


NORMA, SUP, NOV = "Norma", "Supuesto justificado", "No verificado"
# PAT 142: parámetros por defecto (sección 6.2 de la investigación), cada uno con su fuente, fecha y estado
PARAMETROS = {
    "flete_china_20": _p(5100.0, "Good Hope Freight (2026), lista del 05-11-2026, Qingdao o Shanghái a San Antonio, 20GP", SUP,
                         "Flete China, contenedor de 20'", "US$ por contenedor"),
    "flete_china_40": _p(5600.0, "Good Hope Freight (2026), lista del 10-11-2026, Qingdao o Shanghái a San Antonio, 40HQ", SUP,
                         "Flete China, contenedor de 40'", "US$ por contenedor"),
    "flete_europa_20": _p(3000.0, "Ocean Network Express (2026a), tarifa base FAK Hamburgo o Amberes, vigente desde 01-01-2026, sin recargos",
                          SUP, "Flete norte de Europa, contenedor de 20'", "US$ por contenedor"),
    "flete_europa_40": _p(4000.0, "Ocean Network Express (2026a), tarifa base FAK Hamburgo o Amberes, vigente desde 01-01-2026, sin recargos",
                          SUP, "Flete norte de Europa, contenedor de 40'", "US$ por contenedor"),
    "flete_presunto": _p(0.05, "Flete presunto marítimo de Aduanas, 5 % del FOB (Servicio Nacional de Aduanas, s. f., Compendio de Normas "
                               "Aduaneras, cap. 2, num. 2.7). Se usa sin tarifa pública: Italia, EE. UU., Brasil, Argentina y carga "
                               "fuera de contenedor", NORMA, "Flete sin tarifa publicada", "fracción del FOB"),
    "seguro": _p(0.02, "Seguro presunto de Aduanas, 2 % del FOB (Servicio Nacional de Aduanas, s. f., cap. 2, num. 2.7)", NORMA,
                 "Seguro", "fracción del FOB"),
    "arancel": _p(0.06, "Derecho ad valorem general, 6 % del CIF (Servicio Nacional de Aduanas, 2026a, 07-09-2026)", NORMA,
                  "Arancel general", "fracción del CIF"),
    "recargo_usado": _p(0.50, "Recargo de 50 % sobre el derecho ad valorem para mercancía usada (Servicio Nacional de Aduanas, 2026a)",
                        NORMA, "Recargo por equipo usado", "fracción del derecho"),
    "iva": _p(0.19, "D.L. 825, art. 14 (tasa) y art. 16 letra a (base CIF más derechos); crédito fiscal, art. 23 N.º 1 (SII, 2022)",
              NORMA, "IVA", "fracción"),
    "agente": _p(0.005, "Honorario del agente de aduana, 0,5 % del CIF (rango 0,5 a 1,5 %); Chilat (2026, 12-10-2026), referencia de "
                        "operadores privados, no tarifa oficial", SUP, "Honorario del agente de aduana", "fracción del CIF"),
    "dhc": _p(175.0, "DHC de destino de Maersk para contenedor seco, vigente desde 15-10-2026 (Maersk, 2026)", SUP,
              "Manejo en el puerto de destino (DHC)", "US$ por contenedor"),
    "cmd_20": _p(100.0, "Cargo CMD de importación de ONE, 20', vigente desde abril de 2026 (Ocean Network Express, 2026b)", SUP,
                 "Cargo documental (CMD), 20'", "US$ por contenedor"),
    "cmd_40": _p(130.0, "Cargo CMD de importación de ONE, 40', vigente desde abril de 2026 (Ocean Network Express, 2026b)", SUP,
                 "Cargo documental (CMD), 40'", "US$ por contenedor"),
    "gate_clp": _p(90000.0, "Gate in y gate out, $45.000 cada uno, marzo de 2026 (Ocean Network Express, 2026c)", SUP,
                   "Gate in y gate out", "$ por contenedor"),
    "almacenaje_clp": _p(145000.0, "Almacenaje seco en San Antonio por 10 días, más IVA, agosto de 2026 (Hapag-Lloyd, 2026)", SUP,
                         "Almacenaje en el puerto (10 días)", "$ por contenedor"),
    "transporte_usd_t": _p(25.14, "Transporte local de la cadena Maule–San Antonio, datos de 2019 (Steer, 2020, informe del 23-01-2020); "
                                  "San Antonio a Teno 174 km (CalcularRuta, s. f.). Desactualizado: actualizar con una cotización", SUP,
                           "Transporte del puerto a la planta", "US$ por tonelada"),
    "tc": _p(981.08, "Equivalencia aduanera de noviembre de 2026, 29-10-2026 (Servicio Nacional de Aduanas, 2026b). Solo convierte a US$ "
                     "los cargos del puerto cotizados en pesos", NORMA, "Tipo de cambio aduanero", "$ por US$"),
}
EQUIPO_DEF = dict(pais=NACIONAL, incoterm="FOB", carga="40'", n_cont=1, peso_t=20.0, gastos_origen_usd=0.0, flete_usd=None,
                  prueba_origen=True, bien_capital=False, usado=False)
JUST_EQUIPO = ("Supuesto: precio FOB, un contenedor de 40' de 20 t por unidad y prueba de origen al día; los equipos de gran tamaño van fuera de contenedor (break bulk) con el flete presunto de 5 % del FOB")

# clases de estimación de la AACE: clave → (nombre, error mínimo, error máximo), DEI_02 Costes, pág. 2.3 (PDF p. 5)
CLASES = {"orden_magnitud": ("Orden de magnitud", 0.40, 0.50), "estudio": ("Estudio", 0.25, 0.40),
          "preliminar": ("Preliminar", 0.15, 0.25), "definitiva": ("Definitiva", 0.10, 0.15), "detallada": ("Detallada", 0.05, 0.10)}
FUENTE_CLASES = ("Clases de estimación de la AACE en el apunte DEI_02 Costes del curso, pág. 2.3 (PDF p. 5): orden de magnitud "
                 "40 a 50 %, estudio 25 a 40 %, preliminar 15 a 25 %, definitiva 10 a 15 % y detallada 5 a 10 % de error")
CLASE_DEF = "estudio"
JUST_CLASE = ("Estudio: la estimación parte de la lista de equipos de la planta simulada con factores; la clase preliminar pide "
              "además el costo del emplazamiento, que no está (DEI_02 Costes, pág. 2.3)")


def parametros(cambios: dict | None = None) -> dict:
    """Valores de los parámetros ({clave: valor}) con los cambios del usuario sobre los de PARAMETROS."""
    out = {k: v["valor"] for k, v in PARAMETROS.items()}
    for k, v in (cambios or {}).items():
        if k in out and v is not None:
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                pass
    return out


# ---------------------------------------------------------------- país de origen por defecto
def _textos_equipo(eq) -> list[str]:
    t = [str(getattr(eq, "nombre", "") or "")]
    params = getattr(eq, "params", {}) or {}
    if "modelo" in params:
        t.append(str(params["modelo"].valor or ""))
    for p in params.values():
        f = str(getattr(p, "fuente", "") or "")
        if any(f.startswith(m) for m in FABRICANTES) or "fabricante" in f.lower():
            t.append(f)
    return t


def pais_por_defecto(eq) -> tuple[str, str]:
    """(país, justificación) de un equipo de la planta: el del fabricante que ya trae (nombre, modelo o fuente de un parámetro que
    empieza con el fabricante o dice «fabricante»); si no hay, Chile sin internación."""
    if eq is None:
        return NACIONAL, "Sin fabricante declarado: compra nacional, sin internación"
    for txt in _textos_equipo(eq):
        for mod, fab in MODELOS_FABRICANTE.items():
            if mod.lower() in txt.lower():
                return FABRICANTES[fab], f"Modelo {mod} del fabricante {fab} ({FABRICANTES[fab]})"
        for fab, pais in FABRICANTES.items():
            if fab in txt:
                return pais, f"Fabricante {fab} ({pais}) declarado en los datos del equipo"
    return NACIONAL, "Sin fabricante declarado: compra nacional, sin internación"


def config_por_defecto(fila: dict, eq=None) -> dict:
    """Configuración de internación de una fila de costeo: país del fabricante (o Chile), FOB, contenedor o break bulk."""
    pais, just = pais_por_defecto(eq)
    clave = fila.get("clave", "")
    n = int(fila.get("unidades") or 1) if clave not in ("caneria", "cable_electrico", "valvula_control") else 1
    carga = "break bulk" if clave in SOBREDIMENSIONADOS else "40'"
    return dict(EQUIPO_DEF, pais=pais, carga=carga, n_cont=max(1, n), peso_t=20.0 * max(1, n), justificacion=just)


# ---------------------------------------------------------------- costo de un equipo
def flete_tabla(pais: str, carga: str, P: dict) -> float | None:
    """Flete por contenedor de la tabla (US$), o None si el origen o la carga no tienen tarifa publicada."""
    region = PAISES.get(pais, (None, "otro"))[1]
    if carga not in CONTENEDOR:
        return None
    t = "20" if carga == "20'" else "40"
    if region == "china":
        return P[f"flete_china_{t}"]
    if region == "europa_norte":
        return P[f"flete_europa_{t}"]
    return None


def tasa_arancel(pais: str, prueba_origen: bool, bien_capital: bool, P: dict) -> tuple[float, str]:
    """(tasa, razón corta): 0 % con tratado y prueba de origen o con bien de capital de la Ley 18.634; si no, la general.
    La fuente completa de cada acuerdo está en PAISES."""
    g = f"{P['arancel'] * 100:g} %".replace(".", ",")
    if bien_capital:
        return 0.0, "0 %, bien de capital (Ley 18.634)"
    acuerdo = PAISES.get(pais, (None, "otro"))[0]
    if acuerdo and prueba_origen:
        return 0.0, f"0 %, {ACUERDO_CORTO.get(pais, 'tratado')}"
    if acuerdo:
        return P["arancel"], f"{g}, sin prueba de origen"
    return P["arancel"], f"{g}, sin tratado"


def costo_equipo(precio_usd: float, cfg: dict | None = None, parametros_: dict | None = None, f_montaje: float = 0.0) -> dict:
    """Costo puesto en planta de un equipo (US$) con su desglose. cfg: pais, incoterm, carga, n_cont, peso_t, gastos_origen_usd,
    flete_usd (None: de la tabla o presunto), prueba_origen, bien_capital, usado. f_montaje: fracción del costo puesto en planta
    que se suma como montaje (0 si el factor de instalación ya lo incluye)."""
    c = dict(EQUIPO_DEF); c.update({k: v for k, v in (cfg or {}).items() if v is not None or k == "flete_usd"})
    P = parametros(parametros_)
    precio = max(float(precio_usd or 0.0), 0.0)
    vacio = dict(precio=precio, fob=precio, flete=0.0, seguro=0.0, cif=precio, t_arancel=0.0, arancel=0.0, iva_importacion=0.0,
                 agente=0.0, puerto=0.0, transporte=0.0, gastos=0.0, iva_locales=0.0, puesto_planta=precio, montaje=0.0,
                 activo=precio, extra=0.0, importado=False, flete_origen="", razon_arancel="Compra nacional", avisos=[])
    if c["pais"] == NACIONAL or precio <= 0:
        if f_montaje:
            vacio.update(montaje=f_montaje * precio, activo=precio * (1 + f_montaje), extra=f_montaje * precio)
        return vacio
    avisos = []
    inc = c["incoterm"] if c["incoterm"] in INCOTERMS else "FOB"
    fob = precio + (max(float(c.get("gastos_origen_usd") or 0.0), 0.0) if inc in ("EXW", "FCA") else 0.0)
    if inc in ("EXW", "FCA") and not c.get("gastos_origen_usd"):
        avisos.append(f"Precio {inc} sin gastos en origen: cotizarlos (No verificado, se usa 0)")
    carga = c["carga"] if c["carga"] in CARGAS else "40'"
    n_cont = max(int(c.get("n_cont") or 1), 1)
    if inc in ("CFR", "CIF"):
        flete, f_org = 0.0, f"Incluido en el precio {inc}"
    elif c.get("flete_usd") is not None:
        flete, f_org = float(c["flete_usd"]), "Cotización del usuario"
    else:
        ft = flete_tabla(c["pais"], carga, P)
        if ft is not None:
            flete, f_org = ft * n_cont, f"Tarifa por contenedor × {n_cont}"
        else:
            flete, f_org = P["flete_presunto"] * fob, "Flete presunto, 5 % del FOB (sin tarifa publicada)"
    seguro = 0.0 if inc == "CIF" else P["seguro"] * fob
    cif = fob + flete + seguro
    t, razon = tasa_arancel(c["pais"], bool(c.get("prueba_origen", True)), bool(c.get("bien_capital")), P)
    arancel = t * cif * ((1.0 + P["recargo_usado"]) if c.get("usado") and t > 0 else 1.0)
    iva_imp = P["iva"] * (cif + arancel)
    n_puerto = n_cont if carga in CONTENEDOR else 0
    if carga not in CONTENEDOR:
        avisos.append(f"Carga {carga}: gastos del puerto y escolta sin tarifa pública (No verificado, se usan 0)")
    agente = P["agente"] * cif
    cmd = P["cmd_20"] if carga == "20'" else P["cmd_40"]
    puerto = n_puerto * (P["dhc"] + cmd + (P["gate_clp"] + P["almacenaje_clp"]) / P["tc"])
    transporte = P["transporte_usd_t"] * max(float(c.get("peso_t") or 0.0), 0.0)
    gastos = agente + puerto + transporte
    iva_loc = P["iva"] * gastos
    puesto = cif + arancel + gastos
    montaje = max(float(f_montaje or 0.0), 0.0) * puesto
    activo = puesto + montaje
    return dict(precio=precio, fob=fob, flete=flete, seguro=seguro, cif=cif, t_arancel=t, arancel=arancel, iva_importacion=iva_imp,
                agente=agente, puerto=puerto, transporte=transporte, gastos=gastos, iva_locales=iva_loc, puesto_planta=puesto,
                montaje=montaje, activo=activo, extra=activo - precio, importado=True, flete_origen=f_org, razon_arancel=razon,
                avisos=avisos)


# ---------------------------------------------------------------- internación de todo el costeo
SUMAS = ("precio", "fob", "flete", "seguro", "cif", "arancel", "iva_importacion", "agente", "puerto", "transporte", "gastos",
         "iva_locales", "puesto_planta", "montaje", "activo", "extra")
RECUPERACION = ("intercambiador", "bomba_calor")


def internacion(filas: list[dict], equipos: dict | None = None, parametros_: dict | None = None, sumar_montaje: bool = False,
                pl=None) -> dict:
    """Internación de cada fila de costeo. equipos: {id de equipo: cfg} con lo que el usuario cambió; lo que falta sale de
    config_por_defecto (con el equipo de la planta pl, si se da). Devuelve filas (con equipo, nombre, pais y el desglose de
    costo_equipo), totales (US$), totales_recuperacion (solo recuperadores), avisos y los parámetros usados."""
    P = parametros(parametros_)
    equipos = equipos or {}
    out, avisos = [], []
    tot = {k: 0.0 for k in SUMAS}; rec = {k: 0.0 for k in SUMAS}
    for f in filas or []:
        eid = str(f.get("equipo"))
        eq = getattr(pl, "equipos", {}).get(eid) if pl is not None else None
        cfg = config_por_defecto(f, eq)
        cfg.update({k: v for k, v in (equipos.get(eid) or {}).items() if k in EQUIPO_DEF})
        fm = MONTAJE.get(f.get("clave"), MONTAJE_DEF) if sumar_montaje else 0.0
        r = costo_equipo(float(f.get("costo_usd") or 0.0), cfg, P, fm)
        r.update(equipo=eid, nombre=f.get("nombre", ""), clave=f.get("clave", ""), pais=cfg["pais"], incoterm=cfg["incoterm"],
                 carga=cfg["carga"], n_cont=cfg["n_cont"], peso_t=cfg["peso_t"], prueba_origen=bool(cfg["prueba_origen"]),
                 bien_capital=bool(cfg["bien_capital"]), usado=bool(cfg["usado"]), justificacion=cfg.get("justificacion", ""),
                 f_montaje=fm)
        out.append(r)
        for k in SUMAS:
            tot[k] += r[k]
            if r["clave"] in RECUPERACION:
                rec[k] += r[k]
        avisos += [f"{eid}: {a}" for a in r["avisos"]]
    n_imp = sum(1 for r in out if r["importado"])
    return dict(filas=out, totales=tot, totales_recuperacion=rec, n_importados=n_imp, avisos=avisos, parametros=P,
                sumar_montaje=bool(sumar_montaje))


def agregar(res: dict, cfg: dict | None = None, pl=None) -> dict:
    """Suma la internación al resultado de costeo.costear. cfg: activa (bool), equipos, parametros, sumar_montaje.
    Apagada (o sin cfg) devuelve res tal cual. Encendida devuelve una copia con res['internacion'] y los totales de la planta
    y de la recuperación aumentados en lo que la internación agrega sobre el precio (extra), en US$ y en pesos."""
    cfg = cfg or {}
    if not cfg.get("activa") or not res:
        return res
    out = copy.copy(res)
    I = internacion(res.get("filas", []), cfg.get("equipos"), cfg.get("parametros"), bool(cfg.get("sumar_montaje")), pl)
    dolar = float(res.get("dolar") or 0.0)
    t = dict(res.get("totales", {}))
    ex, ex_rec = I["totales"]["extra"], I["totales_recuperacion"]["extra"]
    t["total_sin_internacion_usd"] = t.get("total_usd", 0.0)
    t["internacion_usd"] = ex
    t["total_usd"] = t.get("total_usd", 0.0) + ex
    t["recuperacion_usd"] = t.get("recuperacion_usd", 0.0) + ex_rec
    t["recuperacion_internacion_usd"] = ex_rec
    for k in [k for k in t if k.endswith("_usd")]:
        t[k.replace("_usd", "_clp")] = t[k] * dolar
    out["totales"] = t
    I["totales_clp"] = {k: v * dolar for k, v in I["totales"].items()}
    out["internacion"] = I
    avisos = list(res.get("avisos", []))
    if (res.get("metodo_costeo") or {}).get("avisos") and any("Flete hasta la planta" in a for a in res["metodo_costeo"]["avisos"]):
        avisos.append("El flete hasta la planta del método de costeo y la internación cuentan dos veces la entrega: deje uno solo")
    out["avisos"] = avisos
    return out


def resumen_llevar(res: dict, que: str = "planta") -> dict:
    """Lo que se lleva a Economía (M$): inversión que agrega la internación, derechos (no recuperables) e IVA de importación y de
    los gastos locales (crédito fiscal), de la planta completa (que = 'planta') o solo de los recuperadores ('recuperacion')."""
    I = (res or {}).get("internacion")
    if not I:
        return dict(extra_m=0.0, arancel_m=0.0, iva_internacion_m=0.0, n_importados=0)
    d = float(res.get("dolar") or 0.0) / 1e6
    T = I["totales"] if que == "planta" else I["totales_recuperacion"]
    n = I["n_importados"] if que == "planta" else sum(1 for r in I["filas"] if r["importado"] and r["clave"] in RECUPERACION)
    return dict(extra_m=T["extra"] * d, arancel_m=T["arancel"] * d, iva_internacion_m=(T["iva_importacion"] + T["iva_locales"]) * d,
                n_importados=n)


# ---------------------------------------------------------------- banda de error de la estimación
def banda(total: float, clase: str = CLASE_DEF) -> dict:
    """Banda de error de la clase de estimación (AACE, DEI_02 Costes, pág. 2.3): el total con ± el error máximo de la clase."""
    nombre, emin, emax = CLASES.get(clase, CLASES[CLASE_DEF])
    total = float(total or 0.0)
    return dict(clase=clase if clase in CLASES else CLASE_DEF, nombre=nombre, error_min=emin, error_max=emax,
                bajo=total * (1 - emax), alto=total * (1 + emax), total=total, fuente=FUENTE_CLASES)


# ---------------------------------------------------------------- flujo de caja con impuestos
# Impuesto de primera categoría, régimen general: 27 % (Ley sobre Impuesto a la Renta, D.L. 824, art. 20) y, con la Ley 21.850
# para la Reconstrucción Nacional (D.O. 17-10-2026), 25,5 % en el año tributario 2028, 24 % en el 2029 y 23 % desde el 2030
# (SII, noticia del 19-10-2026, https://www.sii.cl/noticias/2026/191026noti01pcr.htm). El año tributario es el año comercial + 1.
RENTA_POR_AT = {2028: 0.255, 2029: 0.24, 2030: 0.23}
RENTA_GENERAL = 0.27
FUENTE_RENTA = ("Impuesto de primera categoría del régimen general: 27 % (D.L. 824, art. 20) y, con la Ley 21.850 (D.O. "
                "17-10-2026), 25,5 % en el año tributario 2028, 24 % en el 2029 y 23 % desde el 2030 (SII, 19-10-2026). El año "
                "tributario es el año comercial más uno")
VIDA = {"acelerada": (5, "Depreciación acelerada, un tercio de la vida normal de maquinarias y equipos en general (SII, 2002, "
                         "Res. Ex. N.º 43; D.L. 824, art. 31 N.º 5)"),
        "normal": (15, "Vida útil normal de maquinarias y equipos en general (SII, 2002, Res. Ex. N.º 43)")}
JUST_VIDA = ("Supuesto: intercambiadores, calderas y equipos de proceso se asimilan a maquinarias y equipos en general (la tabla "
             "del SII no los nombra; SII, 2002, resolutivo 3)")
CASOS_IVA = {"A": "Empresa en operación: el IVA se imputa como crédito fiscal del mismo período y se recupera en el año 0 "
                  "(D.L. 825, art. 23 N.º 1)",
             "B": "Proyecto nuevo o con remanente: devolución anticipada del remanente por activo fijo (D.L. 825, art. 27 bis); se "
                  "lleva al año 1 por prudencia"}
ANIO_INVERSION = 2027
JUST_ANIO = "Supuesto: la inversión se hace en 2027 y la primera temporada con ahorro es 2028"
JUST_DESECHO = ("Supuesto: valor de desecho contable, el valor libro al final del horizonte (activo no depreciado más terreno), sin "
                "efecto tributario porque se vende a valor libro")
JUST_PERDIDA = ("Con otras utilidades de la empresa, la pérdida tributaria del proyecto rebaja el impuesto de la empresa en el "
                "mismo año (ahorro tributario); sin ellas, se arrastra a los años siguientes")
FLUJO_DEF = dict(tasa_renta_modo="ley", tasa_renta=RENTA_GENERAL, regimen_dep="acelerada", caso_iva="A", anio_inversion=ANIO_INVERSION,
                 otras_utilidades=True, valor_desecho=True, clase_estimacion=CLASE_DEF)


def opciones_flujo(E: dict | None) -> dict:
    """Opciones del flujo con impuestos guardadas en la economía de la sesión, con su valor por defecto si faltan (proyectos
    guardados antes de PAT 142 cargan igual)."""
    E = E or {}
    out = dict(FLUJO_DEF)
    for k in FLUJO_DEF:
        if E.get(k) is not None:
            out[k] = E[k]
    if out["regimen_dep"] not in VIDA:
        out["regimen_dep"] = FLUJO_DEF["regimen_dep"]
    if out["caso_iva"] not in CASOS_IVA:
        out["caso_iva"] = FLUJO_DEF["caso_iva"]
    if out["clase_estimacion"] not in CLASES:
        out["clase_estimacion"] = CLASE_DEF
    return out


def tasa_renta(anio_comercial: int, modo: str = "ley", tasa_fija: float = RENTA_GENERAL) -> float:
    """Tasa del impuesto de primera categoría del año comercial: con modo 'ley', la gradualidad de la Ley 21.850; si no, la fija."""
    if modo != "ley":
        return float(tasa_fija)
    at = int(anio_comercial) + 1
    if at < min(RENTA_POR_AT):
        return RENTA_GENERAL
    return RENTA_POR_AT.get(at, RENTA_POR_AT[max(RENTA_POR_AT)])


def flujo_caja(inversion: float, ahorro_anual: float, costo_anual: float, anios: int, tasa: float, terreno: float = 0.0,
               iva: float | None = None, tasa_iva: float = 0.19, caso_iva: str = "A", regimen_dep: str = "acelerada",
               vida_util: int | None = None, tasa_renta_modo: str = "ley", tasa_renta_fija: float = RENTA_GENERAL,
               anio_inversion: int = ANIO_INVERSION, otras_utilidades: bool = True, valor_desecho: bool = True,
               internacion_m: float = 0.0, **_otros) -> dict:
    """Flujo de caja anual (en las unidades de la inversión, por ejemplo M$). Año 0: −inversión (activo depreciable + terreno),
    −IVA pagado y, en el caso A, +IVA recuperado; en el caso B el IVA vuelve en el año 1. Años 1 a n: ahorro − costo de operación
    − depreciación = utilidad antes de impuesto; impuesto de primera categoría del año; + depreciación; en el último año, valor de
    desecho contable. iva: IVA de la inversión (crédito fiscal); None = tasa_iva × (inversión − terreno), porque equipos,
    internación, montaje y servicios pagan IVA. internacion_m: parte de la inversión que es internación (solo para informar).
    Devuelve filas por año, VAN y TIR (motor/economia.py), recuperación y el VAN y la TIR sin impuestos para comparar."""
    inversion = max(float(inversion or 0.0), 0.0); terreno = min(max(float(terreno or 0.0), 0.0), inversion)
    anios = max(int(anios or 1), 1)
    dep_base = inversion - terreno
    vida = int(vida_util or VIDA.get(regimen_dep, VIDA["acelerada"])[0])
    iva = tasa_iva * dep_base if iva is None else max(float(iva), 0.0)
    anio_rec = 0 if caso_iva == "A" else 1
    filas, perdida = [], 0.0
    for t in range(anios + 1):
        f = dict(anio=t, anio_calendario=int(anio_inversion) + t, ahorro=0.0, costo=0.0, depreciacion=0.0, uai=0.0, tasa_renta=0.0,
                 impuesto=0.0, inversion=0.0, iva_pagado=0.0, iva_recuperado=0.0, valor_desecho=0.0)
        if t == 0:
            f.update(inversion=-inversion, iva_pagado=-iva)
        else:
            dep = dep_base / vida if t <= vida else 0.0
            f.update(ahorro=float(ahorro_anual), costo=-float(costo_anual), depreciacion=-dep)
            uai = float(ahorro_anual) - float(costo_anual) - dep
            tr = tasa_renta(f["anio_calendario"], tasa_renta_modo, tasa_renta_fija)
            base = uai
            if not otras_utilidades:
                base = uai - perdida
                perdida = max(-base, 0.0)
                base = max(base, 0.0)
            f.update(uai=uai, tasa_renta=tr, impuesto=-tr * base)
        if t == anio_rec:
            f["iva_recuperado"] = iva
        if t == anios and valor_desecho:
            libro = dep_base - dep_base / vida * min(anios, vida)
            f["valor_desecho"] = libro + terreno
        for k in ("ahorro", "costo", "depreciacion", "uai", "impuesto", "inversion", "iva_pagado"):
            f[k] = f[k] + 0.0                        # sin «-0,0» en la tabla
        f["utilidad_neta"] = f["uai"] + f["impuesto"]
        f["flujo"] = (f["utilidad_neta"] - f["depreciacion"] + f["inversion"] + f["iva_pagado"] + f["iva_recuperado"]
                      + f["valor_desecho"])
        f["flujo_desc"] = f["flujo"] / (1 + tasa) ** t
        filas.append(f)
    acum = 0.0; rec = None
    for f in filas:
        prev = acum; acum += f["flujo"]; f["acumulado"] = acum
        if rec is None and f["anio"] > 0 and acum >= 0 and prev < 0 and f["flujo"] > 0:
            rec = f["anio"] - 1 + (-prev) / f["flujo"]
    flujos = [f["flujo"] for f in filas]
    sin = eco.evaluacion(inversion, float(ahorro_anual), float(costo_anual), anios, tasa)
    return dict(filas=filas, flujos=flujos, VAN=eco.van(flujos, tasa), TIR=eco.tir(flujos) if inversion > 0 else None,
                recuperacion_anios=rec, vida_util=vida, iva=iva, anio_recuperacion_iva=anio_rec, inversion=inversion,
                terreno=terreno, internacion=float(internacion_m or 0.0), VAN_sin_impuestos=sin["VAN"], TIR_sin_impuestos=sin["TIR"],
                impuesto_total=-sum(f["impuesto"] for f in filas), depreciacion_total=-sum(f["depreciacion"] for f in filas))


def flujo_desde_economia(E: dict, inversion_m: float, ahorro_m: float) -> dict:
    """Flujo con impuestos con la economía de la sesión (M$): tasa, horizonte, costo anual, opciones del flujo y lo que Costeo llevó
    de la internación y el terreno (solo si la inversión evaluada es la llevada desde Costeo)."""
    E = E or {}
    o = opciones_flujo(E)
    desde_costeo = not E.get("inv_auto", True) and E.get("inv_costeo_m") is not None and \
        abs(float(E.get("inv_costeo_m") or 0.0) - float(inversion_m or 0.0)) < 0.051
    terreno = float(E.get("terreno_m") or 0.0) if desde_costeo else 0.0
    inter = float(E.get("internacion_m") or 0.0) if desde_costeo else 0.0
    def _f(inv, ter, inter_=0.0):
        return flujo_caja(inv, ahorro_m, float(E.get("costo_anual") or 0.0), int(E.get("anios") or 20), float(E.get("tasa") or 0.10),
                          terreno=ter, caso_iva=o["caso_iva"], regimen_dep=o["regimen_dep"], tasa_renta_modo=o["tasa_renta_modo"],
                          tasa_renta_fija=float(o["tasa_renta"]), anio_inversion=int(o["anio_inversion"]),
                          otras_utilidades=bool(o["otras_utilidades"]), valor_desecho=bool(o["valor_desecho"]), internacion_m=inter_)
    r = _f(inversion_m, terreno, inter)
    b = banda(inversion_m, o["clase_estimacion"])
    r_bajo = _f(b["bajo"], terreno * (1 - b["error_max"]))
    r_alto = _f(b["alto"], terreno * (1 + b["error_max"]))
    r.update(opciones=o, banda=b, VAN_banda=(r_alto["VAN"], r_bajo["VAN"]), desde_costeo=desde_costeo)
    return r
