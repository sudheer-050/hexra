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

  // ---- hyperdrive: a starfield rushing past (after the 21st.dev "Hyperdrive" hero), on a half-resolution canvas at about 24 frames a second
  const cv = $("#bg"), g = cv.getContext("2d");
  const S = 0.5, R = Math.random, TAU = Math.PI * 2;
  let W = 0, H = 0, last = 0, raf = 0, speed = 2, aim = 2, px = 0.5, py = 0.5, tx = 0.5, ty = 0.5;
  const NUM = 900;
  const stars = [];
  const orbs = [{ c: "70,140,255", x: 0.14, y: 0.3, r: 0.46, p: 0 }, { c: "90,200,255", x: 0.86, y: 0.2, r: 0.4, p: 2 }, { c: "60,110,230", x: 0.55, y: 0.78, r: 0.46, p: 4 }, { c: "110,170,255", x: 0.4, y: 0.12, r: 0.3, p: 1 }];
  function place(s, anywhere) {
    s.x = (R() - 0.5) * W; s.y = (R() - 0.5) * H;
    s.z = anywhere ? R() * W : W;                 // distance: far stars start at the back and fly toward you
    s.pz = s.z;
  }
  function resize() {
    W = cv.width = Math.max(2, Math.round(innerWidth * S)); H = cv.height = Math.max(2, Math.round(innerHeight * S));
    stars.length = 0;
    for (let i = 0; i < NUM; i++) { const s = {}; place(s, true); stars.push(s); }
  }
  addEventListener("resize", () => { resize(); if (!raf) draw(performance.now(), true); });
  resize();
  document.addEventListener("pointermove", e => {
    tx = e.clientX / innerWidth; ty = e.clientY / innerHeight;
    aim = 2 + (1 - Math.abs(e.clientX - innerWidth / 2) / (innerWidth / 2)) * 6.5;          // the closer to the middle, the faster you fly
  }, { passive: true });

  function draw(now, still) {
    const dt = still ? 0 : Math.min(0.2, (now - (draw.t || now)) / 1000); draw.t = now;
    px += (tx - px) * 0.05; py += (ty - py) * 0.05;
    speed += (aim - speed) * Math.min(1, dt * 2);
    g.clearRect(0, 0, W, H);
    // soft coloured lights: these are what shows through the glass
    for (const o of orbs) {
      const ox = (o.x + Math.sin(now / 9000 + o.p) * 0.06) * W, oy = (o.y + Math.cos(now / 11000 + o.p) * 0.05) * H, r = o.r * Math.max(W, H);
      const gr = g.createRadialGradient(ox, oy, 0, ox, oy, r);
      gr.addColorStop(0, `rgba(${o.c},0.24)`); gr.addColorStop(1, `rgba(${o.c},0)`);
      g.fillStyle = gr; g.fillRect(0, 0, W, H);
    }
    // the stars: each streaks from where it was to where it is now, away from the vanishing point (which follows your pointer a little)
    const cx = W / 2 + (px - 0.5) * W * 0.12, cy = H / 2 + (py - 0.5) * H * 0.12;
    g.lineCap = "round";
    for (const s of stars) {
      if (dt > 0) { s.z -= speed * 60 * S * dt; if (s.z < 1) place(s, false); }
      const k = (still ? 1.02 : 1);
      const sx = (s.x / s.z) * W / 2 + cx, sy = (s.y / s.z) * H / 2 + cy;
      const pz = still ? s.z * k : s.pz;
      const ox = (s.x / pz) * W / 2 + cx, oy = (s.y / pz) * H / 2 + cy;
      s.pz = s.z;
      if (sx < -20 || sx > W + 20 || sy < -20 || sy > H + 20) { if (dt > 0) place(s, false); continue; }
      const depth = 1 - s.z / W;                                           // 0 far, 1 near
      g.strokeStyle = `rgba(225,238,255,${Math.min(1, 0.18 + depth * 0.95)})`;
      g.lineWidth = Math.max(0.4, depth * 2.4);
      g.beginPath(); g.moveTo(ox, oy); g.lineTo(sx, sy); g.stroke();
    }
  }
  function loop(now) {
    raf = 0;
    if (body.classList.contains("fx-off")) return;
    if (!document.hidden && now - last >= 41) { last = now; draw(now); }
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
      view.style.setProperty("--ry", (2 + x * 5).toFixed(2) + "deg"); view.style.setProperty("--rx", (-y * 3).toFixed(2) + "deg");
    });
    stage.addEventListener("pointerleave", () => { view.style.setProperty("--ry", "2deg"); view.style.setProperty("--rx", "0deg"); });
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
