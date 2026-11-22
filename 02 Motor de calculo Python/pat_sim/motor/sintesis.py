"""Planta automática y carta en blanco (PAT 136, tarea T22, puntos 5 y 6 de los comentarios del profesor Torres del 13-11-2026).

Punto 6: «botón para armar la planta automáticamente con las mejores opciones». armar_planta(tipo_planta_id, demanda) hace la
síntesis en cuatro pasos:
1. Cadena de operaciones del tipo de planta (catalogos/plantas_genericas.py), en orden, con la precedencia de los estados del
   material (motor/precedencia.py): cada equipo recibe el estado que entrega el anterior.
2. Dimensionamiento con la demanda (motor/demanda.py): capacidad de diseño = percentil (o pico) de la serie en t/h × factor de
   servicio; punto de operación = media de la serie. Si la demanda es de producto (mercado), la materia prima sale del rendimiento
   másico de la misma planta resuelta con 1 t/h.
3. Mejor alternativa de cada equipo con la planta resuelta a la capacidad de diseño: motor/seleccion.py (un equipo más grande o n
   en paralelo, con y sin redundancia, por costo anual total C = C_inv + C_op + C_inef de motor/costo_total.py: anualidad de la
   inversión de motor/costeo.py + energía y mantenimiento + costo de ineficiencia por disponibilidad) y, en las operaciones que traen tipos de equipo alternativos (por ejemplo el secador), el tipo de menor
   costo de su etapa. Solo se llaman esas funciones; no se cambian.
4. La planta queda resuelta en el punto de operación, con la capacidad instalada de la selección en cada equipo, y lleva el informe
   de la síntesis en pl._p["sintesis"] (decisiones, supuestos y límites), que se guarda con la versión.

Los cuatro rubros con escenario (tomate, pellet, chip y leña) usan los mismos tipos de equipo y los parámetros de su escenario
(escenarios/*.crear), así que dan una planta con las mismas operaciones. Los seis tipos nuevos se arman con el registro genérico:
alimentación genérica y equipos de balance simplificado (catalogos/iso_generico.py) donde el equipo propio es de biomasa o no
retira agua. Límites en LIMITES.

PAT 138 (pedido de Jaime del 13-11-2026): la planta de tomate tiene 10 tipos (catalogos/plantas_tomate.py, variantes de la
planta basada en Agrozzi) y su demanda es la llegada diaria de tomate con una de 10 distribuciones (demanda.llegada_tomate).
armar_planta("tomate", demanda, variante=...) toma los parámetros del escenario de la variante; si no se da la variante, se lee
de la demanda (resultado de llegada_tomate o desafío de la sesión con «variante_tomate»). Sin variante queda Agrozzi, como antes.

PAT 144 a (20-11-2026): la pantalla Desafío también arma la planta de agar agar (catalogos/plantas_agar.py, modelo de proceso ×
tamaño) con la llegada de alga seca (demanda.llegada_agar). armar_planta("agar", demanda, variante=...) con una variante de agar
arma la cadena con los equipos propios de catalogos/agar.py (los «equivalentes» de cada operación, más el lavado y neutralización
del escenario) y los parámetros del escenario de la variante; sin variante, el agar sigue con los tipos genéricos de antes.

Punto 5: «Diseño parte en carta en blanco». planta_en_blanco(tipo_planta_id, demanda, desafio) da una planta sin equipos del
rubro del tipo de planta, con la demanda y el tipo guardados en pl._p, para que el estudiante elija los equipos de la librería.
"""
from __future__ import annotations
import math

from .planta import Planta, TIPOS_SERVICIO
from .operacion import Supuesto
from . import precedencia as PR

PRODUCTO = ("producto", "biomasa")
_SD = "sin dato de una planta ni fuente segura en la carpeta del proyecto"
SUPUESTOS = {s.clave: s for s in [
    Supuesto("percentil", "Percentil de la serie para la capacidad de diseño", 95.0, "%",
             "Cubre 95 % de los períodos; los peaks restantes esperan en la cancha (oferta agrícola) o salen del inventario (mercado). "
             "El mismo percentil que entrega motor/demanda.estadisticas; " + _SD),
    Supuesto("factor_servicio", "Factor de servicio sobre la capacidad de diseño", 1.10, "—",
             "10 % sobre la demanda de diseño para detenciones cortas y variación de la materia prima, el orden de la holgura de "
             "escenarios/capacidades.py; " + _SD),
    Supuesto("horas", "Horas de operación al año sin dato de la planta", 7200.0, "h/año",
             "300 días de 24 h, el mismo Supuesto «horas» de motor/seleccion.py"),
    Supuesto("rama", "Fracción de la corriente que va a la rama secundaria", 0.40, "—",
             "Licor de prensa de la harina de pescado: orden de magnitud del líquido que sale de la prensa; el balance simplificado "
             "no separa la torta del licor (" + _SD + ")"),
    Supuesto("operacion", "Punto de operación", 0.0, "—",
             "Media de la serie (en los períodos con llegada, si la demanda es de oferta agrícola o mixta): la planta queda resuelta "
             "ahí y la utilización muestra la holgura frente a la capacidad instalada"),
]}

# Supuestos del balance simplificado de los tipos de planta nuevos: sólidos de la materia prima y fracción de sólidos a la salida de
# las operaciones que retiran agua (por código de operación). Sin fuente segura: orden de magnitud del producto, para revisar.
SIMPLE = {
    "agar": dict(solidos=0.20, x={"secado": 0.88},
                 nota="La corriente pasa con el 20 % de agar del gel prensado (McHugh, 2003); el lavado y la extracción no agregan agua"),
    "jugo_manzana": dict(solidos=0.12, x={"evaporacion": 0.70},
                         nota="Jugo de cerca de 12 °Brix (Supuesto) concentrado a cerca de 70 °Brix (producto del catálogo)"),
    "leche_polvo": dict(solidos=0.125, x={"evaporacion": 0.48, "secado": 0.97},
                        nota="Leche entera de 12,5 % de sólidos, concentrado de 48 % y polvo de 3 % de humedad (Supuesto)"),
    "harina_pescado": dict(solidos=0.25, x={"evaporacion": 0.40, "secado": 0.90},
                           nota="Pescado de 25 % de sólidos, agua de cola concentrada a 40 % y harina de 10 % de humedad (Supuesto)"),
    "ciruela_deshidratada": dict(solidos=0.22, x={"secado": 0.80},
                                 nota="Ciruela fresca de 22 % de sólidos secada a 20 % de humedad (Supuesto); la hidratación no agrega agua"),
    "vino_granel": dict(solidos=0.22, x={},
                        nota="Mosto de 22 °Brix; la fermentación no se modela (el balance no cambia la composición)"),
}
LIMITES = [
    "Los seis tipos de planta nuevos usan un balance simplificado: equipos genéricos de la ISO 10628 que dejan pasar la corriente y "
    "equipos «simplificados» que retiran agua con el calor latente y un rendimiento térmico Supuesto (catalogos/iso_generico.py). "
    "No se modelan reacciones, fermentaciones, adición de agua de lavado o de extracción, ni coproductos separados.",
    "La rama del licor de prensa de la harina de pescado sale de la misma corriente de la prensa con un reparto Supuesto.",
    "La selección compara el costo anual total C = C_inv + C_op + C_inef (motor/costo_total.py, usado por "
    "motor/seleccion.py): anualidad de la inversión, energía con la curva de eficiencia más mantenimiento, y producción perdida por "
    "indisponibilidad. La energía de las unidades sin ficha parte de la potencia eléctrica del equipo de la planta (Supuesto); el ahorro "
    "de calor de los tipos alternativos se compara en las pantallas Alternativas y Economía.",
    "Los tamaños comerciales son los del catálogo del mantenedor (Supuesto escalonado); los equipos sin tamaños propios usan los "
    "genéricos en t/h de carga.",
    "Las horas de operación salen de la alimentación del escenario o del Supuesto de 7.200 h al año; una serie mensual o semanal se "
    "lleva a t/h de operación con esas horas.",
]
_NO_COPIAR = {"capacidad", "costo", "estado", "consumo_especifico", "modelo", "unidades", "unidades_requeridas", "mtbf_h", "mttr_h",
              "carga_t_h", "temporada_t"}


# ---------------------------------------------------------------- utilidades
def _tipos():
    from ..catalogos.registro import TIPOS
    return TIPOS


def _pg():
    from ..catalogos import plantas_genericas as PG
    return PG


def _puerto_prod(ps):
    return next((p for p in ps if p.tipo in PRODUCTO), None)


def _limpio(nombre: str) -> str:
    return " ".join(str(nombre).replace("*", "").split())


def _es_paso(cls) -> bool:
    """Equipo genérico de la ISO 10628 que deja pasar la corriente sin cambiarla (no retira agua)."""
    from ..catalogos.iso_generico import EquipoISO
    return issubclass(cls, EquipoISO)


def clase_para(tipo: str, medio: str, funcion: str = ""):
    """Clase que representa una operación en una línea de «medio» (producto o biomasa): la del tipo si sus puertos sirven; si no,
    su versión de balance simplificado «simple_<tipo>» (también para un genérico de la ISO que debe secar o concentrar)."""
    T = _tipos(); cls = T[tipo]
    pe = _puerto_prod(cls.entradas)
    simple = T.get(PR.PREFIJO_SIMPLE + tipo)
    if pe is not None and pe.tipo != medio and simple is not None:
        return simple
    if funcion in ("secado", "concentracion") and _es_paso(cls) and simple is not None:
        return simple
    return cls


def fijar_alimentacion(eq, t_h: float) -> None:
    """Fija la materia prima de la alimentación en t/h (por temporada en el tomate, por carga en los demás)."""
    t_h = max(1e-6, float(t_h))
    if "temporada_t" in eq.params and hasattr(eq, "horas"):
        eq.set("temporada_t", t_h * eq.horas())
    elif "carga_t_h" in eq.params:
        eq.set("carga_t_h", t_h)
    else:
        raise ValueError(f"{eq.id} no tiene una alimentación editable")


def horas_operacion(pl) -> tuple[float, str]:
    for e in pl.equipos.values():
        if hasattr(e, "horas"):
            return float(e.horas()), f"Alimentación {e.id}: {e.v('dias') if 'dias' in e.params else ''} días".strip()
    return SUPUESTOS["horas"].valor, "Supuesto: " + SUPUESTOS["horas"].justificacion


# ---------------------------------------------------------------- demanda y dimensionamiento
def leer_demanda(demanda, planta_id: str | None = None, semilla=None) -> dict:
    """Normaliza la demanda: None (la demanda por defecto del tipo de planta), id de perfil de motor/demanda.py, resultado de
    demanda.generar(), desafío de la sesión (con «demanda_t_h»), número (t/h constante) o lista de t/h."""
    from . import demanda as DM
    if demanda is None:
        if planta_id is None:
            raise ValueError("Falta la demanda o el tipo de planta")
        demanda = _pg().planta(planta_id)["demanda_defecto"]
    if isinstance(demanda, str):
        demanda = DM.generar(demanda, semilla=semilla)
    if isinstance(demanda, (int, float)):
        v = float(demanda)
        return dict(perfil=None, nombre="Demanda constante", logica="mercado", periodo="hora", unidad="t", serie_t_h=[v], fuente="Usuario")
    if isinstance(demanda, (list, tuple)):
        return dict(perfil=None, nombre="Serie de demanda", logica="mercado", periodo="hora", unidad="t",
                    serie_t_h=[float(x) for x in demanda], fuente="Usuario")
    if isinstance(demanda, dict) and demanda.get("serie_t_h") is not None:
        return dict(perfil=demanda.get("perfil"), nombre=demanda.get("nombre", "Demanda"), logica=demanda.get("logica", "mercado"),
                    periodo=demanda.get("periodo", "mes"), unidad=demanda.get("unidad", "t"),
                    serie_t_h=[float(x) for x in demanda["serie_t_h"]], fuente=f"motor/demanda.py, perfil {demanda.get('perfil')}",
                    variante=demanda.get("variante"), distribucion=demanda.get("distribucion"))
    if isinstance(demanda, dict) and demanda.get("demanda_t_h") is not None:          # desafío de la sesión (motor/desafio.py)
        # PAT 138: el desafío de tomate guarda su lógica (agrícola); los demás siguen como demanda de mercado
        return dict(perfil=demanda.get("perfil_demanda"), nombre=demanda.get("titulo", "Desafío"), logica=demanda.get("logica", "mercado"),
                    variante=demanda.get("variante_tomate"), distribucion=demanda.get("distribucion_tomate"),
                    periodo=demanda.get("periodo", "mes"), unidad=demanda.get("unidad", "t"),
                    serie_t_h=[float(x) for x in demanda["demanda_t_h"]], fuente=demanda.get("fuente_demanda", "Desafío"))
    raise ValueError("No reconozco la demanda: use un perfil de motor/demanda.py, una serie en t/h o un número")


def dimensionar(dem: dict, horas: float, criterio: str = "percentil", percentil: float | None = None,
                factor_servicio: float | None = None) -> dict:
    """Capacidad de diseño y punto de operación en t/h de operación (de materia prima o de producto, según la lógica)."""
    from .demanda import percentil as _pct
    p = SUPUESTOS["percentil"].valor if percentil is None else float(percentil)
    f = SUPUESTOS["factor_servicio"].valor if factor_servicio is None else float(factor_servicio)
    serie = [max(0.0, float(x)) for x in dem["serie_t_h"]]
    if not serie or max(serie) <= 0:
        raise ValueError("La serie de demanda no tiene valores positivos")
    razon = 8760.0 / float(horas) if dem.get("periodo") in ("semana", "mes", "año") and horas else 1.0
    if criterio == "pico":
        base = max(serie)
    elif criterio == "media":
        base = sum(serie) / len(serie)
    else:
        base = _pct(serie, p)
    agricola = dem.get("logica") in ("agricola", "mixta")
    activos = [x for x in serie if x > 0] if agricola else serie
    media = sum(activos) / len(activos)
    return dict(criterio=criterio, percentil=p, factor_servicio=f, razon_horas=razon, horas=float(horas),
                base_t_h=base * razon, diseno_t_h=base * razon * f, operacion_t_h=media * razon,
                de="materia prima" if dem.get("logica") == "agricola" else "producto")


# ---------------------------------------------------------------- armado de la línea
def _referencia(pid: str, variante: str | None = None):
    """Escenario del tipo de planta (sin capacidades) para tomar sus parámetros; None en los tipos nuevos. PAT 138: en el tomate,
    el escenario de la variante (catalogos/plantas_tomate.py)."""
    try:
        if pid == "tomate" and variante:
            from ..catalogos import plantas_tomate as PT
            return PT.crear_escenario(variante, capacidades=False)
        if pid == "agar" and variante:                                # PAT 144 a: el escenario de la variante de agar
            from ..catalogos import plantas_agar as PA
            return PA.crear_escenario(variante, capacidades=False)
        return _pg().crear_escenario(pid, capacidades=False)
    except Exception:
        return None


def _copiar(eq, ref):
    """Copia al equipo los parámetros del primer equipo del mismo tipo del escenario (mismo modelo físico que el escenario)."""
    if ref is None:
        return False
    fuente = next((e for e in ref.equipos.values() if e.tipo == eq.tipo), None)
    if fuente is None:
        return False
    for k, p in fuente.params.items():
        if k in eq.params and k not in _NO_COPIAR:
            eq.set(k, p.valor, categoria=p.categoria, fuente=p.fuente, justificacion=p.justificacion)
    return True


_META_SALIDA = ("humedad_salida", "brix_salida", "x_salida")


def _copiar_meta(eq, ref, tipo_principal: str) -> None:
    """A un tipo alternativo se le da la especificación de salida (humedad o sólidos) del equipo principal del escenario, para que
    la comparación de costos sea a igual producto."""
    fuente = next((e for e in ref.equipos.values() if e.tipo == tipo_principal), None)
    for k in _META_SALIDA:
        if fuente is not None and k in fuente.params and k in eq.params:
            p = fuente.params[k]
            eq.set(k, p.valor, categoria=p.categoria, fuente=p.fuente, justificacion=p.justificacion)


def operaciones_agar() -> list[dict]:
    """PAT 144 a: la cadena del tipo de planta agar con el equipo propio de catalogos/agar.py en cada operación (su «equivalente»)
    y el lavado y neutralización después del tratamiento alcalino, como en escenarios/agar.py (sin él, la soda llega al extractor).
    El lavado y neutralización no cambia el estado del material, así que no lleva fila de precedencia."""
    out = []
    for o in _pg().planta("agar")["operaciones"]:
        q = dict(o)
        if o.get("equivalentes"):
            q["tipo_equipo"] = o["equivalentes"][0]
        out.append(q)
        if o["codigo"] == "alcali":
            out.append(dict(o, codigo="neutralizacion", nombre="Lavado y neutralización del alga tratada", funcion="lavado",
                            tipo_equipo="lavado_neutralizacion_agar", entrada=[o["salida"]], salida=o["salida"], alternativas=(),
                            equivalentes=(), opcional=False, rama="",
                            nota="Del escenario base (escenarios/agar.py): la soda se va con el agua de lavado"))
    return out


def _construir(pid: str, elecciones: dict | None = None, ref=None, alimentacion_t_h: float = 1.0,
               operaciones: list[dict] | None = None) -> tuple[Planta, list[dict]]:
    """Planta con la cadena del tipo pid. elecciones: {código de operación: tipo de equipo} para las alternativas.
    operaciones: otra cadena para el mismo tipo (PAT 144 a: la del agar con sus equipos propios); con ella no se usa el balance
    simplificado (SIMPLE). Devuelve (planta resuelta, operaciones con el equipo que las representa)."""
    PG = _pg(); T = _tipos(); p = PG.planta(pid); elecciones = elecciones or {}
    from .lienzo import siguiente_id
    pl = Planta(f"Planta automática: {p['nombre']}", p["rubro"])
    if ref is not None:
        pl.globales.update(ref.globales)
    ops = operaciones or p["operaciones"]
    primera = T[ops[0]["tipo_equipo"]]
    medio = (_puerto_prod(primera.salidas) or _puerto_prod(primera.entradas)).tipo if not primera.entradas else "producto"
    sim = SIMPLE.get(pid, {}) if operaciones is None else {}
    pos = [0]

    def nuevo(cls, nombre, fila_extra=0):
        i = pos[0]; pos[0] += 1
        x, y = 40 + 160 * (i % 7), 120 + 220 * (i // 7) + fila_extra
        eq = cls(siguiente_id(pl, cls.iso_letra), _limpio(nombre)[:60], x, y)
        pl.agregar(eq)
        return eq

    usados = []
    ultimo = None; rama_ult = None; rama_ini = None; puerto_rama = None
    if primera.entradas:                                             # tipos nuevos: la recepción necesita una alimentación
        from ..catalogos.iso_generico import AlimentacionGenerica
        ali = nuevo(AlimentacionGenerica, f"Alimentación de {p['materia_prima'].lower()}")
        ali.set("materia", p["materia_prima"])
        if "solidos" in sim:
            ali.set("solidos", sim["solidos"], categoria="Supuesto", fuente="motor/sintesis.py, SIMPLE", justificacion=sim.get("nota", ""))
        fijar_alimentacion(ali, alimentacion_t_h)
        ultimo = (ali, "producto")
    frac_rama = SUPUESTOS["rama"].valor
    for o in ops:
        tipo = elecciones.get(o["codigo"], o["tipo_equipo"])
        cls = clase_para(tipo, medio, o["funcion"])
        eq = nuevo(cls, o["nombre"], 160 if o.get("rama") else 0)
        if not _copiar(eq, ref) and tipo != o["tipo_equipo"] and ref is not None:
            _copiar_meta(eq, ref, o["tipo_equipo"])                    # alternativa: la misma especificación de salida
        if not cls.entradas:                                         # la operación es la alimentación (rubros con escenario)
            fijar_alimentacion(eq, alimentacion_t_h)
        xs = sim.get("x", {}).get(o["codigo"])
        if xs is not None:
            clave = "brix_salida" if "brix_salida" in eq.params else "x_salida" if "x_salida" in eq.params else None
            if clave:
                eq.set(clave, xs, categoria="Supuesto", fuente="motor/sintesis.py, SIMPLE", justificacion=sim.get("nota", ""))
        pe = _puerto_prod(eq.entradas); ps = _puerto_prod(eq.salidas)
        if pe is not None:
            if o.get("rama"):
                if rama_ult is None:                                  # la rama sale del último equipo de la línea principal
                    rama_ini, puerto_rama = ultimo
                    pl.conectar(rama_ini.id, puerto_rama, eq.id, pe.nombre, 100 * frac_rama)
                else:
                    pl.conectar(rama_ult[0].id, rama_ult[1], eq.id, pe.nombre)
            elif ultimo is not None:
                rep = 100 * (1 - frac_rama) if (rama_ini is not None and ultimo[0] is rama_ini) else 100.0
                pl.conectar(ultimo[0].id, ultimo[1], eq.id, pe.nombre, rep)
                if rama_ult is not None:                              # la rama vuelve a la línea principal
                    pl.conectar(rama_ult[0].id, rama_ult[1], eq.id, pe.nombre)
                    rama_ult = None
        if o.get("rama"):
            rama_ult = (eq, ps.nombre) if ps else rama_ult
        else:
            ultimo = (eq, ps.nombre) if ps else ultimo
        usados.append(dict(codigo=o["codigo"], operacion=_limpio(o["nombre"]), funcion=o["funcion"], tipo_catalogo=o["tipo_equipo"],
                           tipo=eq.tipo, equipo=eq.id, simplificado=eq.tipo.startswith(PR.PREFIJO_SIMPLE), opcional=o["opcional"],
                           alternativas=list(o.get("alternativas") or ())))
    # servicios: caldera a gas (vapor) o generador de calor a biomasa (aire caliente) y sus conexiones
    pide = {pt.tipo for e in pl.equipos.values() for pt in e.entradas if pt.tipo in ("vapor", "calor")}
    servicios = list(p.get("equipos_servicio") or ())
    if "vapor" in pide and not any(s.startswith("caldera_gas") for s in servicios):
        servicios.append("caldera_gas")
    for s in servicios:
        cls = T[s]
        sal = [pt for pt in cls.salidas if pt.tipo in ("vapor", "calor")]
        if not sal or sal[0].tipo not in pide:
            continue
        d = cls(siguiente_id(pl, cls.iso_letra), cls.nombre_tipo, 200, 120 + 220 * (1 + (pos[0] - 1) // 7) + 170)
        pl.agregar(d); _copiar(d, ref)
        n = 0
        for e in list(pl.equipos.values()):
            for pt in e.entradas:
                if pt.tipo == sal[0].tipo and e.id != d.id:
                    n += 1
                    pl.conectar(d.id, sal[0].nombre, e.id, pt.nombre, nombre=f"{'V' if pt.tipo == 'vapor' else 'Q'}{n}")
    _numerar(pl)
    pl.resolver()
    return pl, usados


def _numerar(pl):
    n = 0
    for c in pl.conexiones:
        if not c.nombre:
            n += 1; c.nombre = str(n)


def producto_final(pl) -> float | None:
    """t/h de producto a la salida del último equipo de la línea (la última operación de envasado o despacho)."""
    finales = [e for e in pl.equipos.values() if e.resultado and _puerto_prod(e.salidas)
               and not any(c.origen == e.id and not pl.es_servicio(c) for c in pl.conexiones)]
    if not finales:
        return None
    e = finales[-1]; ps = _puerto_prod(e.salidas)
    s = pl.salidas.get((e.id, ps.nombre))
    return s.m / 1000 if s is not None else None


def _alimentacion(pl):
    return next(e for e in pl.equipos.values() if not e.entradas and not e.tipo.startswith(("caldera", "generador")))


def _seleccionar(pl, catalogo, economia):
    from . import seleccion as SEL
    res = SEL.seleccionar(pl, catalogo=catalogo, economia=economia)
    return res, {e["equipo"]: e for e in res["etapas"]}


def _costo_etapa(et) -> float:
    a = (et or {}).get("recomendada")
    return float(a.get("C_clp", a["total_clp"])) if a else math.inf          # PAT 139: C = C_inv + C_op + C_inef


# ---------------------------------------------------------------- API
def armar_planta(tipo_planta_id: str, demanda=None, criterio: str = "percentil", percentil: float | None = None,
                 factor_servicio: float | None = None, alternativas: bool = True, catalogo: list[dict] | None = None,
                 economia: dict | None = None, desafio: dict | None = None, semilla=None, variante: str | None = None) -> Planta:
    """Planta automática del tipo de planta con la demanda dada (ver leer_demanda). Resuelta en el punto de operación, con la
    capacidad instalada de la mejor alternativa de cada equipo y el informe en pl._p["sintesis"].
    PAT 138: variante = tipo de planta de tomate de catalogos/plantas_tomate.py (solo con «tomate»); si falta, se toma de la
    demanda. Sin demanda y con variante, la llegada de la variante con la distribución por defecto (normal truncada).
    PAT 144 a: con «agar», variante = planta de agar de catalogos/plantas_agar.py (o la que trae la demanda); sin demanda, la
    llegada de alga seca de la variante con la distribución uniforme. Con variante de agar la cadena es la de operaciones_agar()."""
    PG = _pg(); p = PG.planta(tipo_planta_id)
    if catalogo is None:
        from ..datos.mantenedor import semilla_catalogo_comercial
        catalogo = semilla_catalogo_comercial()
    variante, distribucion = _variante(tipo_planta_id, demanda, variante)
    if tipo_planta_id == "tomate" and variante and demanda is None:
        from . import demanda as DM
        demanda = DM.llegada_tomate(variante, semilla=semilla, perdida_1pct=False)
        distribucion = demanda["distribucion"]
    agar = tipo_planta_id == "agar" and bool(variante)              # PAT 144 a
    if agar and demanda is None:
        from . import demanda as DM
        demanda = DM.llegada_agar(variante, semilla=semilla)
        distribucion = demanda["distribucion"]
    ops = operaciones_agar() if agar else None
    simple = tipo_planta_id in SIMPLE and not agar
    dem = leer_demanda(demanda, tipo_planta_id, semilla)
    ref = _referencia(tipo_planta_id, variante)
    pl1, _u = _construir(tipo_planta_id, None, ref, 1.0, ops)       # rendimiento másico con 1 t/h de materia prima
    h, f_h = horas_operacion(pl1)
    rend = producto_final(pl1) or 1.0
    dim = dimensionar(dem, h, criterio, percentil, factor_servicio)
    a_mp = 1.0 if dim["de"] == "materia prima" else 1.0 / rend      # t/h de materia prima por t/h de la demanda
    diseno_mp, oper_mp = dim["diseno_t_h"] * a_mp, dim["operacion_t_h"] * a_mp
    # elección del tipo de equipo en las operaciones con alternativas: menor costo anual de su etapa a la capacidad de diseño
    elecciones, comparadas = {}, []
    pl, usados = _construir(tipo_planta_id, elecciones, ref, diseno_mp, ops)
    res, etapas = _seleccionar(pl, catalogo, economia)
    if alternativas:
        for o in (ops or p["operaciones"]):
            alts = [a for a in (o.get("alternativas") or ()) if a in _tipos()]
            if not alts:
                continue
            u = next(x for x in usados if x["codigo"] == o["codigo"])
            costos = [dict(tipo=u["tipo"], costo=_costo_etapa(etapas.get(u["equipo"])))]
            for a in alts:
                try:
                    pa, ua = _construir(tipo_planta_id, dict(elecciones, **{o["codigo"]: a}), ref, diseno_mp, ops)
                    _r, ea = _seleccionar(pa, catalogo, economia)
                    eq_a = next(x for x in ua if x["codigo"] == o["codigo"])["equipo"]
                    if len(pa.avisos) > len(pl.avisos):                  # no cumple el producto: queda fuera de la comparación
                        costos.append(dict(tipo=pa.equipos[eq_a].tipo, costo=math.inf, error="; ".join(pa.avisos[:2])))
                        continue
                    costos.append(dict(tipo=pa.equipos[eq_a].tipo, costo=_costo_etapa(ea.get(eq_a)), elegido_tipo=a))
                except Exception as e:                               # la alternativa no resuelve con estos datos
                    costos.append(dict(tipo=a, costo=math.inf, error=str(e)))
            mejor = min(costos, key=lambda c: c["costo"])
            comparadas.append(dict(operacion=u["operacion"], opciones=[dict(tipo=c["tipo"], costo_anual_clp=None if math.isinf(c["costo"]) else c["costo"],
                                                                            nota=c.get("error", "")) for c in costos], elegido=mejor["tipo"]))
            if mejor.get("elegido_tipo"):
                elecciones[o["codigo"]] = mejor["elegido_tipo"]
        if elecciones:
            pl, usados = _construir(tipo_planta_id, elecciones, ref, diseno_mp, ops)
            res, etapas = _seleccionar(pl, catalogo, economia)
    # selección comercial a la capacidad de diseño y vuelta al punto de operación
    from . import seleccion as SEL
    elegidas = {k: e["recomendada"] for k, e in etapas.items() if e.get("recomendada")}
    SEL.aplicar(pl, elegidas)
    sin_sel = []
    for k, eq in pl.equipos.items():
        if k in elegidas or "capacidad" not in eq.params or eq.resultado is None:
            continue
        carga = eq.resultado.detalle.get("carga_t_h")
        if carga:
            eq.set("capacidad", math.ceil(float(carga) * 10) / 10, categoria="Supuesto",
                   fuente="Planta automática (PAT 136): carga a la capacidad de diseño, sin modelo comercial en el catálogo",
                   justificacion="Capacidad de diseño = percentil de la demanda × factor de servicio (motor/sintesis.py)")
            sin_sel.append(k)
    fijar_alimentacion(_alimentacion(pl), oper_mp)
    pl.resolver()
    decisiones = []
    for u in usados:
        et = etapas.get(u["equipo"]); a = (et or {}).get("recomendada")
        decisiones.append(dict(u, modelo=a["modelo"] if a else "", n=a["n"] if a else None, k=a["k"] if a else None,
                               instalada_t_h=a["instalada_t_h"] if a else pl.equipos[u["equipo"]].params.get("capacidad").valor
                               if "capacidad" in pl.equipos[u["equipo"]].params else None,
                               costo_anual_clp=a.get("C_clp", a["total_clp"]) if a else None, A_etapa=a["A_etapa"] if a else None,
                               etiqueta=a["etiqueta"] if a else "Sin modelo comercial: capacidad = carga de diseño (Supuesto)"))
    viol = PR.violaciones(pl, PR.tabla_plantas())
    nombre_tipo = p["nombre"]
    if agar:                                                        # PAT 144 a: nombre de la variante de agar
        from ..catalogos import plantas_agar as PA
        nombre_tipo = PA.variante(variante)["nombre"]
        pl.nombre = f"Planta automática: {nombre_tipo}"
    elif variante:                                                  # PAT 138: nombre de la variante de tomate
        from ..catalogos import plantas_tomate as PT
        nombre_tipo = PT.variante(variante)["nombre"]
        PT.ajustar_nombres(pl, variante)
        pl.nombre = f"Planta automática: {nombre_tipo}"
    v_tom, d_tom = (None, None) if agar else (variante, distribucion)
    informe = dict(tipo_planta=tipo_planta_id, nombre=nombre_tipo, rubro=p["rubro"], variante_tomate=v_tom, distribucion_tomate=d_tom, demanda=dict(perfil=dem.get("perfil"), nombre=dem["nombre"],
                   logica=dem["logica"], periodo=dem["periodo"], fuente=dem.get("fuente", "")),
                   dimensionamiento=dict(dim, rendimiento=rend, materia_prima_diseno_t_h=diseno_mp, materia_prima_operacion_t_h=oper_mp,
                                         fuente_horas=f_h),
                   decisiones=decisiones, alternativas=comparadas, sin_seleccion=sin_sel, avisos_seleccion=list(res.get("avisos") or []),
                   producto_t_h=producto_final(pl), violaciones=[m for _i, _c, m in viol],
                   supuestos=[dict(clave=s.clave, nombre=s.nombre, valor=s.valor, unidad=s.unidad, justificacion=s.justificacion)
                              for s in SUPUESTOS.values()] + ([dict(clave="simple", nombre="Balance simplificado", valor=0.0, unidad="—",
                                                                    justificacion=SIMPLE[tipo_planta_id]["nota"])] if simple else []),
                   limites=list(LIMITES) if simple else LIMITES[2:])
    if agar:
        informe.update(variante_agar=variante, distribucion_agar=distribucion)
    base = dict(ref._p) if ref is not None and isinstance(getattr(ref, "_p", None), dict) else {}
    base.update(sintesis=informe, tipo_planta=tipo_planta_id)
    if agar:
        base.update(variante_agar=variante, distribucion_agar=distribucion)
    elif variante:
        base.update(variante_tomate=variante, distribucion_tomate=distribucion)
    if desafio:
        base["desafio"] = desafio
    pl._p = base
    pl.precedencia = PR.tabla_plantas()
    return pl


def planta_en_blanco(tipo_planta_id: str | None = None, demanda=None, desafio: dict | None = None, variante: str | None = None) -> Planta:
    """Carta en blanco: planta sin equipos del rubro del tipo de planta (o «general» sin tipo), con el tipo, la demanda y el desafío
    en pl._p para que la planta automática y las demás pantallas los usen. Queda resuelta (sin equipos no hay nada que calcular).
    PAT 138: con «tomate», la variante (o la de la demanda) y la distribución de la llegada quedan en pl._p.
    PAT 144 a: con «agar», la variante de agar (la dada, la de la demanda o la del desafío de agar) queda en pl._p como variante_agar."""
    variante, distribucion = _variante(tipo_planta_id, demanda, variante)
    if tipo_planta_id == "agar" and not variante:                   # PAT 144 a: la del desafío de agar en curso
        variante, distribucion = _variante("agar", desafio if isinstance(desafio, dict) and desafio.get("tipo_planta") == "agar" else None, None)
    if tipo_planta_id:
        p = _pg().planta(tipo_planta_id)
        nombre = p["nombre"]
        if variante and tipo_planta_id == "agar":
            from ..catalogos import plantas_agar as PA
            nombre = PA.variante(variante)["nombre"]
        elif variante:
            from ..catalogos import plantas_tomate as PT
            nombre = PT.variante(variante)["nombre"]
        pl = Planta(f"Carta en blanco: {nombre}", p["rubro"])
    else:
        pl = Planta("Carta en blanco", "general")
    pdem = demanda if isinstance(demanda, str) else (_pg().planta(tipo_planta_id)["demanda_defecto"] if tipo_planta_id and demanda is None else None)
    if isinstance(demanda, dict):
        pdem = demanda.get("perfil") or demanda.get("perfil_demanda")
    pl._p = dict(tipo_planta=tipo_planta_id, demanda_perfil=pdem, carta_en_blanco=True)
    if variante and tipo_planta_id == "agar":
        pl._p.update(variante_agar=variante, distribucion_agar=distribucion)
    elif variante:
        pl._p.update(variante_tomate=variante, distribucion_tomate=distribucion)
    if desafio:
        pl._p["desafio"] = desafio
    pl.resolver()
    return pl


def _variante(tipo_planta_id, demanda, variante) -> tuple[str | None, str | None]:
    """(variante de tomate, distribución) de los argumentos: la variante dada o la que trae la demanda (resultado de
    demanda.llegada_tomate o desafío de la sesión). None en los demás tipos de planta. PAT 144 a: con «agar», la variante de
    catalogos/plantas_agar.py (resultado de demanda.llegada_agar o desafío de agar con «variante_agar»)."""
    if tipo_planta_id == "agar":
        from ..catalogos import plantas_agar as PA
        from .demanda import PERFIL_AGAR
        dist = None
        if isinstance(demanda, dict) and (demanda.get("perfil") == PERFIL_AGAR or demanda.get("variante_agar")):
            dist = demanda.get("distribucion") or demanda.get("distribucion_agar")
            variante = variante or demanda.get("variante") or demanda.get("variante_agar")
        if variante:
            variante = PA.variante(variante)["id"]
        return variante, dist
    if tipo_planta_id != "tomate":
        return None, None
    dist = None
    if isinstance(demanda, dict):
        dist = demanda.get("distribucion") or demanda.get("distribucion_tomate")
        variante = variante or demanda.get("variante") or demanda.get("variante_tomate")
    if variante:
        from ..catalogos import plantas_tomate as PT
        variante = PT.variante(variante)["id"]
    return variante, dist


def variante_de(pl) -> str | None:
    """Variante de tomate de una planta (PAT 138), o None."""
    p = getattr(pl, "_p", None)
    return p.get("variante_tomate") if isinstance(p, dict) else None


def variante_agar_de(pl) -> str | None:
    """Variante de agar de una planta (PAT 144 a), o None."""
    p = getattr(pl, "_p", None)
    return p.get("variante_agar") if isinstance(p, dict) else None


def agar_de_desafio(d: dict | None) -> tuple[str, str] | None:
    """PAT 144 a: (variante de agar, distribución de la llegada) de un desafío de agar de la pantalla Desafío, o None."""
    from ..catalogos import plantas_agar as PA
    from .demanda import DISTRIBUCIONES
    d = d or {}
    v, dist = d.get("variante_agar"), d.get("distribucion_agar")
    if d.get("tipo_planta") == "agar" and PA.es_variante(v) and dist in DISTRIBUCIONES:
        return v, dist
    return None


def es_carta_en_blanco(pl) -> bool:
    p = getattr(pl, "_p", None)
    return isinstance(p, dict) and bool(p.get("carta_en_blanco")) and not pl.equipos


def tipo_de(pl) -> str | None:
    """Tipo de planta de catalogos/plantas_genericas.py de una planta (guardado en _p o deducido del rubro)."""
    p = getattr(pl, "_p", None)
    if isinstance(p, dict) and p.get("tipo_planta"):
        return p["tipo_planta"]
    PG = _pg()
    return next((k for k, v in PG.PLANTAS.items() if v["rubro"] == getattr(pl, "rubro", None)), None)


def informe(pl) -> dict | None:
    p = getattr(pl, "_p", None)
    return p.get("sintesis") if isinstance(p, dict) else None


def misma_cadena(pl, tipo_planta_id: str) -> bool:
    """La planta tiene una operación por cada operación de la cadena del tipo (por tipo de equipo, sus alternativas o su versión
    simplificada), además de alimentación y servicios."""
    p = _pg().planta(tipo_planta_id)
    tipos = [e.tipo for e in pl.equipos.values()]
    for o in p["operaciones"]:
        ok = {o["tipo_equipo"], *(o.get("alternativas") or ()), *(o.get("equivalentes") or ())}   # PAT 143 b: equivalentes del agar
        ok |= {PR.PREFIJO_SIMPLE + t for t in list(ok)}
        if not any(t in ok for t in tipos):
            return False
    return True
