"""Capacidad nominal de partida de cada equipo de los escenarios base (PAT 132).

Como en el simulador del profesor, cada equipo trae una capacidad nominal (t/h de carga) para que la vista de teoría de
restricciones muestre desde el inicio la utilización de cada máquina con su semáforo. No hubo visita a la planta ni hay
placas de los equipos: la capacidad es la carga de diseño del escenario por (1 + holgura), y la holgura es un supuesto del
simulador. Criterio: el equipo más caro de cada línea (el evaporador de pasta o el secador de biomasa) se dimensiona más
ajustado y queda como recurso crítico; recepción, lavado, acopio y despacho se sobredimensionan para absorber los peaks de
llegada y de despacho. El usuario puede cambiar cada capacidad en Propiedades o reasignarlas con «Asignar capacidades»."""
from __future__ import annotations
import math

HOLGURAS = {
    "tomate": {"F1": 1.10, "Z1": 0.60, "W1": 0.30, "F2": 0.40, "W2": 0.15, "W3": 0.15, "W4": 0.08, "W5": 0.40, "B2": 0.60, "A1": 0.30},
    "pellet": {"T1": 0.10, "Z1": 0.30, "A1": 0.15, "T2": 0.40, "F1": 0.50, "A2": 1.00},
    "chip": {"Z1": 0.40, "F1": 0.60, "T1": 0.10, "A1": 1.00},
    "lena": {"A1": 0.20, "T1": 0.10, "A2": 1.00},
}
JUSTIFICACION = ("Holgura de diseño supuesta por el simulador, no es dato de la planta: el equipo más caro de la línea se dimensiona "
                 "más ajustado (recurso crítico) y la recepción, el acopio y el despacho se sobredimensionan para los peaks")


def aplicar(pl, holguras: dict | None = None) -> int:
    """Fija capacidad = carga resuelta × (1 + holgura), redondeada hacia arriba a 0,1 t/h. Devuelve cuántos equipos cambió."""
    holguras = HOLGURAS.get(pl.rubro, {}) if holguras is None else holguras
    n = 0
    for k, h in holguras.items():
        eq = pl.equipos.get(k)
        if eq is None or "capacidad" not in eq.params or eq.resultado is None:
            continue
        carga = eq.resultado.detalle.get("carga_t_h")
        if not carga:
            continue
        eq.set("capacidad", math.ceil(float(carga) * (1 + h) * 10) / 10, categoria="Supuesto",
               fuente=f"Supuesto del simulador (PAT 132, 02-11-2026): carga de diseño × {1 + h:.2f}".replace(".", ","),
               justificacion=JUSTIFICACION)
        n += 1
    return n
