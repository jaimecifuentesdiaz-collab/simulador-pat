"""Animación 2D de la línea simulada (PAT 134, segunda ronda): como la vista del modelo de FlexSim, a partir de un resultado de
motor/linea_fluida.simular_linea.

Un solo componente streamlit.components.v1.html con SVG y JavaScript propios, sin bibliotecas externas ni internet: los equipos
son cajas en fila (en varias filas si no caben) pintadas con el color de su estado en el instante (COLOR_ESTADO de la línea),
entre ellos los tanques pulmón con su barra de nivel (como el indicador de nivel de la *Fluid Library*), flechas de flujo con
grosor según la tasa, reloj de la simulación, botones reproducir y pausa, velocidad (1×, 5×, 20× y 60×; 1× = 1 min simulado
por segundo) y barra de tiempo para saltar. Los datos van como JSON reducido: muestras de tiempo_h, niveles y tasas (como mucho
MAX_MUESTRAS) y los tramos de estado completos. Los números visibles van en formato chileno (coma decimal).

Uso: from . import s_animacion as AN; AN.mostrar(st.session_state.linea_resultado)."""
from __future__ import annotations
import json
import streamlit as st
import streamlit.components.v1 as components
from pat_sim.motor import linea_fluida as LF
from . import comun as C

ALTO = 500                  # alto fijo del componente (px); el ancho se adapta a la columna
MAX_MUESTRAS = 800          # muestras de niveles y tasas que viajan al navegador


def _r(v, d=4):
    try:
        return round(float(v), d)
    except (TypeError, ValueError):
        return None


def datos_animacion(res: dict, max_muestras: int = MAX_MUESTRAS) -> dict:
    """JSON reducido para la animación: equipos, tanques, estados con su color, muestras de tiempo, niveles, tasas y producción,
    y los tramos de estado de cada equipo como [inicio_h, fin_h, índice del estado]."""
    th = list(res.get("tiempo_h") or [])
    n = len(th); paso = max(1, -(-n // max(2, int(max_muestras))))
    idx = list(range(0, n, paso))
    if n and idx[-1] != n - 1:
        idx.append(n - 1)
    est_i = {s: j for j, s in enumerate(LF.ESTADOS)}
    eqs = [dict(id=e["id"], nombre=e["nombre"], cap=_r(e.get("capacidad_t_h")), carga=_r(e.get("carga_t_h"))) for e in res["equipos"]]
    tramos = {e["id"]: [] for e in eqs}
    for t in res.get("tramos") or []:
        if t["equipo"] in tramos:
            tramos[t["equipo"]].append([_r(t["inicio_h"], 5), _r(t["fin_h"], 5), est_i.get(t["estado"], 0)])
    tks = [dict(id=t["id"], antes=t["antes"], despues=t["despues"], cap=_r(t.get("capacidad_t")), anulado=bool(t.get("anulado")))
           for t in res.get("tanques") or []]
    niv = res.get("niveles") or {}; tas = res.get("tasas") or {}; pa = res.get("produccion_acumulada_t") or []
    H = float((res.get("parametros") or {}).get("horas") or (th[-1] if th else 0.0))
    return dict(horas=H, t=[_r(th[i], 4) for i in idx],
                niveles={k: [_r(v[i], 3) for i in idx] for k, v in niv.items()},
                tasas={k: [_r(v[i], 3) for i in idx] for k, v in tas.items()},
                prod=[_r(pa[i], 2) for i in idx] if len(pa) == n else [],
                equipos=eqs, tanques=tks, tramos=tramos,
                estados=[dict(clave=s, nombre=LF.NOMBRE_ESTADO[s], color=LF.COLOR_ESTADO[s]) for s in LF.ESTADOS])


_HTML = r"""<!doctype html><html lang="es-CL"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root{--fondo:#ffffff;--tinta:#1f1f1e;--tinta2:#5f5e5a;--borde:#dcdedb;--acento:#1b7a5a;--tanque:#eef2f4;--liquido:#2a78d6;--flecha:#7f8c92}
*{box-sizing:border-box}
html,body{margin:0;background:var(--fondo);color:var(--tinta);font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:13px}
#raiz{padding:6px 4px 0}
.barra{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:6px}
.reloj{font-variant-numeric:tabular-nums;font-weight:600;font-size:15px;min-width:220px}
.dato{color:var(--tinta2);font-variant-numeric:tabular-nums}
button,select{font:inherit;border:1px solid var(--borde);background:#f6f7f6;color:var(--tinta);border-radius:6px;padding:4px 10px;cursor:pointer}
button.activo{background:var(--acento);color:#fff;border-color:var(--acento)}
input[type=range]{flex:1 1 220px;min-width:160px;accent-color:var(--acento)}
#lienzo{width:100%;height:330px;display:block;border:1px solid var(--borde);border-radius:8px;background:#fbfcfb}
.leyenda{display:flex;flex-wrap:wrap;gap:12px;margin-top:6px;color:var(--tinta2)}
.leyenda span{display:inline-flex;align-items:center;gap:5px}.leyenda i{width:11px;height:11px;border-radius:2px;display:inline-block}
</style></head><body><div id="raiz">
<div class="barra">
  <button id="bPlay" title="Reproducir">&#9654; Reproducir</button>
  <button id="bPausa" title="Pausa">&#10074;&#10074; Pausa</button>
  <label class="dato">Velocidad <select id="vel" title="1× = 1 min de simulación por segundo">
    <option value="1">1×</option><option value="5">5×</option><option value="20" selected>20×</option><option value="60">60×</option></select></label>
  <span class="reloj" id="reloj">—</span>
  <span class="dato" id="prod"></span>
</div>
<div class="barra"><input type="range" id="tiempo" min="0" max="1" step="0.001" value="0" aria-label="Tiempo de la simulación"><span class="dato" id="fin"></span></div>
<svg id="lienzo" role="img" aria-label="Animación de la línea simulada" preserveAspectRatio="xMidYMin meet"></svg>
<div class="leyenda" id="leyenda"></div>
</div>
<script>
const D = __DATOS__;
const NS = "http://www.w3.org/2000/svg";
const svg = document.getElementById("lienzo");
const EQ = D.equipos, TK = D.tanques, T = D.t, H = D.horas || (T.length ? T[T.length - 1] : 1);
const tkPorAntes = {}; TK.forEach(k => tkPorAntes[k.antes] = k);
let ahora = 0, jugando = false, ultimo = null, dib = null;

function fmt(v, d) {                       // formato chileno: miles con punto y decimales con coma
  if (v === null || v === undefined || !isFinite(v)) return "—";
  const s = Math.abs(v).toFixed(d).split(".");
  s[0] = s[0].replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return (v < 0 && Number(Math.abs(v).toFixed(d)) !== 0 ? "-" : "") + s.join(",");
}
function el(tag, at, padre) { const e = document.createElementNS(NS, tag); for (const k in at) e.setAttribute(k, at[k]); if (padre) padre.appendChild(e); return e; }
function corto(s, n) { return s.length > n ? s.slice(0, n - 1) + "…" : s; }
function idxMuestra(t) {                   // primera muestra con tiempo >= t (búsqueda binaria)
  let a = 0, b = T.length - 1;
  if (!T.length) return 0;
  if (t <= T[0]) return 0;
  if (t >= T[b]) return b;
  while (b - a > 1) { const m = (a + b) >> 1; if (T[m] >= t) b = m; else a = m; }
  return b;
}
function nivel(id, t) {                    // interpolación lineal entre muestras
  const v = D.niveles[id]; if (!v || !v.length) return 0;
  const j = idxMuestra(t); if (j === 0) return v[0];
  const t0 = T[j - 1], t1 = T[j]; const f = t1 > t0 ? (t - t0) / (t1 - t0) : 1;
  return v[j - 1] + (v[j] - v[j - 1]) * Math.max(0, Math.min(1, f));
}
function tasa(id, t) {                     // tasa media del intervalo de muestra que contiene t
  const v = D.tasas[id]; if (!v || !v.length) return 0;
  return v[Math.max(1, idxMuestra(t))] ?? v[v.length - 1];
}
function produccion(t) {
  const v = D.prod; if (!v || !v.length) return null;
  const j = idxMuestra(t); if (j === 0) return v[0];
  const t0 = T[j - 1], t1 = T[j]; const f = t1 > t0 ? (t - t0) / (t1 - t0) : 1;
  return v[j - 1] + (v[j] - v[j - 1]) * Math.max(0, Math.min(1, f));
}
function estado(id, t) {                   // tramo que contiene t (búsqueda binaria)
  const tr = D.tramos[id]; if (!tr || !tr.length) return 0;
  let a = 0, b = tr.length - 1;
  if (t >= tr[b][0]) return tr[b][2];
  while (a < b) { const m = (a + b) >> 1; if (tr[m][1] <= t) a = m + 1; else b = m; }
  return tr[a][2];
}
const maxTasa = {};
EQ.forEach(e => { const v = D.tasas[e.id] || []; maxTasa[e.id] = Math.max(e.cap || 0, e.carga || 0, ...v.map(x => x || 0), 1e-9); });

// --------------------------------------------------------------- dibujo (se rehace al cambiar el ancho)
const CH = 64, TW = 34, TH = 56, FILA = 170;
let CW = 132, GAP = 112;
function armar() {
  const ancho = Math.max(320, svg.clientWidth || svg.parentNode.clientWidth || 800);
  if (ancho < 640) { CW = 112; GAP = 76; } else { CW = 132; GAP = 112; }     // pantallas angostas: cajas más chicas
  const por = Math.max(1, Math.floor((ancho - 40 + GAP) / (CW + GAP)));
  const filas = Math.ceil(EQ.length / por);
  const usado = Math.min(EQ.length, por) * (CW + GAP) - GAP;
  const x0 = Math.max(20, (ancho - usado) / 2);
  const alto = 30 + filas * FILA;
  svg.setAttribute("viewBox", `0 0 ${ancho} ${alto}`);
  while (svg.firstChild) svg.removeChild(svg.firstChild);
  const defs = el("defs", {}, svg);
  const mk = el("marker", {id: "punta", viewBox: "0 0 10 10", refX: "8", refY: "5", markerWidth: "4", markerHeight: "4", orient: "auto-start-reverse"}, defs);
  el("path", {d: "M0 0L10 5L0 10z", fill: "#7f8c92"}, mk);
  const capaF = el("g", {}, svg), capaE = el("g", {}, svg);
  const pos = EQ.map((e, i) => { const f = Math.floor(i / por), c = i % por; return {x: x0 + c * (CW + GAP), y: 26 + f * FILA, f: f}; });
  const cajas = {}, flechas = [], tanques = {};
  EQ.forEach((e, i) => {
    const p = pos[i], g = el("g", {}, capaE);
    const r = el("rect", {x: p.x, y: p.y, width: CW, height: CH, rx: 8, fill: "#ccc", stroke: "#2b2b2b", "stroke-opacity": 0.25}, g);
    const tt = el("title", {}, r); tt.textContent = `${e.id} ${e.nombre}`;
    const t1 = el("text", {x: p.x + 8, y: p.y + 17, "font-size": 12, "font-weight": 600, fill: "#fff"}, g); t1.textContent = corto(`${e.id} · ${e.nombre}`, Math.floor((CW - 12) / 6.3));
    const t2 = el("text", {x: p.x + 8, y: p.y + 35, "font-size": 11, fill: "#fff"}, g);
    const t3 = el("text", {x: p.x + 8, y: p.y + 53, "font-size": 11, fill: "#fff", "font-variant-numeric": "tabular-nums"}, g);
    cajas[e.id] = {r, t2, t3};
    if (i === EQ.length - 1) {             // salida de producto
      const a = el("path", {d: `M${p.x + CW} ${p.y + CH / 2}h34`, stroke: "#7f8c92", fill: "none", "marker-end": "url(#punta)"}, capaF);
      flechas.push({p: a, id: e.id});
      return;
    }
    const q = pos[i + 1], k = tkPorAntes[e.id];
    const yC = p.y + CH / 2;
    if (q.f === p.f) {                     // misma fila: caja, tanque, caja
      const xm = p.x + CW + GAP / 2;
      if (k && !k.anulado) {
        const a1 = el("path", {d: `M${p.x + CW} ${yC}H${xm - TW / 2 - 3}`, stroke: "#7f8c92", fill: "none", "marker-end": "url(#punta)"}, capaF);
        const a2 = el("path", {d: `M${xm + TW / 2} ${yC}H${q.x - 3}`, stroke: "#7f8c92", fill: "none", "marker-end": "url(#punta)"}, capaF);
        flechas.push({p: a1, id: e.id}, {p: a2, id: EQ[i + 1].id});
        tanques[k.id] = tanque(capaE, k, xm - TW / 2, yC - TH / 2);
      } else {
        const a1 = el("path", {d: `M${p.x + CW} ${yC}H${q.x - 3}`, stroke: "#7f8c92", fill: "none", "marker-end": "url(#punta)"}, capaF);
        flechas.push({p: a1, id: e.id});
        if (k) { const tx = el("text", {x: xm, y: yC - 8, "text-anchor": "middle", "font-size": 10, fill: "#5f5e5a"}, capaE); tx.textContent = "directo"; }
      }
    } else {                               // cambio de fila: baja por la derecha, cruza y entra a la caja siguiente por la izquierda
      const xd = p.x + CW + 26, yb = p.y + CH + (FILA - CH) / 2, xi = q.x - 26, yq = q.y + CH / 2;
      if (k && !k.anulado) {
        const xt = x0 + Math.floor((por - 1) / 2) * (CW + GAP) + CW / 2;     // bajo una caja, lejos de los rótulos de la fila
        
        const a1 = el("path", {d: `M${p.x + CW} ${yC}H${xd}V${yb}H${xt + TW / 2 + 3}`, stroke: "#7f8c92", fill: "none", "marker-end": "url(#punta)"}, capaF);
        const a2 = el("path", {d: `M${xt - TW / 2} ${yb}H${xi}V${yq}H${q.x - 3}`, stroke: "#7f8c92", fill: "none", "marker-end": "url(#punta)"}, capaF);
        flechas.push({p: a1, id: e.id}, {p: a2, id: EQ[i + 1].id});
        tanques[k.id] = tanque(capaE, k, xt - TW / 2, yb - TH / 2, false);
      } else {
        const a1 = el("path", {d: `M${p.x + CW} ${yC}H${xd}V${yb}H${xi}V${yq}H${q.x - 3}`, stroke: "#7f8c92", fill: "none", "marker-end": "url(#punta)"}, capaF);
        flechas.push({p: a1, id: e.id});
      }
    }
  });
  dib = {cajas, flechas, tanques};
  pintar();
}
function tanque(capa, k, x, y, lado) {
  const g = el("g", {}, capa);
  const c = el("rect", {x, y, width: TW, height: TH, rx: 5, fill: "#eef2f4", stroke: "#36586c", "stroke-width": 1.2}, g);
  const tt = el("title", {}, c); tt.textContent = `Tanque ${k.id}: capacidad ${fmt(k.cap, 2)} t`;
  const liq = el("rect", {x: x + 3, y: y + TH - 3, width: TW - 6, height: 0, rx: 2, fill: "#2a78d6"}, g);
  // rótulos arriba y abajo; en el tanque del cambio de fila, al lado (la flecha pasa por arriba y por abajo no hay espacio)
  const t1 = el("text", lado ? {x: x + TW + 6, y: y + TH / 2 - 10, "font-size": 10, fill: "#1f1f1e", "font-variant-numeric": "tabular-nums"}
                             : {x: x + TW / 2, y: y - 6, "text-anchor": "middle", "font-size": 10, fill: "#1f1f1e", "font-variant-numeric": "tabular-nums"}, g);
  const t2 = el("text", lado ? {x: x + TW + 6, y: y + TH / 2 + 22, "font-size": 10, fill: "#5f5e5a", "font-variant-numeric": "tabular-nums"}
                             : {x: x + TW / 2, y: y + TH + 13, "text-anchor": "middle", "font-size": 10, fill: "#5f5e5a", "font-variant-numeric": "tabular-nums"}, g);
  return {liq, t1, t2, x, y, cap: k.cap || 0};
}
function pintar() {
  if (!dib) return;
  const t = ahora;
  EQ.forEach(e => {
    const s = D.estados[estado(e.id, t)] || D.estados[0], c = dib.cajas[e.id], q = tasa(e.id, t);
    c.r.setAttribute("fill", s.color); c.t2.textContent = s.nombre; c.t3.textContent = `${fmt(q, 1)} t/h`;
  });
  dib.flechas.forEach(f => {
    const q = tasa(f.id, t), w = 1 + 9 * Math.max(0, Math.min(1, q / maxTasa[f.id]));
    f.p.setAttribute("stroke-width", w.toFixed(2));
    f.p.setAttribute("stroke-dasharray", q > 1e-9 ? "" : "4 4");
  });
  TK.forEach(k => {
    const d = dib.tanques[k.id]; if (!d) return;
    const v = nivel(k.id, t), f = d.cap > 0 ? Math.max(0, Math.min(1, v / d.cap)) : 0, h = (TH - 6) * f;
    d.liq.setAttribute("y", (d.y + TH - 3 - h).toFixed(2)); d.liq.setAttribute("height", h.toFixed(2));
    d.t1.textContent = `${fmt(v, 1)} t`; d.t2.textContent = `${fmt(100 * f, 0)} %`;
  });
  const dia = Math.floor(t / 24) + 1, hh = t - 24 * (dia - 1), h = Math.floor(hh + 1e-9), m = Math.floor((hh - h) * 60 + 1e-6);
  document.getElementById("reloj").textContent = `Día ${dia}, ${String(h).padStart(2, "0")}:${String(Math.min(59, m)).padStart(2, "0")} · t = ${fmt(t, 2)} h`;
  const p = produccion(t);
  document.getElementById("prod").textContent = p === null ? "" : `Producción acumulada ${fmt(p, 1)} t`;
  document.getElementById("tiempo").value = t;
}
function cuadro(ts) {
  if (!jugando) return;
  if (ultimo !== null) {
    const v = Number(document.getElementById("vel").value) || 1;
    ahora = Math.min(H, ahora + (ts - ultimo) / 1000 * v / 60);   // 1× = 1 min de simulación por segundo
    if (ahora >= H) { jugando = false; marcar(); }
  }
  ultimo = ts; pintar();
  if (jugando) requestAnimationFrame(cuadro);
}
function marcar() {
  document.getElementById("bPlay").classList.toggle("activo", jugando);
  document.getElementById("bPausa").classList.toggle("activo", !jugando);
}
document.getElementById("bPlay").onclick = () => { if (ahora >= H) ahora = 0; jugando = true; ultimo = null; marcar(); requestAnimationFrame(cuadro); };
document.getElementById("bPausa").onclick = () => { jugando = false; marcar(); };
const rango = document.getElementById("tiempo");
rango.max = H; rango.step = Math.max(H / 2000, 1 / 60);
rango.oninput = () => { ahora = Number(rango.value); ultimo = null; pintar(); };
document.getElementById("fin").textContent = `${fmt(H, 1)} h`;
const ley = document.getElementById("leyenda");
D.estados.forEach(s => { const sp = document.createElement("span"); const i = document.createElement("i"); i.style.background = s.color; sp.appendChild(i); sp.appendChild(document.createTextNode(s.nombre)); ley.appendChild(sp); });
const sp = document.createElement("span"); sp.textContent = "Flechas: grosor según la tasa; punteadas sin flujo. Tanques: nivel en t y % de su capacidad."; ley.appendChild(sp);
let anchoPrevio = 0;
function revisar() { const w = svg.clientWidth; if (w && Math.abs(w - anchoPrevio) > 4) { anchoPrevio = w; armar(); } }
if (window.ResizeObserver) new ResizeObserver(revisar).observe(svg); else window.addEventListener("resize", revisar);
armar(); marcar();
</script></body></html>"""


def html_animacion(res: dict, max_muestras: int = MAX_MUESTRAS) -> str:
    """Documento HTML completo de la animación (SVG y JavaScript propios) con los datos del resultado incrustados."""
    js = json.dumps(datos_animacion(res, max_muestras), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    js = js.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return _HTML.replace("__DATOS__", js)


def mostrar(resultado):
    """Animación 2D de la línea a partir de un resultado de simular_linea (st.session_state.linea_resultado)."""
    if not isinstance(resultado, dict) or not resultado.get("equipos") or not resultado.get("tramos"):
        st.info("Simule la línea para ver su animación.")
        return
    try:
        doc = html_animacion(resultado)
    except (KeyError, TypeError, ValueError) as e:
        st.warning(f"No se pudo armar la animación: {e}")
        return
    html = getattr(components, "html", None)
    if html is None:            # solo el sustituto de Streamlit del banco de pruebas no trae components.html
        st.html(doc)
    else:
        html(doc, height=ALTO, scrolling=False)
    C.ayuda("Vista 2D como la del modelo de FlexSim: cada caja es un equipo con el color de su estado en el instante; entre ellas, los "   # PAT 134: ayuda «?»
            "tanques pulmón con su nivel. Velocidad 1× = 1 min de simulación por segundo (60× = 1 h por segundo). Los niveles y las "
            f"tasas son las muestras de la simulación (cada {C.fmt((resultado.get('parametros') or {}).get('muestra_min'), 0)} min) "
            "y los estados, los tramos con su hora exacta.")
