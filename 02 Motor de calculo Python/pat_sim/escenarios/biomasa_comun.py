"""Piezas comunes de los escenarios de biomasa: crear la planta desde un diccionario de parámetros y la especificación de producción."""
from __future__ import annotations
from ..motor.planta import Planta, EspecDiseno


def nueva_planta(nombre: str, rubro: str, p: dict) -> Planta:
    pl = Planta(nombre, rubro)
    pl.globales.update(T_final_residual=p["Tfin"], dT_min=p["dT"])
    return pl


def fijar_produccion(pl: Planta, alimentacion: str, despacho: str, t_h: float, descripcion: str):
    """Ajusta la biomasa verde que entra para que el despacho reciba t_h de producto (como el °Brix de la pasta en Agrozzi)."""
    pl.especs.append(EspecDiseno(alimentacion, "carga_t_h", despacho, "m", t_h * 1000, descripcion))


def resumen_corto(pl: Planta) -> dict:
    """Cifras de control de un escenario de biomasa (para las pruebas y la pestaña Escenario)."""
    from ..motor.resumen import resumen_planta
    r = resumen_planta(pl)
    seca = [e for e in pl.equipos.values() if e.tipo.startswith("secador")]
    desp = [e for e in pl.equipos.values() if e.tipo == "despacho_biomasa"]
    d = seca[0].resultado.detalle if seca else {}
    q = desp[0].resultado.detalle if desp else {}
    return dict(producto_t_h=q.get("producto_t_h"), humedad_producto=q.get("humedad_bh"), PCI_producto=q.get("PCI_MJ_kg"),
                carga_t_h=pl.equipos[next(iter(pl.equipos))].resultado.detalle.get("carga_t_h"),
                agua_evaporada_kgh=d.get("agua_evaporada_kgh"), consumo_MJ_kg_agua=d.get("consumo_MJ_kg_agua"),
                calor_secado_kW=r["servicios"]["calor_kW"], electricidad_kW=r["servicios"]["electricidad_kW"],
                sumidero=r.get("Qsumidero"), cascada=r.get("cascada"), cobertura_cascada=r.get("cobertura_cascada"),
                pinch=r.get("pinch"), combustible_kgh=r.get("combustible_kgh"), horas=r.get("horas"),
                biomasa_desplazada_t=(r.get("biomasa_cascada") or {}).get("t"))
