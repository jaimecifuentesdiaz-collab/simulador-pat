"""Escenario: planta de agar agar en polvo a partir de alga roja Gracilaria seca (rubro agar).

Línea (McHugh, 2003; Armisen y Galatas, 1987): recepción del alga seca, lavado e hidratación, tratamiento alcalino con NaOH a 85 °C,
lavado y neutralización, extracción con agua a 95 °C, filtro prensa en caliente, enfriamiento y gelificación del extracto, prensa
del gel (sinéresis hasta 20 % de agar), secador de banda con aire calentado con vapor, molino y envasado. Una caldera a gas entrega
el vapor del baño alcalino, del extractor y de la batería del aire de secado.
Los valores por defecto y sus fuentes están en catalogos/agar.py; aquí van solo los que cambian con el escenario.
Tamaño: 602 t de agar en polvo al año, la producción de referencia del tipo de planta agar de catalogos/plantas_genericas.py
(Supuesto ilustrativo del desafío de ejemplo de datos/mantenedor.py), en 330 días de 24 h (Supuesto)."""
from __future__ import annotations
from ..motor.planta import Instrumento
from ..catalogos import agar as A
from ..catalogos.servicios import CalderaGas
from .biomasa_comun import nueva_planta, fijar_produccion
from . import capacidades as _cap

NOMBRE = "Planta de agar agar (escenario base)"
AGAR_T_ANO = 602.0      # t de agar en polvo al año (catalogos/plantas_genericas.py, tipo de planta agar)
BASE = dict(produccion=AGAR_T_ANO / (330 * 24), M0=0.20, naoh=0.035, Tbano=85.0, Text=95.0, rend=0.2326, cext=0.01, xgel=0.20,
            Mseco=0.15, Tae=75.0, Tas=45.0, dias=330, hpd=24, Tfin=30.0, dT=5.0)
PARAMS = [  # (clave, etiqueta, mínimo, máximo, paso, formato) para la pantalla Escenario
    ("produccion", "Agar en polvo producido (t/h)", 0.005, 2.0, 0.001, "%.5f"),
    ("M0", "Humedad del alga recibida (base húmeda)", 0.05, 0.40, 0.01, "%.2f"),
    ("naoh", "Concentración de NaOH del baño (fracción)", 0.01, 0.08, 0.005, "%.3f"),
    ("Tbano", "Temperatura del baño alcalino (°C)", 70.0, 95.0, 1.0, "%.0f"),
    ("Text", "Temperatura de extracción (°C)", 85.0, 100.0, 1.0, "%.0f"),
    ("rend", "Agar extraído por kg de materia seca del alga", 0.10, 0.35, 0.005, "%.3f"),
    ("cext", "Agar en la fase líquida del extracto (fracción)", 0.005, 0.02, 0.001, "%.3f"),
    ("xgel", "Agar en el gel prensado (fracción)", 0.08, 0.25, 0.01, "%.2f"),
    ("Mseco", "Humedad del agar seco (base húmeda)", 0.05, 0.18, 0.01, "%.2f"),
    ("Tae", "Temperatura del aire de secado (°C)", 50.0, 85.0, 1.0, "%.0f"),
    ("Tas", "Temperatura del escape del secador (°C)", 30.0, 70.0, 1.0, "%.0f"),
    ("dias", "Días de operación al año", 100, 366, 1, "%d"),
    ("dT", "Aproximación mínima de temperatura (°C)", 2.0, 15.0, 0.5, "%.1f"),
    ("Tfin", "Temperatura final de los residuales (°C)", 20.0, 40.0, 1.0, "%.1f"),
]


def crear(capacidades=True, **kw):
    p = dict(BASE); p.update(kw)
    pl = nueva_planta(NOMBRE, "agar", p); E = pl.agregar
    E(A.RecepcionAlga("B1", "Recepción del alga seca", 40, 120, humedad=p["M0"], dias=p["dias"], horas_dia=p["hpd"]))
    E(A.LavadoAlga("R1", "Lavado e hidratación", 200, 120))
    E(A.TratamientoAlcalino("C1", "Tratamiento alcalino", 360, 120, conc_naoh=p["naoh"], T_bano=p["Tbano"]))
    E(A.LavadoNeutralizacion("R2", "Lavado y neutralización", 520, 120))
    E(A.ExtractorAgar("W1", "Extractor de agar", 680, 120, rendimiento=p["rend"], conc_extracto=p["cext"], T_extraccion=p["Text"]))
    E(A.FiltroPrensaAgar("F1", "Filtro prensa", 840, 120))
    E(A.GelificadorAgar("W2", "Enfriador y gelificación", 1000, 120))
    E(A.PrensaGel("F2", "Prensa del gel", 1000, 320, solidos_salida=p["xgel"]))
    E(A.SecadorAgar("T1", "Secador de banda", 840, 320, humedad_salida=p["Mseco"], T_aire_entrada=p["Tae"], T_aire_salida=p["Tas"],
                    T_condensacion=p["Tfin"]))
    E(A.MolinoAgar("Z1", "Molino de agar", 680, 320))
    E(A.EnvasadoAgar("A1", "Envasado del agar en polvo", 520, 320))
    E(CalderaGas("D1", "Caldera a gas natural", 200, 320))
    C = pl.conectar
    C("B1", "producto", "R1", "entrada", nombre="1"); C("R1", "producto", "C1", "entrada", nombre="2")
    C("C1", "producto", "R2", "entrada", nombre="3"); C("R2", "producto", "W1", "entrada", nombre="4")
    C("W1", "producto", "F1", "entrada", nombre="5"); C("F1", "producto", "W2", "entrada", nombre="6")
    C("W2", "producto", "F2", "entrada", nombre="7"); C("F2", "producto", "T1", "entrada", nombre="8")
    C("T1", "producto", "Z1", "entrada", nombre="9"); C("Z1", "producto", "A1", "entrada", nombre="10")
    C("D1", "vapor", "C1", "vapor", nombre="V1"); C("D1", "vapor", "W1", "vapor", nombre="V2"); C("D1", "vapor", "T1", "vapor", nombre="V3")
    fijar_produccion(pl, "B1", "A1", p["produccion"], "Agar en polvo producido")
    # Controladores con alimentación, acción y consigna (ISA-5.4, como los lazos típicos de motor/instrumentacion.py): acción inversa
    # con la válvula de vapor que cierra en falla y con la de agua de enfriamiento que abre en falla (Supuesto de diseño)
    ctl = lambda letras, num, eq, desc, par, fin, consigna: Instrumento(letras, num, eq, "plc", desc, par, fin, alimentacion="L1, L2, G",
                                                                         accion="inversa", consigna=consigna)
    pl.instrumentos += [
        ctl("TIC", "101", "C1", "Control de temperatura del baño alcalino", "T_bano", "TV-101", f"{A._f(p['Tbano'], 0)} °C"),
        ctl("TIC", "201", "W1", "Control de temperatura de extracción", "T_extraccion", "TV-201", f"{A._f(p['Text'], 0)} °C"),
        ctl("TIC", "301", "W2", "Control de temperatura del gel a la salida del enfriador", "T_gel", "TV-301",
            f"{A._f(pl.equipos['W2'].v('T_gel'), 0)} °C"),
        ctl("TIC", "401", "T1", "Control de temperatura del aire de secado a la entrada", "T_aire_entrada", "TV-401", f"{A._f(p['Tae'], 0)} °C"),
        ctl("MIC", "402", "T1", "Control de humedad del agar a la salida del secador", "humedad_salida", "Velocidad de la banda",
            f"{A._f(100 * p['Mseco'], 0)} %"),
    ]
    pl._p = p
    pl.resolver()
    if capacidades:                       # capacidad nominal de partida (PAT 132), como en los demás escenarios
        _cap.aplicar(pl)
    return pl


# ----------------------------------------------------------------------------------------------- recuperación con todas las corrientes
def objetivo_pinch_multiple(pl, dT: float | None = None, T_final: float | None = None) -> dict:
    """Tabla del problema (Linnhoff y Flower, 1978, en Klemeš et al., 2018) con todas las corrientes calientes del mapa y todos los
    sumideros de la planta a la vez. Complementa motor/resumen.resumen_planta, que cruza las calientes con un solo sumidero (el
    mayor). Devuelve calor de proceso de las frías, calor externo mínimo, enfriamiento mínimo, calor recuperable y pinch."""
    g = pl.globales
    dT = float(g.get("dT_min", 5.0)) if dT is None else float(dT)
    Tf = float(g.get("T_final_residual", 30.0)) if T_final is None else float(T_final)
    calientes, frias = [], []
    for r in pl.residuales():
        if r.CP is None:                   # latente a T_in: se reparte en 1 K para la tabla (no hay en el agar)
            calientes.append((r.nombre, r.T_in, r.T_in - 1.0, r.Q))
            continue
        To = r.T_out if r.T_out is not None else Tf
        if r.T_in > To:
            calientes.append((r.nombre, r.T_in, To, r.CP))
    for s in pl.sumideros():
        if s.T_out > s.T_in:
            frias.append((s.nombre + " " + s.equipo, s.T_in, s.T_out, s.CP))
    Q_frio = sum(c[3] * (c[2] - c[1]) for c in frias)
    Q_cal = sum(h[3] * (h[1] - h[2]) for h in calientes)
    pts = sorted({h[1] - dT / 2 for h in calientes} | {h[2] - dT / 2 for h in calientes}
                 | {c[1] + dT / 2 for c in frias} | {c[2] + dT / 2 for c in frias}, reverse=True)
    cum = 0.0
    flujos = [(pts[0], 0.0)] if pts else []
    for a, b in zip(pts[:-1], pts[1:]):
        cp_h = sum(h[3] for h in calientes if h[1] - dT / 2 >= a - 1e-12 and h[2] - dT / 2 <= b + 1e-12)
        cp_c = sum(c[3] for c in frias if c[2] + dT / 2 >= a - 1e-12 and c[1] + dT / 2 <= b + 1e-12)
        cum += (cp_h - cp_c) * (a - b); flujos.append((b, cum))
    mn = min((f for _, f in flujos), default=0.0)
    Qh = max(0.0, -mn); Qc = Qh + (flujos[-1][1] if flujos else 0.0)
    pin = sorted({round(t, 3) for t, f in flujos if abs(f - mn) < 1e-6}) if Qh > 0 and flujos else []
    Q_frio, Q_cal, Qh, Qc = float(Q_frio), float(Q_cal), float(Qh), float(Qc)
    return dict(dT_min=dT, T_final=Tf, calientes=calientes, frias=frias, Q_frias_kW=Q_frio, Q_calientes_kW=Q_cal,
                Q_externo_min_kW=Qh, Q_enfriamiento_min_kW=Qc, recuperable_kW=Q_frio - Qh,
                cobertura=(Q_frio - Qh) / Q_frio if Q_frio else 0.0, T_pinch_desplazada=pin)


def resumen_corto(pl) -> dict:
    """Cifras de control del escenario de agar (para las pruebas y la pantalla Escenario)."""
    from ..motor.resumen import resumen_planta
    r = resumen_planta(pl)
    eq = {e.tipo: e for e in pl.equipos.values()}
    det = lambda t, k: (eq[t].resultado.detalle.get(k) if t in eq and eq[t].resultado is not None else None)
    srv = lambda t, k: (eq[t].resultado.servicios.get(k, 0.0) if t in eq and eq[t].resultado is not None else 0.0)
    alga = det("alimentacion_alga", "carga_t_h"); prod = det("envasado_agar", "producto_t_h"); seco = det("envasado_agar", "agar_seco_t_h")
    m = objetivo_pinch_multiple(pl)
    return dict(producto_t_h=prod, humedad_producto=det("envasado_agar", "humedad_bh"), alga_t_h=alga,
                rendimiento_global=(seco / alga) if alga and seco is not None else None,
                agua_proceso_kgh=pl.servicio_total("agua_kgh"), naoh_kgh=pl.servicio_total("reactivo_kgh"),
                calor_proceso_kW=r["servicios"]["vapor_kW"], calor_bano_kW=srv("tratamiento_alcalino_agar", "vapor_kW"),
                calor_extraccion_kW=srv("extractor_agar", "vapor_kW"), calor_secado_kW=srv("secador_agar", "vapor_kW"),
                electricidad_kW=r["servicios"]["electricidad_kW"], agua_evaporada_kgh=det("secador_agar", "agua_evaporada_kgh"),
                consumo_MJ_kg_agua=det("secador_agar", "consumo_MJ_kg_agua"),
                sumidero=r.get("sumidero"), Qsumidero=r.get("Qsumidero"), cascada=r.get("cascada"), cobertura_cascada=r.get("cobertura_cascada"),
                pinch=r.get("pinch"), gas_kgh=r.get("gas_caldera_kgh"), horas=r.get("horas"),
                recuperable_todas_kW=m["recuperable_kW"], Q_externo_min_kW=m["Q_externo_min_kW"], cobertura_todas=m["cobertura"],
                Q_residual_kW=m["Q_calientes_kW"])

