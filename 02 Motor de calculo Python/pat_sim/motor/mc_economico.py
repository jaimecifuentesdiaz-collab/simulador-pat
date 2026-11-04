"""Montecarlo económico con confiabilidad de los equipos y fluctuación de la demanda (PAT 135, tarea T7.2, 05-11-2026).

Indicación 2 del profesor Torres (reunión del 04-11-2026): la planta se diseña para acomodarse a una demanda con una
estrategia de capacidad (seguimiento, un nivel o dos niveles); habrá períodos con exceso y con déficit de capacidad, y eso,
junto con las paradas por fallas de los equipos, entra en la evaluación económica.

Cómo se calcula (PAT 135):
- Demanda por período (semanas o meses de la temporada): la curva de llegada de Temporada (temporada.curva_llegada) sumada
  por período, o la lista de st.session_state["desafio"]["demanda"] (t de producto por período) si existe. En cada réplica y
  cada año la demanda de cada período se multiplica por un factor gamma de media 1 y coeficiente de variación editable
  (Supuesto: la gamma es positiva y con un solo parámetro fija la dispersión).
- Estrategias de capacidad (planeación agregada; Heizer, Render y Munson, 2017, cap. 13): seguimiento, la tasa de cada período
  sigue a su demanda esperada; un nivel, una sola tasa igual a la demanda media de la temporada; dos niveles, una tasa para los
  períodos de temporada alta (demanda esperada sobre la media) y otra para los de temporada baja, cada una igual a la demanda
  media de su grupo. A las tres se les suma la holgura editable y se limitan a la capacidad de la línea
  (temporada.capacidad_linea). En pellet, chip y leña la llegada de Temporada es pareja: se le puede dar una estacionalidad
  (coseno con peak a mitad de la temporada que conserva el total, Supuesto: el pellet y la leña son combustible de calefacción
  de invierno; el chip abastece calderas industriales y es menos estacional). Sin inventario entre períodos (Supuesto: el tomate es perecible; en la biomasa es conservador).
- Confiabilidad: cada equipo de la línea principal (linea_fluida.linea_principal) con su MTBF y MTTR (linea_fluida.fallas_defecto
  o los de la pestaña Línea). Disponibilidad A = MTBF/(MTBF + MTTR). En cada período de h horas el número de fallas es Poisson
  con media h·A/MTBF (el reloj de falla corre solo mientras el equipo opera, como la base «operando» de la Línea) y cada
  reparación es exponencial de media MTTR, de modo que el tiempo caído es una gamma (Erlang) de forma igual al número de
  fallas y escala MTTR (Law, 2015, cap. 6 y 14). Así el tiempo caído medio es h·(1 − A). La capacidad disponible del período es
  la del cuello de botella disponible: mín(capacidad planificada, mín por equipo de tasa × (h − tiempo caído)).
  Supuesto: los tanques pulmón y la holgura permiten recuperar una parada dentro del período; las paradas de equipos distintos
  no se suman (cota optimista frente a la línea en serie sin pulmones).
- Mantenimiento preventivo: reduce la tasa de falla en la fracción elegida (MTBF / (1 − reducción)) con un costo anual
  proporcional (Supuesto).
- En cada período: producción = mín(demanda, capacidad disponible); déficit = demanda − producción (venta perdida, se valora
  con el margen de contribución) y exceso = capacidad disponible − producción (capacidad ociosa, se valora con una fracción del
  margen como costo fijo sin uso). Cambiar de tasa entre períodos cuesta una fracción del margen por tonelada de capacidad
  cambiada. El ahorro de energía del recuperador (riesgo.ahorro_anual) es proporcional a la producción real frente a la de
  diseño.
- Dos alcances del flujo de cada año (corrección del coordinador, PAT 135):
  «recuperador» (por omisión sin costeo): VAN incremental, proyecto con recuperador menos situación sin recuperador. El margen
  perdido, la capacidad ociosa, el ajuste y el preventivo de la línea ocurren igual con o sin recuperador y se cancelan; la
  confiabilidad y la demanda solo afectan el ahorro de energía, proporcional a la producción real, y las paradas del propio
  recuperador dan ahorro cero mientras está detenido. Flujo = ahorro − costo anual del recuperador; inversión = la de Economía.
  «planta» (por omisión con el costeo): VAN de la planta completa, margen × producción + ahorro − costo anual − preventivo −
  capacidad ociosa − ajuste, con la inversión del costeo; la venta perdida queda implícita en la menor producción.
  En ambos alcances el déficit y el exceso medios se informan como indicadores operacionales.
- Paradas del recuperador: MTBF y MTTR de un equipo térmico (linea_fluida.FALLAS_TIPO["termico"], Supuesto PAT 134) con el
  mismo muestreo Poisson y gamma; mientras está detenido la línea sigue con el combustible (desvío), sin ahorro (Supuesto).
  VAN = −inversión + flujos descontados (la misma economia.van de la pestaña Economía). Cada año de cada réplica se sortea
  por separado. NumPy vectorizado con np.random.default_rng(semilla): la misma semilla repite los resultados y las tres
  estrategias usan los mismos números aleatorios (números aleatorios comunes, Law, 2015, cap. 11), así la comparación es justa.

Referencias: Heizer, J., Render, B. y Munson, C. (2017). Operations management: sustainability and supply chain management
(12.ª ed.). Pearson. Law, A. M. (2015). Simulation modeling and analysis (5.ª ed.). McGraw-Hill Education.
Las cifras sin fuente segura están en SUPUESTOS con su justificación.
"""
from __future__ import annotations
import math
import time
import numpy as np
from . import ajuste as AJ
from . import linea_fluida as LF
from . import operacion as OP
from . import riesgo as R
from . import temporada as TM
from .operacion import Supuesto

ESTRATEGIAS = ("seguimiento", "un_nivel", "dos_niveles")
NOMBRE_ESTRATEGIA = dict(seguimiento="Seguimiento de la demanda", un_nivel="Un nivel", dos_niveles="Dos niveles")
PERIODOS = dict(semana=7, mes=30)
REDUCCION_MAX = 0.9                     # PAT 135: el preventivo no elimina todas las fallas

_SD = "sin dato de la planta ni fuente segura"
_JM = ("Orden de magnitud didáctico del margen de contribución (precio de venta menos costos variables) por tonelada de producto; "
       + _SD + ". Se reemplaza con el precio de venta del desafío o de la empresa")
MARGEN = {"tomate": 200000.0, "pellet": 60000.0, "chip": 6000.0, "lena": 35000.0}     # $/t de producto, Supuesto PAT 135
ESTACIONALIDAD = {"tomate": 0.0, "pellet": 0.35, "chip": 0.15, "lena": 0.35}            # amplitud del coseno, Supuesto PAT 135
ALCANCES = ("recuperador", "planta")
NOMBRE_ALCANCE = dict(recuperador="Recuperador (VAN incremental)", planta="Planta completa con recuperador")
SUPUESTOS = {s.clave: s for s in [
    Supuesto("margen", "Margen de contribución por tonelada de producto", MARGEN["tomate"], "$/t", _JM),
    Supuesto("cv_demanda", "Coeficiente de variación de la demanda de cada período", 0.15, "—",
             "Variación de un período a otro alrededor de la demanda esperada (clima, cosecha, pedidos); " + _SD +
             ". Factor gamma de media 1: siempre positivo"),
    Supuesto("estacionalidad", "Amplitud de la estacionalidad de la demanda de biomasa", ESTACIONALIDAD["pellet"], "fracción de la media",
             "El pellet y la leña se queman sobre todo en la calefacción de invierno, así que su demanda tiene un peak en la mitad de la "
             "temporada (0,35 en pellet y leña, 0,15 en chip, que abastece calderas industriales todo el año); " + _SD + ". En el tomate es 0: "
             "su campana ya viene de Temporada"),
    Supuesto("holgura", "Holgura de capacidad sobre la demanda esperada", 0.10, "fracción",
             "Colchón usual para absorber la variación y las fallas sin agrandar mucho la capacidad ociosa; " + _SD),
    Supuesto("frac_ocioso", "Costo de la capacidad ociosa", 0.25, "fracción del margen por t",
             "Costos fijos de la capacidad sin uso (personal del turno, energía base, depreciación) como una cuarta parte del margen; " + _SD),
    Supuesto("frac_ajuste", "Costo de cambiar la capacidad entre períodos", 0.10, "fracción del margen por t de capacidad cambiada",
             "Contratar, capacitar o despedir turnos y arrancar o detener equipos; " + _SD),
    Supuesto("reduccion_pm", "Reducción de la tasa de falla por mantenimiento preventivo", 0.0, "fracción",
             "Parte en 0: las fallas de la pestaña Línea son las de un mantenimiento correctivo; con más preventivo baja la tasa de falla"),
    Supuesto("costo_pm_equipo", "Costo del preventivo para bajar a la mitad la tasa de falla de un equipo", 3.0, "MM$/año por equipo",
             "Plan de inspección, lubricación y cambio de piezas de un equipo durante la temporada; el costo crece en proporción a la "
             "reducción pedida; " + _SD),
    Supuesto("recuperador", "Fallas del recuperador", LF.FALLAS_TIPO["termico"][0], "h de MTBF",
             "Intercambiadores como equipo térmico de la Línea (MTBF 160 h y MTTR 2 h, Supuesto PAT 134); mientras está detenido la "
             "línea sigue produciendo con el combustible de la caldera o del generador por el desvío y el ahorro es cero"),
    Supuesto("sin_inventario", "Inventario entre períodos", 0.0, "t",
             "La demanda que no se atiende en su período se pierde: el tomate es perecible y en la biomasa el supuesto es conservador"),
    Supuesto("cuello", "Capacidad disponible del período", 0.0, "—",
             "Cuello de botella disponible: los pulmones y la holgura permiten recuperar una parada dentro del período y las paradas de "
             "equipos distintos no se suman (cota optimista frente a una línea en serie sin pulmones)"),
]}
NOMBRES = dict(R.NOMBRES, margen="Margen de contribución", cv_demanda="Variación de la demanda", holgura="Holgura de capacidad",
               estacionalidad="Estacionalidad de la demanda", inversion_planta="Inversión de la planta (costeo)", f_mtbf="MTBF de los equipos (factor)", f_mttr="MTTR de los equipos (factor)", reduccion_pm="Mantenimiento preventivo")


def _num(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def margen_defecto(rubro: str) -> float:
    """Margen de contribución por tonelada de producto del rubro (Supuesto PAT 135); los rubros que no están usan el del pellet."""
    return MARGEN.get(rubro, MARGEN["pellet"])


# ----------------------------------------------------------------------------------------------- confiabilidad
def disponibilidad(mtbf: float, mttr: float) -> float:
    """Disponibilidad A = MTBF/(MTBF + MTTR)."""
    mtbf, mttr = float(mtbf), float(mttr)
    if mtbf <= 0 or mttr < 0:
        raise ValueError("MTBF debe ser positivo y MTTR no negativo.")
    return mtbf / (mtbf + mttr)


def equipos(pl, fallas: dict | None = None) -> tuple[list, list]:
    """Equipos de la línea principal con capacidad y fallas: id, nombre, tasa máxima en t/h de materia prima (capacidad efectiva
    referida a la alimentación, como temporada.capacidad_linea), MTBF, MTTR y disponibilidad. fallas: {id: (mtbf, mttr) o None}
    de la pestaña Línea (None = sin fallas); si falta un equipo se usan las de linea_fluida.fallas_defecto."""
    ids, avisos = LF.linea_principal(pl)
    d = TM.datos_planta(pl); out = []
    for k in ids:
        e = pl.equipos[k]; cap = e.capacidad_efectiva()
        carga = _num(e.resultado.detalle.get("carga_t_h")) if e.resultado is not None else None
        if not cap or not carga:
            continue
        if fallas is not None and k in fallas:
            if fallas[k] is None:
                continue
            mtbf, mttr = float(fallas[k][0]), float(fallas[k][1]); origen = "Pestaña Línea"
        else:
            f = LF.fallas_defecto(e)
            if f is None:
                continue
            mtbf, mttr = AJ.media(f["mtbf"]), AJ.media(f["mttr"]); origen = f.get("origen", "Supuesto")
        out.append(dict(id=k, nombre=e.nombre, tasa_mp=d["carga"] * float(cap) / carga, mtbf=mtbf, mttr=mttr,
                        disponibilidad=disponibilidad(mtbf, mttr), origen=origen))
    return out, avisos


def capacidad_fallas(rng, horas, eqs: list, forma: tuple, f_mtbf: float = 1.0, f_mttr: float = 1.0, reduccion_pm: float = 0.0):
    """Capacidad que dejan las fallas en cada período (t de materia prima): mín por equipo de tasa × (h − tiempo caído).
    forma: (réplicas, años, períodos). Fallas Poisson de media h·A/MTBF y tiempo caído gamma(forma = fallas, escala = MTTR).
    Devuelve (capacidad, horas caídas medias por equipo y período). Sin equipos, capacidad infinita."""
    h = np.asarray(horas, dtype=float)
    cap = np.full(forma, np.inf); caidas = []
    red = min(max(float(reduccion_pm), 0.0), REDUCCION_MAX)
    for eq in eqs:
        mtbf = float(eq["mtbf"]) * float(f_mtbf) / (1.0 - red); mttr = float(eq["mttr"]) * float(f_mttr)
        a = mtbf / (mtbf + mttr)
        nf = rng.poisson(h * a / mtbf, size=forma)
        caida = np.minimum(rng.gamma(nf, mttr), h) if mttr > 0 else np.zeros(forma)
        cap = np.minimum(cap, float(eq["tasa_mp"]) * (h - caida))
        caidas.append(caida.mean(axis=(0, 1)))
    return cap, caidas


# ----------------------------------------------------------------------------------------------- demanda y capacidad
def estacional(valores, amplitud: float, pico: float = 0.5):
    """Multiplica la serie por 1 + amplitud·cos(2π(i − pico·n)/n) y la reescala para conservar el total."""
    v = np.asarray(valores, dtype=float); n = len(v); a = max(0.0, min(float(amplitud), 0.95))
    if n < 2 or a == 0 or v.sum() <= 0:
        return v.copy()
    i = np.arange(n); w = v * (1 + a * np.cos(2 * np.pi * (i - pico * (n - 1)) / n))
    return w * v.sum() / w.sum()


def periodos(pl, periodo: str = "semana", demanda: list | None = None, disp_programa: float = 1.0,
             estacionalidad: float | None = None) -> dict:
    """Demanda esperada por período en t de materia prima y horas de producción de cada período.
    demanda: lista del desafío en t de producto por período (números o dicts con «valor»); si no hay, la curva de llegada de
    Temporada sumada por semanas (7 días) o meses (30 días), con la estacionalidad del rubro (None = la de ESTACIONALIDAD).
    Las horas son días × horas por día × disponibilidad del programa."""
    d = TM.datos_planta(pl); D, H = d["D"], d["H"]
    ln = OP.linea(pl); mp = ln["mp_por_t"] if ln and ln.get("mp_por_t") else 1.0
    if demanda:
        vals = [_num(x.get("valor", x.get("demanda")) if isinstance(x, dict) else x) for x in demanda]
        if any(v is None or v < 0 for v in vals):
            raise ValueError("La demanda del desafío debe ser una lista de números no negativos (t de producto por período).")
        n = len(vals); dem = np.array(vals, dtype=float) * mp
        dias = np.full(n, D / n); etiquetas = [f"Período {i + 1}" for i in range(n)]; origen = "desafío"
    else:
        if periodo not in PERIODOS:
            raise ValueError(f"Período desconocido: {periodo}.")
        largo = PERIODOS[periodo]; curva = TM.curva_llegada(pl)
        grupos = [list(range(i, min(i + largo, D))) for i in range(0, D, largo)]
        dem = np.array([sum(curva[j] for j in g) for g in grupos], dtype=float); dias = np.array([len(g) for g in grupos], dtype=float)
        etiquetas = [("Semana " if periodo == "semana" else "Mes ") + str(i + 1) for i in range(len(grupos))]; origen = "temporada"
        a = ESTACIONALIDAD.get(pl.rubro, 0.0) if estacionalidad is None else float(estacionalidad)
        if a > 0:                                                     # la estacionalidad se aplica a la tasa diaria
            nueva = estacional(dem / dias, a) * dias; dem = nueva * dem.sum() / nueva.sum()
    horas = dias * H * float(disp_programa)
    return dict(demanda=dem, horas=horas, dias=dias, etiquetas=etiquetas, origen=origen, mp_por_t=mp, periodo=periodo,
                total_diseno=d["total"], dias_temporada=D, horas_dia=H)


def capacidad_estrategia(demanda, horas, cap_t_h: float, estrategia: str, holgura: float = 0.0):
    """Capacidad planificada de cada período (t) según la estrategia, limitada a la capacidad de la línea (t/h × horas)."""
    dem = np.asarray(demanda, dtype=float); h = np.asarray(horas, dtype=float)
    if np.any(h <= 0):
        raise ValueError("Cada período debe tener horas de producción positivas.")
    tasa = dem / h; media = dem.sum() / h.sum()
    if estrategia == "seguimiento":
        t = tasa.copy()
    elif estrategia == "un_nivel":
        t = np.full_like(tasa, media)
    elif estrategia == "dos_niveles":
        alto = tasa >= media * (1 - 1e-9)
        t_alto = dem[alto].sum() / h[alto].sum() if alto.any() else media
        t_bajo = dem[~alto].sum() / h[~alto].sum() if (~alto).any() else media
        t = np.where(alto, t_alto, t_bajo)
    else:
        raise ValueError(f"Estrategia desconocida: {estrategia}.")
    t = np.minimum(t * (1.0 + float(holgura)), float(cap_t_h))
    return t * h


def cambios_capacidad(capacidad, horas) -> float:
    """Capacidad cambiada en la temporada (t): suma de los cambios de tasa entre períodos × horas del período típico (mediana)."""
    t = np.asarray(capacidad, dtype=float) / np.asarray(horas, dtype=float)
    if len(t) < 2:
        return 0.0
    dif = np.abs(np.diff(t)); dif[dif <= 1e-9 * max(1.0, float(np.abs(t).max()))] = 0.0    # ruido de redondeo
    return float(dif.sum() * np.median(horas))


# ----------------------------------------------------------------------------------------------- contexto
def contexto(pl, r: dict, E: dict, periodo: str = "semana", demanda: list | None = None, costeo: dict | None = None,
             fallas: dict | None = None, aplicar_programa: bool = True, margen: float | None = None,
             estacionalidad: float | None = None) -> dict | None:
    """Arma lo que necesita simular: períodos, equipos, capacidad de la línea, combustible desplazado y parámetros base.
    None si la planta no tiene caldera o generador con horas (no hay ahorro que evaluar). costeo: st.session_state["costeo"];
    si trae total_clp positivo, la inversión es ese total en millones de pesos."""
    s = R.supuestos(r, E)
    if s is None:
        return None
    avisos = list(s["avisos"]); base = dict(s["base"])
    inv_c = _num((costeo or {}).get("total_clp"))
    if inv_c and inv_c > 0:
        base["inversion_planta"] = inv_c / 1e6
        txt = f"{inv_c / 1e6:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
        avisos.append(f"En el alcance planta la inversión es el costo total de la planta del costeo: {txt} MM$.")
    disp = 1.0
    if aplicar_programa:
        try:
            disp = float(TM.programa_temporada(pl, resumen=r)["disponibilidad"])
        except Exception as e:                       # el programa es opcional: sin él se usan todas las horas
            avisos.append(f"No se pudo aplicar el programa de la temporada ({e}); se usan todas las horas de diseño.")
    per = periodos(pl, periodo, demanda, disp, estacionalidad)
    cap = TM.capacidad_linea(pl)
    if cap is None:
        cap = TM.datos_planta(pl)["carga"]
        avisos.append("La línea no tiene capacidades declaradas: se usa la alimentación de diseño como capacidad.")
    eqs, av_l = equipos(pl, fallas)
    base.update(margen=float(margen) if margen is not None else margen_defecto(pl.rubro), frac_ocioso=SUPUESTOS["frac_ocioso"].valor,
                frac_ajuste=SUPUESTOS["frac_ajuste"].valor, cv_demanda=SUPUESTOS["cv_demanda"].valor, holgura=SUPUESTOS["holgura"].valor,
                f_mtbf=1.0, f_mttr=1.0, reduccion_pm=SUPUESTOS["reduccion_pm"].valor, costo_pm_equipo=SUPUESTOS["costo_pm_equipo"].valor,
                alcance="planta" if (inv_c and inv_c > 0) else "recuperador")
    mtbf_r, mttr_r = LF.FALLAS_TIPO["termico"]
    rec = dict(id="recuperador", nombre="Recuperador de calor", tasa_mp=math.inf, mtbf=mtbf_r, mttr=mttr_r,
               disponibilidad=disponibilidad(mtbf_r, mttr_r), origen="Supuesto")
    return dict(rubro=pl.rubro, combustible=s["combustible"], desplazado=s["desplazado"], base=base, rangos_riesgo=s["rangos"],
                periodos=per, equipos=eqs, recuperador=rec, cap_t_h=float(cap), disp_programa=disp, avisos=avisos + av_l)


# ----------------------------------------------------------------------------------------------- Montecarlo
def _stats(v: np.ndarray) -> dict:
    p5, p50, p95 = np.percentile(v, [5, 50, 95])
    return dict(media=float(v.mean()), desviacion=float(v.std(ddof=1)) if v.size > 1 else 0.0, p5=float(p5), p50=float(p50),
                p95=float(p95), prob_negativo=float((v < 0).mean()), prob_positivo=float((v > 0).mean()))


def simular(ctx: dict, params: dict | None = None, n: int = 2000, semilla: int = 135, estrategias=ESTRATEGIAS) -> dict:
    """Montecarlo vectorizado: n réplicas × años × períodos. Devuelve, por estrategia, el VAN de cada réplica con su media,
    desviación, percentiles 5, 50 y 95 y P(VAN < 0), déficit, exceso y producción medios por año (t de producto), los
    componentes medios del flujo anual (MM$) y las series medias por período. params reemplaza valores de ctx["base"]."""
    t0 = time.perf_counter()
    p = dict(ctx["base"]); p.update(params or {})
    per = ctx["periodos"]; dem0 = per["demanda"]; h = per["horas"]; mp = per["mp_por_t"]
    A = int(p["anios"]); n = int(n); P = len(dem0); forma = (n, A, P)
    if P == 0 or A < 1 or n < 1:
        raise ValueError("Se necesitan al menos un período, un año y una réplica.")
    if p.get("alcance", "recuperador") not in ALCANCES:
        raise ValueError(f"Alcance desconocido: {p.get('alcance')}.")
    p.setdefault("alcance", "recuperador")
    rng = np.random.default_rng(int(semilla))
    cv = max(0.0, float(p["cv_demanda"]))
    fac = rng.gamma(1.0 / cv ** 2, cv ** 2, size=forma) if cv > 0 else np.ones(forma)
    dem = dem0 * fac
    cap_f, caidas = capacidad_fallas(rng, h, ctx["equipos"], forma, p["f_mtbf"], p["f_mttr"], p["reduccion_pm"])
    red = min(max(float(p["reduccion_pm"]), 0.0), REDUCCION_MAX)
    costo_pm = len(ctx["equipos"]) * float(p["costo_pm_equipo"]) * red / 0.5
    ahorro_base = R.ahorro_anual(p, ctx["desplazado"], ctx["combustible"])
    rec = ctx.get("recuperador")
    if rec is not None:                     # fracción del período con el recuperador operando (sin preventivo de la línea)
        _c, c_rec = capacidad_fallas(rng, h, [dict(rec, tasa_mp=1.0)], forma, p["f_mtbf"], p["f_mttr"], 0.0)
        f_rec = _c / h; caida_rec = c_rec[0]
    else:
        f_rec = np.ones(forma); caida_rec = np.zeros(P)
    planta = p["alcance"] == "planta"
    inversion = float(p.get("inversion_planta") or p["inversion"]) if planta else float(p["inversion"])
    m_mp = float(p["margen"]) / mp / 1e6                                     # MM$ por t de materia prima
    df = 1.0 / (1.0 + float(p["tasa"])) ** np.arange(1, A + 1)
    out = {}
    for est in estrategias:
        L = capacidad_estrategia(dem0, h, ctx["cap_t_h"], est, p["holgura"])
        disp = np.minimum(L, cap_f)
        prod = np.minimum(dem, disp); deficit = dem - prod; exceso = disp - prod
        prod_y = prod.sum(axis=2); def_y = deficit.sum(axis=2); exc_y = exceso.sum(axis=2)
        ajuste = cambios_capacidad(L, h)
        ahorro = ahorro_base * (prod * f_rec).sum(axis=2) / per["total_diseno"]
        perdido = def_y * m_mp; ocioso = exc_y * m_mp * float(p["frac_ocioso"]); c_aj = ajuste * m_mp * float(p["frac_ajuste"])
        if planta:
            ingreso = prod_y * m_mp
            flujo = ingreso + ahorro - float(p["costo_anual"]) - costo_pm - ocioso - c_aj
        else:                               # incremental: lo de la línea se cancela con y sin recuperador
            ingreso = np.zeros_like(ahorro)
            flujo = ahorro - float(p["costo_anual"])
        van = -inversion + flujo @ df
        out[est] = dict(estrategia=est, nombre=NOMBRE_ESTRATEGIA[est], van=van, **_stats(van),
                        deficit_t=float(def_y.mean()) / mp, exceso_t=float(exc_y.mean()) / mp, produccion_t=float(prod_y.mean()) / mp,
                        demanda_t=float(dem.sum(axis=2).mean()) / mp, ajuste_t=ajuste / mp,
                        servicio=float(prod_y.sum() / dem.sum(axis=2).sum()) if dem.sum() > 0 else 1.0,
                        componentes=dict(margen_produccion=float(np.mean(ingreso)), ahorro=float(ahorro.mean()), costo_anual=float(p["costo_anual"]),
                                         preventivo=costo_pm if planta else 0.0,
                                         margen_perdido=float(perdido.mean()), ocioso=float(ocioso.mean()), ajuste=c_aj,
                                         flujo=float(flujo.mean())),
                        por_periodo=dict(demanda=dem0 / mp, demanda_media=dem.mean(axis=(0, 1)) / mp, capacidad=L / mp,
                                         disponible=np.where(np.isfinite(disp), disp, np.nan).mean(axis=(0, 1)) / mp,
                                         produccion=prod.mean(axis=(0, 1)) / mp, deficit=deficit.mean(axis=(0, 1)) / mp,
                                         exceso=exceso.mean(axis=(0, 1)) / mp))
    return dict(estrategias=out, alcance=p["alcance"], n=n, semilla=int(semilla), anios=A, periodos=P, horas_caidas=caidas, horas_caidas_recuperador=caida_rec,
                inversion=inversion, costo_pm=costo_pm if planta else 0.0,
                ahorro_diseno=ahorro_base, segundos=time.perf_counter() - t0, params=p)


def rangos_tornado(ctx: dict) -> dict:
    """Rangos del tornado: precio, tasa e inversión (±30 %) como riesgo.supuestos; variación de la demanda de 5 a 30 %,
    MTBF y MTTR de 0,5 a 1,5 veces y holgura de 0 a 25 % (Supuesto PAT 135). En el alcance planta se agrega el margen ±30 % y la
    inversión es la del costeo; en el alcance recuperador el margen no entra (se cancela). Se ensanchan para contener la base."""
    b = ctx["base"]; rr = ctx["rangos_riesgo"]
    band = lambda v, lo, hi: (min(lo, v), max(hi, v))
    planta = b.get("alcance") == "planta"
    k_inv = "inversion_planta" if planta and b.get("inversion_planta") else "inversion"
    out = {"precio": rr["precio"], "tasa": rr["tasa"], k_inv: (b[k_inv] * 0.7, b[k_inv] * 1.3)}
    if planta:
        out["margen"] = (b["margen"] * 0.7, b["margen"] * 1.3)
    out.update(cv_demanda=band(b["cv_demanda"], 0.05, 0.30), f_mtbf=band(b["f_mtbf"], 0.5, 1.5), f_mttr=band(b["f_mttr"], 0.5, 1.5),
               holgura=band(b["holgura"], 0.0, 0.25))
    return out


def tornado(ctx: dict, estrategia: str = "seguimiento", params: dict | None = None, n: int = 400, semilla: int = 135) -> list:
    """Tornado del VAN medio de la estrategia (riesgo.tornado) con Montecarlo de n réplicas y la misma semilla en cada punto."""
    base = dict(ctx["base"]); base.update(params or {})
    fn = lambda q: simular(ctx, q, n=n, semilla=semilla, estrategias=(estrategia,))["estrategias"][estrategia]["media"]
    filas = R.tornado(base, rangos_tornado(dict(ctx, base=base)), fn)
    for f in filas:
        f["nombre"] = NOMBRES.get(f["clave"], f["clave"])
    return filas


def histograma(valores, n_clases: int = 30, desde=None, hasta=None) -> list:
    """Clases de igual ancho (desde, hasta, frecuencia); con desde y hasta fijos sirve para comparar estrategias en las mismas clases."""
    v = np.asarray(valores, dtype=float)
    if v.size == 0:
        return []
    lo = float(v.min()) if desde is None else float(desde); hi = float(v.max()) if hasta is None else float(hasta)
    if hi - lo < 1e-12:
        return [(lo, hi, int(v.size))]
    cuenta, bordes = np.histogram(v, bins=n_clases, range=(lo, hi))
    return [(float(bordes[i]), float(bordes[i + 1]), int(c)) for i, c in enumerate(cuenta)]
