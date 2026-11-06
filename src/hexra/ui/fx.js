"use strict";
/* Visual effects only: nothing here touches settings or the engine. They switch off with the ✦ button or with the OS "reduce motion" setting. */
(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const body = document.body;
  let fxOn = true;
  try { fxOn = localStorage.getItem("hexra-fx") !== "0"; } catch (e) {}
  const fxBtn = $("#fx");
  function applyFx() { body.classList.toggle("fx-off", !fxOn || reduce); if (fxBtn) fxBtn.setAttribute("aria-pressed", fxOn && !reduce ? "true" : "false"); }
  applyFx();
  if (fxBtn) fxBtn.addEventListener("click", () => { fxOn = !fxOn; try { localStorage.setItem("hexra-fx", fxOn ? "1" : "0"); } catch (e) {} applyFx(); if (fxOn) kick(); });

  // ---- perspective grid floor + drifting light, on a half-resolution canvas at about 24 frames a second
  const cv = $("#bg"), g = cv.getContext("2d");
  const S = 0.5;
  let W = 0, H = 0, phase = 0, last = 0, raf = 0, px = 0.5, py = 0.5, tx = 0.5, ty = 0.5;
  const stars = Array.from({ length: 90 }, () => ({ x: Math.random(), y: Math.random() * 0.56, r: Math.random() * 1.3 + 0.3, s: Math.random() * 6.28, v: Math.random() * 0.00004 + 0.00001 }));
  const orbs = [{ c: "138,125,255", x: 0.15, y: 0.3, r: 0.42, p: 0 }, { c: "63,224,255", x: 0.85, y: 0.22, r: 0.36, p: 2 }, { c: "255,93,224", x: 0.6, y: 0.7, r: 0.4, p: 4 }];
  function resize() { W = cv.width = Math.max(2, Math.round(innerWidth * S)); H = cv.height = Math.max(2, Math.round(innerHeight * S)); }
  addEventListener("resize", () => { resize(); if (!raf) draw(performance.now(), true); });
  resize();
  document.addEventListener("pointermove", e => { tx = e.clientX / innerWidth; ty = e.clientY / innerHeight; }, { passive: true });

  function draw(now, still) {
    px += (tx - px) * 0.05; py += (ty - py) * 0.05;
    g.clearRect(0, 0, W, H);
    const hy = H * (0.56 + (py - 0.5) * 0.03), vx = W * (0.5 + (px - 0.5) * 0.12);
    // soft moving lights
    for (const o of orbs) {
      const ox = (o.x + Math.sin(now / 9000 + o.p) * 0.05) * W, oy = (o.y + Math.cos(now / 11000 + o.p) * 0.04) * H, r = o.r * Math.max(W, H);
      const gr = g.createRadialGradient(ox, oy, 0, ox, oy, r);
      gr.addColorStop(0, `rgba(${o.c},0.16)`); gr.addColorStop(1, `rgba(${o.c},0)`);
      g.fillStyle = gr; g.fillRect(0, 0, W, H);
    }
    // stars
    for (const s of stars) {
      const a = 0.35 + 0.65 * Math.abs(Math.sin(now * s.v * 40 + s.s));
      g.fillStyle = `rgba(190,215,255,${a * 0.7})`;
      g.fillRect(s.x * W, s.y * H, s.r, s.r);
    }
    // the floor: lines that rush toward you
    const near = (W / 5.2);
    g.lineWidth = 1;
    for (let i = -14; i <= 14; i++) {
      const a = Math.max(0.05, 0.32 - Math.abs(i) * 0.016);
      const gr = g.createLinearGradient(0, hy, 0, H);
      gr.addColorStop(0, "rgba(63,224,255,0)"); gr.addColorStop(1, `rgba(138,125,255,${a})`);
      g.strokeStyle = gr;
      g.beginPath(); g.moveTo(vx + i * near * 0.06, hy); g.lineTo(vx + i * near, H); g.stroke();
    }
    const K = 16;
    for (let k = 0; k < K; k++) {
      const z = ((k + phase) % K) / K, y = hy + (H - hy) * Math.pow(z, 2.3);
      g.strokeStyle = `rgba(63,224,255,${0.04 + z * 0.3})`;
      g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke();
    }
    // horizon glow
    const hg = g.createLinearGradient(0, hy - 24, 0, hy + 24);
    hg.addColorStop(0, "rgba(255,93,224,0)"); hg.addColorStop(0.5, "rgba(138,125,255,0.45)"); hg.addColorStop(1, "rgba(63,224,255,0)");
    g.fillStyle = hg; g.fillRect(0, hy - 24, W, 48);
  }
  function loop(now) {
    raf = 0;
    if (body.classList.contains("fx-off")) return;
    if (!document.hidden && now - last >= 41) { phase += (now - last) * 0.0006; last = now; draw(now); }
    raf = requestAnimationFrame(loop);
  }
  function kick() { if (!raf && !body.classList.contains("fx-off")) raf = requestAnimationFrame(loop); }
  document.addEventListener("visibilitychange", kick);
  if (reduce) draw(0, true); else kick();

  // ---- the camera tilts toward the pointer, and cards catch the light
  const stage = $(".stage"), view = $(".cam-view");
  if (stage && view) {
    stage.addEventListener("pointermove", e => {
      if (body.classList.contains("fx-off")) return;
      const r = stage.getBoundingClientRect(), x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
      view.style.setProperty("--ry", (3 + x * 8).toFixed(2) + "deg"); view.style.setProperty("--rx", (-y * 6).toFixed(2) + "deg");
    });
    stage.addEventListener("pointerleave", () => { view.style.setProperty("--ry", "3deg"); view.style.setProperty("--rx", "0deg"); });
    const cam = $("#cam");
    const live = () => stage.classList.toggle("live", !cam.hidden);
    new MutationObserver(live).observe(cam, { attributes: true, attributeFilter: ["hidden"] });
    live();
  }
  document.addEventListener("pointermove", e => {
    const el = e.target.closest && e.target.closest(".card,.preset,.camtile");
    if (!el) return;
    const r = el.getBoundingClientRect();
    el.style.setProperty("--mx", (e.clientX - r.left) + "px"); el.style.setProperty("--my", (e.clientY - r.top) + "px");
  }, { passive: true });

  // ---- sliders: fill the track up to the thumb
  const paint = r => { const min = +r.min || 0, max = +r.max || 100; r.style.setProperty("--p", (((+r.value) - min) / ((max - min) || 1) * 100).toFixed(1) + "%"); };
  const paintAll = () => document.querySelectorAll("input[type=range]").forEach(paint);
  document.addEventListener("input", e => { if (e.target.type === "range") paint(e.target); });
  const main = $("#main");
  if (main) new MutationObserver(paintAll).observe(main, { childList: true, subtree: true });
  paintAll();
})();
