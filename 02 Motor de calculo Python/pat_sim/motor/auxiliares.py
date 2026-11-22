"""Equipos auxiliares de la planta (PAT 136, tarea T23; punto 10c de los comentarios del profesor Torres del 13-11-2026).

Tercera pantalla de construcción, después de la planta ficticia (Diseño) y la planta real (selección de equipos comerciales):
lo que no es una operación unitaria pero hace falta para que la planta funcione.

- Bombas: las líneas de líquido de motor/hidraulica.py (red_hidraulica) con su caudal, altura y potencia; las que el diagrama ya
  trae y las que el costeo agrega por línea sin bomba. Solo se llama a la red hidráulica y al costeo.
- Válvulas: las de control de los lazos (Cv de motor/hidraulica.cv_requerido, la misma lista del costeo) y las de bloqueo y retención
  de cada bomba (cantidad, sin precio: costeo.py no trae referencia).
- Estanques pulmón entre equipos consecutivos de la línea principal (motor/linea_fluida.linea_principal), dimensionados con el
  tiempo de residencia (el mismo Supuesto de 30 min de la Línea), con el pulmón por falla (MTTR del equipo de aguas arriba por el
  flujo que pide el de aguas abajo) o con el mayor de los dos. El costo es un Supuesto escalado con Williams y el CEPCI de
  motor/costeo.py.
- Cañerías: las mismas líneas, con el diámetro nominal de motor/costeo.py y el largo del layout (sin layout, 30 m por línea).
- Servicios: vapor, calor, agua, aire y electricidad con su demanda y su costo, tomado del costeo (caldera o generador, cable) y de
  las tarifas de Economía (electricidad).

Todo se calcula con costeo.costear() y hidraulica.red_hidraulica(): este módulo no agrega correlaciones de costo propias salvo la del
estanque, declarada Supuesto. Con la planta vacía o sin resolver devuelve listas vacías y un aviso, nunca falla.
"""
from __future__ import annotations
import math

from . import costeo as CO, costos, hidraulica as HID, linea_fluida as LF, seleccion as SEL
from .operacion import Supuesto

_SD = "sin dato de la planta ni fuente segura"
SUPUESTOS = {s.clave: s for s in [
    Supuesto("residencia_min", "Tiempo de residencia del estanque pulmón", LF.SUPUESTOS["tanque_min"].valor, "min",
             "El mismo pulmón corto de la pestaña Línea (motor/linea_fluida.py): una detención breve no para de inmediato toda la línea; " + _SD),
    Supuesto("cobertura_falla", "Cobertura del pulmón por falla", 1.0, "veces el MTTR",
             "El pulmón por falla cubre una reparación de duración media del equipo de aguas arriba; con reparaciones exponenciales, "
             "cubrir 95 % de las fallas pide cerca de 3 veces el MTTR (se cambia en la interfaz); " + _SD),
    Supuesto("llenado", "Nivel máximo de llenado del estanque", 0.8, "fracción",
             "El volumen útil es 80 % del geométrico, para dejar espacio de gases y de rebose; " + _SD),
    Supuesto("relacion_hd", "Altura sobre diámetro del estanque", 2.0, "—",
             "Estanque cilíndrico vertical con altura igual a dos diámetros, una proporción usual de estanques de proceso; " + _SD),
    Supuesto("densidad_solido", "Densidad aparente de un sólido a granel", 400.0, "kg/m³",
             "Un solo valor para biomasa y producto a granel (silos entre equipos de sólidos), entre el de la astilla y el del pellet; "
             "no sale de una fuente: se reemplaza con el dato del material; " + _SD),
    Supuesto("precio_estanque", "Precio de un estanque de acero inoxidable de 10 m³ (año 2023)", 20000.0, "US$",
             "Orden de magnitud de partida, escalado con Williams (n = 0,6) y el CEPCI de costeo.py; se reemplaza con una cotización o "
             "con el precio de internet (Tavily); " + _SD),
    Supuesto("volumen_ref", "Volumen del estanque de referencia", 10.0, "m³", "Tamaño al que se da el precio de referencia; " + _SD),
    Supuesto("bloqueo_por_bomba", "Válvulas de bloqueo por bomba", 2.0, "unidades",
             "Una de aislación en la succión y otra en la descarga de cada bomba, más una de retención; " + _SD),
]}
ANIO_REF_ESTANQUE = 2023
AG_RHO = 1000.0     # kg/m³; el mismo valor de motor/agua.py (RHO_AGUA_CAPTADA)
METODOS_PULMON = ("residencia", "falla", "mayor")
NOMBRE_METODO = dict(residencia="Tiempo de residencia", falla="Pulmón por falla", mayor="El mayor de los dos")


def _aviso_vacio(pl) -> str | None:
    if not getattr(pl, "equipos", None):
        return "La planta está vacía: agregue equipos en Diseño para dimensionar sus equipos auxiliares."
    if not getattr(pl, "resuelta", False):
        return "La planta no está resuelta: resuélvala en Diseño para dimensionar sus equipos auxiliares."
    return None


def _num(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _filas_costeo(pl, longitudes, cables_m, res, kw) -> list[dict]:
    """Filas del costeo (precio de bibliografía o Supuesto, sin internet) de la planta. res permite reutilizar un costeo ya hecho."""
    if res is not None:
        return list(res.get("filas") or [])
    try:
        return CO.costear(pl, X={}, longitudes=longitudes, cables_m=cables_m, **kw)["filas"]
    except Exception:
        return []


def _por_clave(filas, *claves) -> list[dict]:
    return [f for f in filas if f.get("clave") in claves]


def _costo(f: dict | None) -> dict:
    if not f:
        return dict(costo_usd=None, costo_clp=None, fuente_costo="Sin referencia en costeo.py", origen_costo="")
    return dict(costo_usd=f["costo_usd"], costo_clp=f["costo_clp"], fuente_costo=f"{f.get('fuente', '')} ({f.get('categoria', '')})",
                origen_costo=f.get("origen", ""))


# ---------------------------------------------------------------- bombas
def bombas(pl, filas_costeo: list[dict] | None = None) -> dict:
    """Bombas de las líneas de líquido: id, línea, caudal, altura, diámetro, velocidad, potencia y costo del costeo."""
    out = dict(filas=[], total_kw=0.0, energia_mwh=None, horas=None, avisos=[])
    av = _aviso_vacio(pl)
    if av:
        out["avisos"].append(av); return out
    try:
        red = HID.red_hidraulica(pl)
    except Exception as e:
        out["avisos"].append(f"No se pudo calcular la red hidráulica: {e}"); return out
    out["avisos"] += list(red["avisos"])
    costos_por_id = {f["equipo"]: f for f in _por_clave(filas_costeo or [], "bomba_centrifuga")}
    vistas = set()
    for i, ln in enumerate(red["lineas"], 1):
        if ln["bomba_diagrama"] is not None:
            pid = ln["bomba_diagrama"]; en_diagrama = True
            if pid in vistas:
                continue
        elif ln["potencia_kW"] > 0:
            pid = f"P-{100 + i}"; en_diagrama = False
        else:
            continue
        vistas.add(pid)
        P = _num(pl.equipos[pid].resultado.detalle.get("W_kW")) if en_diagrama and pl.equipos[pid].resultado else None
        P = P if P else float(ln["potencia_kW"])
        out["filas"].append(dict(id=pid, linea=str(ln["linea"]), origen=ln["origen"], destino=ln["destino"], Q_m3h=float(ln["Q_m3h"]),
                                 H_m=float(ln["H_m"]), D_mm=float(ln["D_mm"]), v=float(ln["v"]), potencia_kW=float(P), en_diagrama=en_diagrama,
                                 **_costo(costos_por_id.get(pid))))
    out["total_kw"] = float(sum(f["potencia_kW"] for f in out["filas"]))
    out["horas"] = red.get("horas")
    out["energia_mwh"] = out["total_kw"] * red["horas"] / 1000.0 if red.get("horas") else None
    if not out["filas"]:
        out["avisos"].append("La planta no mueve líquidos por cañería: no hay bombas que dimensionar (los sólidos van en transportadores).")
    return out


# ---------------------------------------------------------------- válvulas
def valvulas(pl, filas_costeo: list[dict] | None = None, n_bombas: int | None = None) -> dict:
    """Válvulas de control de los lazos (Cv) y cantidad de válvulas de bloqueo y retención de las bombas."""
    out = dict(control=[], n_bloqueo=0, n_retencion=0, avisos=[])
    av = _aviso_vacio(pl)
    if av:
        out["avisos"].append(av); return out
    for f in _por_clave(filas_costeo or [], "valvula_control"):
        out["control"].append(dict(id=f["equipo"], nombre=f["nombre"], Cv=_num(f["tamano"]), nota=f.get("nota", ""), **_costo(f)))
    nb = int(n_bombas if n_bombas is not None else len(bombas(pl)["filas"]))
    out["n_bloqueo"] = int(round(nb * SUPUESTOS["bloqueo_por_bomba"].valor)); out["n_retencion"] = nb
    if not out["control"]:
        out["avisos"].append("La planta no tiene lazos de control con válvula como elemento final (se agregan en Lazos de control).")   # PAT 142
    return out


# ---------------------------------------------------------------- cañerías
def canerias(pl, longitudes: dict | None = None, filas_costeo: list[dict] | None = None) -> dict:
    """Cañerías por línea (diámetro nominal y largo del layout o Supuesto) y por diámetro nominal con su costo del costeo."""
    out = dict(lineas=[], por_dn=[], total_m=0.0, avisos=[])
    av = _aviso_vacio(pl)
    if av:
        out["avisos"].append(av); return out
    try:
        lineas = HID.red_hidraulica(pl)["lineas"]
    except Exception as e:
        out["avisos"].append(f"No se pudo calcular la red hidráulica: {e}"); return out
    longitudes = longitudes or {}
    for ln in lineas:
        L = longitudes.get(str(ln["linea"]), longitudes.get(ln["linea"]))
        dn = CO.diametro_nominal(ln["D_mm"])
        out["lineas"].append(dict(linea=str(ln["linea"]), origen=ln["origen"], destino=ln["destino"], D_mm=float(ln["D_mm"]), DN=dn,
                                  pulgadas=CO.pulgadas(dn), largo_m=float(L) if L is not None else HID.L_LINEA,
                                  fuente_largo="Layout" if L is not None else f"Supuesto: sin layout, {HID.L_LINEA:g} m por línea (motor/hidraulica.py)"))
    for f in _por_clave(filas_costeo or [], "caneria"):
        out["por_dn"].append(dict(DN=int(f["tamano"]), pulgadas=CO.pulgadas(int(f["tamano"])), largo_m=float(f["cantidad"]), nota=f.get("nota", ""),
                                  **_costo(f)))
    out["total_m"] = float(sum(x["largo_m"] for x in out["lineas"]))
    if not out["lineas"]:
        out["avisos"].append("La planta no tiene líneas de líquido: no hay cañerías que dimensionar.")
    return out


# ---------------------------------------------------------------- estanques pulmón
def precio_estanque(volumen_m3: float, cepci_hoy: float = CO.CEPCI_HOY) -> dict:
    """Costo de un estanque (Supuesto): precio de referencia a 10 m³ escalado con Williams y actualizado con el CEPCI de 2023."""
    S0 = SUPUESTOS["volumen_ref"].valor; C0 = SUPUESTOS["precio_estanque"].valor
    n, fn, cn = CO.exponente("estanque_pulmon")
    C = CO.williams(C0, S0, max(volumen_m3, 1e-6), n)
    C_hoy, fc = CO.actualizar(C, CO.cepci_de(ANIO_REF_ESTANQUE), cepci_hoy)
    fuente = (f"Supuesto: US$ {C0:,.0f} a {S0:g} m³ de {ANIO_REF_ESTANQUE}, escalado con Williams (n = {n:g}) y el CEPCI de costeo.py"
              .replace(",", "."))
    return dict(costo_usd=float(C_hoy), n=n, factor_cepci=float(fc), categoria="Supuesto", fuente=fuente)


def dimensionar_estanque(masa_t: float, rho_kg_m3: float, llenado: float | None = None, relacion_hd: float | None = None) -> dict:
    """Volumen útil y geométrico, diámetro, altura y huella de un estanque cilíndrico vertical que guarda masa_t toneladas."""
    llenado = SUPUESTOS["llenado"].valor if llenado is None else llenado
    hd = SUPUESTOS["relacion_hd"].valor if relacion_hd is None else relacion_hd
    if rho_kg_m3 <= 0 or llenado <= 0 or hd <= 0:
        raise ValueError("Densidad, llenado y relación altura/diámetro deben ser positivos.")
    v_util = max(masa_t, 0.0) * 1000.0 / rho_kg_m3
    v_geo = v_util / llenado
    D = (4.0 * v_geo / (math.pi * hd)) ** (1.0 / 3.0) if v_geo > 0 else 0.0
    return dict(v_util_m3=v_util, v_geo_m3=v_geo, D_m=D, H_m=hd * D, huella_m2=math.pi * D * D / 4.0)


def _mttr_h(eq) -> tuple[float, str]:
    eqv = SEL.fallas_equivalentes(eq)
    if eqv is not None:
        return float(eqv[1]), "Selección de equipos aplicada"
    cat = LF.categoria(eq.tipo)
    return float(LF.FALLAS_TIPO[cat][1]), f"Supuesto PAT 134 de motor/linea_fluida.py ({cat})"


def _densidad(pl, a: str, b: str) -> tuple[float, str]:
    for c in pl.conexiones:
        if c.origen == a and c.destino == b and not pl.es_servicio(c):
            cor = pl.salidas.get((c.origen, c.puerto_origen))
            props = HID.propiedades_corriente(cor) if cor is not None else None
            if props:
                return float(props["rho"]), "Corriente líquida de la línea (motor/propiedades.py)"
            break
    return SUPUESTOS["densidad_solido"].valor, "Supuesto: " + SUPUESTOS["densidad_solido"].justificacion


def estanques(pl, metodo: str = "residencia", minutos: float | None = None, cobertura: float | None = None,
              cepci_hoy: float = CO.CEPCI_HOY) -> dict:
    """Estanques pulmón entre equipos consecutivos de la línea principal. metodo: «residencia» (minutos de la carga del equipo de
    aguas abajo), «falla» (cobertura × MTTR del de aguas arriba, por la carga de aguas abajo) o «mayor». Cada fila trae la masa que
    guarda (t, comparable con la capacidad de la pestaña Línea), el volumen, las dimensiones y el costo Supuesto."""
    if metodo not in METODOS_PULMON:
        raise ValueError(f"Método desconocido: {metodo}. Use {', '.join(METODOS_PULMON)}")
    out = dict(filas=[], metodo=metodo, avisos=[], total_usd=0.0, total_clp=0.0)
    av = _aviso_vacio(pl)
    if av:
        out["avisos"].append(av); return out
    minutos = SUPUESTOS["residencia_min"].valor if minutos is None else float(minutos)
    cobertura = SUPUESTOS["cobertura_falla"].valor if cobertura is None else float(cobertura)
    try:
        ids, avisos = LF.linea_principal(pl)
    except Exception as e:
        out["avisos"].append(f"No hay línea principal de proceso: {e}"); return out
    out["avisos"] += list(avisos)
    if len(ids) < 2:
        out["avisos"].append("La línea principal tiene un solo equipo: no hay pulmones entre equipos.")
        return out
    for a, b in zip(ids[:-1], ids[1:]):
        ea, eb = pl.equipos[a], pl.equipos[b]
        carga_b = _num(eb.resultado.detalle.get("carga_t_h")) if eb.resultado else None
        if not carga_b or carga_b <= 0:
            continue
        mttr, f_mttr = _mttr_h(ea)
        t_res = carga_b * minutos / 60.0
        t_falla = carga_b * mttr * cobertura
        masa = {"residencia": t_res, "falla": t_falla, "mayor": max(t_res, t_falla)}[metodo]
        rho, f_rho = _densidad(pl, a, b)
        d = dimensionar_estanque(masa, rho)
        pr = precio_estanque(d["v_geo_m3"], cepci_hoy)
        out["filas"].append(dict(id=f"{a}-{b}", antes=a, despues=b, nombre_antes=ea.nombre, nombre_despues=eb.nombre, carga_t_h=float(carga_b),
                                 masa_residencia_t=float(t_res), mttr_h=mttr, masa_falla_t=float(t_falla), masa_t=float(masa), rho=rho,
                                 fuente_rho=f_rho, fuente_mttr=f_mttr, costo_usd=pr["costo_usd"], costo_clp=pr["costo_usd"] * costos.DOLAR,
                                 fuente_costo=pr["fuente"], origen_costo="Supuesto", **d))
    out["total_usd"] = float(sum(f["costo_usd"] for f in out["filas"]))
    out["total_clp"] = out["total_usd"] * costos.DOLAR
    return out


# ---------------------------------------------------------------- servicios
def servicios(pl, filas_costeo: list[dict] | None = None, precio_kwh: float = SEL.PRECIO_KWH, horas: float | None = None,
              bombas_kw: float = 0.0) -> dict:
    """Vapor, calor, agua, aire y electricidad: demanda total, unidad, equipo que lo genera y costo (inversión del costeo y, en
    electricidad, energía anual a precio_kwh). bombas_kw: potencia de las bombas de línea, que no figura en los equipos."""
    out = dict(filas=[], avisos=[], total_usd=0.0)
    av = _aviso_vacio(pl)
    if av:
        out["avisos"].append(av); return out
    filas_costeo = filas_costeo or []
    h = horas or HID._horas(pl) or SEL.SUPUESTOS["horas"].valor
    gen = _por_clave(filas_costeo, "caldera_gas", "generador_biomasa")
    usd_gen = sum(f["costo_usd"] for f in gen)
    vapor_kW = pl.servicio_total("vapor_kW")
    calor_kW, aire_kgh, elec_kW = pl.servicio_total("calor_kW"), pl.servicio_total("aire_kgh"), pl.servicio_total("electricidad_kW")
    vapor_kgh = vapor_kW * 3600.0 / CO.DH_VAPOR        # toda la demanda de vapor con el mismo calor de costeo.py (Supuesto)
    gen_txt = ", ".join(f"{f['equipo']} ({f['nombre']})" for f in gen) or "sin caldera ni generador en la planta"
    fuente_gen = (gen[0].get("fuente", "") + f" ({gen[0].get('categoria', '')})") if gen else ""

    def fila(servicio, demanda, unidad, genera, usd, fuente, nota=""):
        out["filas"].append(dict(servicio=servicio, demanda=float(demanda), unidad=unidad, genera=genera, costo_usd=usd,
                                 costo_clp=None if usd is None else usd * costos.DOLAR, fuente=fuente, nota=nota))
    fila("Vapor", vapor_kW, "kW", gen_txt, usd_gen if vapor_kW else None, fuente_gen if vapor_kW else "Sin demanda de vapor",
         f"{vapor_kgh:,.0f} kg/h con {CO.DH_VAPOR:g} kJ/kg (Supuesto de costeo.py)".replace(",", ".") if vapor_kW else "")
    fila("Calor (aire caliente)", calor_kW, "kW", gen_txt, usd_gen if (calor_kW and not vapor_kW) else (0.0 if calor_kW else None),
         fuente_gen if calor_kW else "Sin demanda de calor", "Generador a biomasa de la planta" if calor_kW else "")
    # agua: la que se evapora en la caldera (un kg de agua por kg de vapor) y el condensado que la planta puede recuperar
    rec_kgh = 0.0; nota_agua = ""
    try:
        from . import agua as AG
        rec_kgh = float(AG.agua_recuperada(pl)["total_kgh"])
    except Exception:
        nota_agua = "No se pudo estimar el agua recuperable. "
    cubre = (min(rec_kgh / vapor_kgh, 1.0) * 100.0) if vapor_kgh > 0 else 0.0
    fila("Agua de caldera", vapor_kgh / AG_RHO, "m³/h", "Captación y tratamiento (sin referencia de costo en costeo.py)", None,
         "Sin referencia en costeo.py: sus bombas y cañerías están en esas listas",
         (nota_agua + f"Un kg de agua por kg de vapor ({vapor_kgh:,.0f} kg/h); el condensado recuperable es {rec_kgh:,.0f} kg/h "
          f"(motor/agua.py), que cubre {cubre:,.0f} % de la demanda").replace(",", "X").replace(".", ",").replace("X", ".") if vapor_kgh > 0
         else "La planta no genera vapor")
    fila("Aire", aire_kgh, "kg/h", "Ventiladores del equipo que lo pide", None,
         "Incluido en el costo del equipo (costeo.py no trae ventilador aparte)", "Aire de secado u otro flujo de aire de los equipos")
    # PAT 143 b: agua de proceso y reactivos de los equipos que los piden como servicio (agar: lavados, baño alcalino y extracción)
    agua_kgh, reac_kgh = pl.servicio_total("agua_kgh"), pl.servicio_total("reactivo_kgh")
    if agua_kgh > 0:
        fila("Agua de proceso", agua_kgh / AG_RHO, "m³/h", "Captación y tratamiento (sin referencia de costo en costeo.py)", None,
             "Sin referencia en costeo.py: sus bombas y cañerías están en esas listas",
             f"{agua_kgh:,.0f} kg/h para lavados, soluciones y extracción".replace(",", "."))
    if reac_kgh > 0:
        fila("Reactivos (NaOH)", reac_kgh, "kg/h", "Bodega y preparación de soluciones", None,
             "Insumo de operación: su precio no está en costeo.py", "Soda cáustica disuelta en el baño alcalino")
    P_total = elec_kW + bombas_kw
    cable = _por_clave(filas_costeo, "cable_electrico")
    usd_cable = sum(f["costo_usd"] for f in cable)
    kwh = P_total * h
    fila("Electricidad", P_total, "kW", "Red de baja tensión y CCM del layout", usd_cable if cable else None,
         (cable[0].get("fuente", "") + f" ({cable[0].get('categoria', '')})") if cable else "Sin cables del layout: calcule la red eléctrica en Layout",
         f"{kwh / 1000:,.0f} MWh/año con {h:,.0f} h; energía ${kwh * precio_kwh / 1e6:,.1f} M/año a ${precio_kwh:,.1f}/kWh "
         f"(equipos {elec_kW:,.1f} kW y bombas {bombas_kw:,.1f} kW)".replace(",", "X").replace(".", ",").replace("X", "."))
    out["energia_kwh"] = float(kwh); out["energia_clp"] = float(kwh * precio_kwh); out["horas"] = float(h)
    out["total_usd"] = float(sum(f["costo_usd"] or 0.0 for f in out["filas"]))
    if not (vapor_kW or calor_kW or aire_kgh or P_total):
        out["avisos"].append("Ningún equipo de la planta pide servicios.")
    return out


# ---------------------------------------------------------------- todo junto
def auxiliares(pl, longitudes: dict | None = None, cables_m: dict | None = None, metodo: str = "residencia", minutos: float | None = None,
               cobertura: float | None = None, precio_kwh: float = SEL.PRECIO_KWH, costeo_res: dict | None = None,
               f_inst: float = costos.F_INSTALACION, **kw_costeo) -> dict:
    """Bombas, válvulas, estanques pulmón, cañerías y servicios de la planta, con la inversión de cada rubro (comprada y con el
    factor de instalación f_inst). kw_costeo pasa a costeo.costear (cepci_hoy, dolar, euro, ...). Con la planta vacía o sin
    resolver, todo viene vacío con un aviso."""
    av = _aviso_vacio(pl)
    vacio = dict(bombas=dict(filas=[], total_kw=0.0, energia_mwh=None, horas=None, avisos=[]), valvulas=dict(control=[], n_bloqueo=0, n_retencion=0, avisos=[]),
                 estanques=dict(filas=[], metodo=metodo, avisos=[], total_usd=0.0, total_clp=0.0), canerias=dict(lineas=[], por_dn=[], total_m=0.0, avisos=[]),
                 servicios=dict(filas=[], avisos=[], total_usd=0.0), resumen=[], total_usd=0.0, total_instalado_usd=0.0,
                 total_clp=0.0, total_instalado_clp=0.0, f_inst=f_inst, avisos=[av] if av else [])
    if av:
        return vacio
    filas = _filas_costeo(pl, longitudes, cables_m, costeo_res, kw_costeo)
    b = bombas(pl, filas)
    v = valvulas(pl, filas, len(b["filas"]))
    c = canerias(pl, longitudes, filas)
    e = estanques(pl, metodo, minutos, cobertura, kw_costeo.get("cepci_hoy", CO.CEPCI_HOY))
    s = servicios(pl, filas, precio_kwh, b.get("horas"), b["total_kw"])
    suma = lambda xs: float(sum(x["costo_usd"] or 0.0 for x in xs))
    cable_usd = suma(_por_clave(filas, "cable_electrico")); gen_usd = suma(_por_clave(filas, "caldera_gas", "generador_biomasa"))
    resumen = [dict(rubro="Bombas", cantidad=len(b["filas"]), costo_usd=suma(b["filas"])),
               dict(rubro="Válvulas de control", cantidad=len(v["control"]), costo_usd=suma(v["control"])),
               dict(rubro="Cañerías", cantidad=len(c["por_dn"]), costo_usd=suma(c["por_dn"])),
               dict(rubro="Estanques pulmón", cantidad=len(e["filas"]), costo_usd=e["total_usd"]),
               dict(rubro="Cable eléctrico", cantidad=1 if cable_usd else 0, costo_usd=cable_usd),
               dict(rubro="Generación de vapor o calor", cantidad=len(_por_clave(filas, "caldera_gas", "generador_biomasa")), costo_usd=gen_usd)]
    for r in resumen:
        r["costo_clp"] = r["costo_usd"] * kw_costeo.get("dolar", costos.DOLAR)
        r["instalado_usd"] = r["costo_usd"] * f_inst
    total = float(sum(r["costo_usd"] for r in resumen))
    avisos = list(dict.fromkeys(b["avisos"] + v["avisos"] + c["avisos"] + e["avisos"] + s["avisos"]))
    dolar = kw_costeo.get("dolar", costos.DOLAR)
    return dict(bombas=b, valvulas=v, estanques=e, canerias=c, servicios=s, resumen=resumen, total_usd=total, total_instalado_usd=total * f_inst,
                total_clp=total * dolar, total_instalado_clp=total * f_inst * dolar, f_inst=f_inst, avisos=avisos)
