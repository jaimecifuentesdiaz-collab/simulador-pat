// PAT 135 (T15): interacción de la vista isométrica (componente de Streamlit, apiVersion 1, por postMessage). Sin internet.
"use strict";
(function () {
  const $ = id => document.getElementById(id);
  let D = null, rot = 0, vb0 = null, vb = null, drag = null, fijo = null, altoPrevio = 0, firma = "";

  function aST(type, data) { window.parent.postMessage(Object.assign({isStreamlitMessage: true, type}, data || {}), "*"); }
  function fmt(v, d) {
    if (v === null || v === undefined || isNaN(v)) return "—";
    return new Intl.NumberFormat("es-CL", {minimumFractionDigits: d, maximumFractionDigits: d}).format(v);
  }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c])); }
  const NOMBRE_ROT = {0: "Vista desde el sureste", 90: "Vista desde el noreste", 180: "Vista desde el noroeste", 270: "Vista desde el suroeste"};

  window.addEventListener("message", e => {
    const m = e.data;
    if (m && m.type === "streamlit:render" && m.args && m.args.datos) recibir(m.args.datos);
  });

  function recibir(datos) {
    const f = JSON.stringify(Object.keys(datos.vistas || {})) + (datos.firma || "");
    const primera = D === null;
    D = datos;
    if (primera) rot = Number(datos.rot || 0);
    if (primera || f !== firma) { firma = f; pintar(true); }
    altura();
  }

  function svgEl() { return $("vista").querySelector("svg"); }

  function pintar(ajustarVista) {
    if (!D) return;
    $("vista").style.height = (D.alto || 620) + "px";
    $("vista").innerHTML = (D.vistas || {})[String(rot)] || "<p style='padding:10px'>Sin vista</p>";
    const s = svgEl();
    if (s) {
      const v = (s.getAttribute("viewBox") || "0 0 1000 600").split(/[\s,]+/).map(Number);
      vb0 = v.slice();
      if (ajustarVista || !vb) vb = v.slice();
      s.removeAttribute("width"); s.removeAttribute("height");
      s.setAttribute("preserveAspectRatio", "xMidYMid meet");
      aplicarVB();
      eventos(s);
    }
    for (const b of document.querySelectorAll("button[data-rot]")) b.classList.toggle("activo", Number(b.dataset.rot) === rot);
    fijo = null; resaltar(null); mostrar(null);
  }

  function aplicarVB() { const s = svgEl(); if (s && vb) s.setAttribute("viewBox", vb.map(x => x.toFixed(1)).join(" ")); }

  function puntoSVG(ev) {
    const s = svgEl(), r = s.getBoundingClientRect();
    const k = Math.max(vb[2] / r.width, vb[3] / r.height);
    const ox = (r.width * k - vb[2]) / 2, oy = (r.height * k - vb[3]) / 2;
    return [vb[0] - ox + (ev.clientX - r.left) * k, vb[1] - oy + (ev.clientY - r.top) * k, k];
  }

  function zoom(f, cx, cy) {
    if (!vb) return;
    if (cx === undefined) { cx = vb[0] + vb[2] / 2; cy = vb[1] + vb[3] / 2; }
    const w = Math.min(vb0[2] * 4, Math.max(vb0[2] / 12, vb[2] / f)), h = w * vb[3] / vb[2];
    vb = [cx - (cx - vb[0]) * w / vb[2], cy - (cy - vb[1]) * h / vb[3], w, h];
    aplicarVB();
  }

  // ------------------------------------------------------------ resaltar un equipo o una cañería y sus conexiones
  function objetivo(el) {
    const g = el && el.closest ? el.closest(".eq,.ccm,.co,.ca,.rot") : null;
    if (!g) return null;
    if (g.classList.contains("co") || g.classList.contains("ca")) return {t: g.classList.contains("co") ? "co" : "ca", id: g.dataset.c, o: g.dataset.o, d: g.dataset.d};
    return {t: "eq", id: g.dataset.id};
  }
  function resaltar(obj) {
    const s = svgEl();
    if (!s) return;
    for (const e of s.querySelectorAll(".foco")) e.classList.remove("foco");
    s.classList.toggle("atenuado", !!obj);
    if (!obj) return;
    const ids = new Set(), sel = [];
    if (obj.t === "eq") {
      ids.add(obj.id);
      for (const e of s.querySelectorAll(".co,.ca")) if (e.dataset.o === obj.id || e.dataset.d === obj.id) { sel.push(e); ids.add(e.dataset.o); ids.add(e.dataset.d); }
    } else {
      ids.add(obj.o); ids.add(obj.d);
      for (const e of s.querySelectorAll(".co,.ca")) if (e.dataset.c === obj.id) sel.push(e);
    }
    for (const e of s.querySelectorAll(".eq,.ccm,.rot")) if (ids.has(e.dataset.id)) e.classList.add("foco");
    for (const e of sel) e.classList.add("foco");
  }

  function fila(t, v) { return `<tr><td class="suave">${esc(t)}</td><td class="n">${v}</td></tr>`; }
  function mostrar(obj) {
    const P = $("panel"), I = (D && D.info) || {};
    if (!obj) {
      P.innerHTML = `<h4>${esc(NOMBRE_ROT[rot] || "")}</h4><p class="suave">Pase el mouse por un equipo, una cañería o un alimentador para ver sus datos y resaltar sus conexiones. Haga clic para dejarlo fijo y otra vez para soltarlo.</p>`;
      return;
    }
    if (obj.t === "eq") {
      const e = (I.equipos || {})[obj.id];
      if (!e) { P.innerHTML = `<h4>${esc(obj.id)}</h4>`; return; }
      let h = `<h4>${esc(obj.id)} · ${esc(e.nombre)}</h4><table>`;
      h += fila("Familia", esc(e.familia));
      h += fila("Largo × ancho × alto", `${fmt(e.largo, 1)} × ${fmt(e.ancho, 1)} × ${fmt(e.alto, 1)} m`);
      h += fila("Centro (x; y)", `${fmt(e.x, 1)}; ${fmt(e.y, 1)} m`);
      h += fila("Rotación", `${fmt(e.rot, 0)}°`);
      if (e.P_kW != null) h += fila(obj.id === "CCM" ? "Potencia conectada" : "Potencia eléctrica", `${fmt(e.P_kW, 1)} kW`);
      if (e.alimentador) h += fila("Alimentador", `${esc(e.alimentador)}<br>${esc(e.conductor || "")}`);
      h += fila("Conexiones", esc((e.conexiones || []).join(", ") || "—"));
      P.innerHTML = h + "</table>";
      return;
    }
    if (obj.t === "co") {
      const c = (I.corrientes || {})[obj.id] || {};
      let h = `<h4>Corriente ${esc(obj.id)}</h4><table>`;
      h += fila("Tramo", `${esc(c.origen || obj.o)} → ${esc(c.destino || obj.d)}`);
      h += fila("Fluido", esc(c.tipo_txt || c.tipo || ""));
      h += fila("Medio", esc(c.medio || ""));
      h += fila("Diámetro interno", c.D_mm != null ? `${fmt(c.D_mm, 0)} mm` : "—");
      h += fila("Longitud", `${fmt(c.largo_m, 1)} m`);
      P.innerHTML = h + "</table>";
      return;
    }
    const c = (I.cables || {})[obj.id] || {};
    let h = `<h4>Alimentador ${esc(obj.id)}</h4><table>`;
    h += fila("Tramo", `CCM → ${esc(c.destino || obj.d)}`);
    h += fila("Carga", esc(c.nombre || ""));
    h += fila("Potencia", `${fmt(c.P_kW, 1)} kW`);
    h += fila("Corriente", `${fmt(c.I_A, 1)} A`);
    h += fila("Conductor", esc(c.conductor || ""));
    h += fila("Longitud", `${fmt(c.largo_m, 1)} m`);
    h += fila("Caída de tensión", `${fmt(c.dU_pct, 2)} %`);
    P.innerHTML = h + "</table>";
  }

  function eventos(s) {
    s.addEventListener("mouseover", ev => { if (drag && drag.movio) return; if (fijo) return; const o = objetivo(ev.target); resaltar(o); mostrar(o); });
    s.addEventListener("mouseleave", () => { if (!fijo) { resaltar(null); mostrar(null); } });
    s.addEventListener("pointerdown", ev => {
      const [x, y] = puntoSVG(ev);
      drag = {x, y, vb: vb.slice(), cx: ev.clientX, cy: ev.clientY, movio: false};
      s.setPointerCapture(ev.pointerId);
    });
    s.addEventListener("pointermove", ev => {
      if (!drag) return;
      if (!drag.movio && Math.hypot(ev.clientX - drag.cx, ev.clientY - drag.cy) < 4) return;
      drag.movio = true; s.classList.add("arrastrando");
      const r = s.getBoundingClientRect(), k = Math.max(drag.vb[2] / r.width, drag.vb[3] / r.height);
      vb = [drag.vb[0] - (ev.clientX - drag.cx) * k, drag.vb[1] - (ev.clientY - drag.cy) * k, drag.vb[2], drag.vb[3]];
      aplicarVB();
    });
    const soltar = ev => {
      if (drag && !drag.movio) {
        const o = objetivo(document.elementFromPoint(ev.clientX, ev.clientY));
        const igual = o && fijo && o.t === fijo.t && o.id === fijo.id;
        fijo = (o && !igual) ? o : null;
        resaltar(fijo || o); mostrar(fijo || o);
      }
      drag = null; s.classList.remove("arrastrando");
    };
    s.addEventListener("pointerup", soltar);
    s.addEventListener("pointercancel", () => { drag = null; s.classList.remove("arrastrando"); });
    s.addEventListener("wheel", ev => { ev.preventDefault(); const [x, y] = puntoSVG(ev); zoom(ev.deltaY < 0 ? 1.15 : 1 / 1.15, x, y); }, {passive: false});
  }

  function girar(n) { rot = ((rot + n) % 360 + 360) % 360; pintar(true); }
  $("g-izq").onclick = () => girar(-90);
  $("g-der").onclick = () => girar(90);
  for (const b of document.querySelectorAll("button[data-rot]")) b.onclick = () => { rot = Number(b.dataset.rot); pintar(true); };
  $("z-mas").onclick = () => zoom(1.25);
  $("z-menos").onclick = () => zoom(0.8);
  $("ajustar").onclick = () => { vb = vb0.slice(); aplicarVB(); };
  $("descargar").onclick = () => {
    const txt = (D && D.vistas || {})[String(rot)];
    if (!txt) return;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([txt], {type: "image/svg+xml"}));
    a.download = `Layout_isometrica_${rot}.svg`;
    document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  };

  function altura() {
    const h = Math.ceil(document.body.getBoundingClientRect().height) + 6;
    if (Math.abs(h - altoPrevio) > 2) { altoPrevio = h; aST("streamlit:setFrameHeight", {height: h}); }
  }
  new ResizeObserver(() => altura()).observe(document.body);
  aST("streamlit:componentReady", {apiVersion: 1});
})();
