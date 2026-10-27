/* Golf Cornhole's campsite: a grassy clearing in the woods with a campfire, tents, a picnic
 * table and string lights. The layout comes from the server (cornhole.campsite) in yards,
 * already scaled with the board; camp.k is yards per real metre, for the sizes of the small
 * things drawn here, so everything matches the board's scale.
 */
import * as THREE from "three";

const toV = (p, out) => (out || new THREE.Vector3()).set(p[1], p[2] || 0, -p[0]);

function canvasTexture(w, h, draw, srgb = true) {
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  draw(c.getContext("2d"), w, h);
  const t = new THREE.CanvasTexture(c);
  if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

// the same camp every time it is built
function seeded(seed) {
  let s = seed >>> 0;
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
}

// draw something near an edge on the far side too, so a repeating texture has no seams
function wrapped(w, h, x, y, m, fn) {
  const xs = [x], ys = [y];
  if (x < m) xs.push(x + w); else if (x > w - m) xs.push(x - w);
  if (y < m) ys.push(y + h); else if (y > h - m) ys.push(y - h);
  xs.forEach((a) => ys.forEach((b) => fn(a, b)));
}

/* ---------------- textures ---------------- */

function grassTexture(R) {   // 1.2 m of short grass
  return canvasTexture(512, 512, (g, w, h) => {
    g.fillStyle = "#29461f"; g.fillRect(0, 0, w, h);
    for (let i = 0; i < 350; i++) {
      g.fillStyle = "rgba(62,46,26," + (0.12 + R() * 0.2) + ")";
      const r = 2 + R() * 7;
      wrapped(w, h, R() * w, R() * h, 12, (x, y) => { g.beginPath(); g.ellipse(x, y, r, r * 0.6, R() * 3, 0, 7); g.fill(); });
    }
    const greens = ["#3d6b2c", "#4a7a32", "#2f5a26", "#58893a", "#6b9442", "#36602a", "#7a9a4a", "#4f6e2a"];
    g.lineCap = "round";
    for (let i = 0; i < 16000; i++) {
      const len = 5 + R() * 13, a = -Math.PI / 2 + (R() - 0.5) * 1.8, bend = (R() - 0.5) * 4;
      g.strokeStyle = greens[(R() * greens.length) | 0];
      g.globalAlpha = 0.5 + R() * 0.5;
      g.lineWidth = 1 + R() * 1.5;
      wrapped(w, h, R() * w, R() * h, 18, (x, y) => {
        g.beginPath(); g.moveTo(x, y);
        g.quadraticCurveTo(x + Math.cos(a) * len * 0.5 + bend, y + Math.sin(a) * len * 0.5, x + Math.cos(a) * len, y + Math.sin(a) * len);
        g.stroke();
      });
    }
    g.globalAlpha = 1;
  });
}

function litterTexture(R) {   // 2.5 m of forest floor: soil, fallen leaves, needles, twigs, moss
  return canvasTexture(512, 512, (g, w, h) => {
    g.fillStyle = "#2a2116"; g.fillRect(0, 0, w, h);
    for (let i = 0; i < 160; i++) {
      g.fillStyle = R() < 0.5 ? "rgba(20,15,9,0.35)" : "rgba(70,55,35,0.25)";
      const r = 8 + R() * 30;
      wrapped(w, h, R() * w, R() * h, 40, (x, y) => { g.beginPath(); g.arc(x, y, r, 0, 7); g.fill(); });
    }
    for (let i = 0; i < 40; i++) {
      g.fillStyle = "rgba(52,80,42," + (0.25 + R() * 0.3) + ")";
      const r = 6 + R() * 16;
      wrapped(w, h, R() * w, R() * h, 24, (x, y) => { g.beginPath(); g.ellipse(x, y, r, r * 0.7, R() * 3, 0, 7); g.fill(); });
    }
    const leaves = ["#6b4a2a", "#8a5a2c", "#5a3e22", "#9a6a30", "#4a3a1e", "#7a6a3a", "#a0702a", "#5e4a28"];
    for (let i = 0; i < 2600; i++) {
      const r = 2.5 + R() * 5, rot = R() * Math.PI;
      g.fillStyle = leaves[(R() * leaves.length) | 0];
      g.globalAlpha = 0.6 + R() * 0.4;
      wrapped(w, h, R() * w, R() * h, 10, (x, y) => { g.beginPath(); g.ellipse(x, y, r, r * 0.45, rot, 0, 7); g.fill(); });
    }
    g.lineCap = "round";
    for (let i = 0; i < 2200; i++) {
      const len = 4 + R() * 9, a = R() * Math.PI;
      g.strokeStyle = R() < 0.5 ? "#3a2614" : "#6e4320";
      g.globalAlpha = 0.5 + R() * 0.5; g.lineWidth = 0.8;
      wrapped(w, h, R() * w, R() * h, 12, (x, y) => { g.beginPath(); g.moveTo(x, y); g.lineTo(x + Math.cos(a) * len, y + Math.sin(a) * len); g.stroke(); });
    }
    for (let i = 0; i < 26; i++) {
      const len = 20 + R() * 40, a = R() * Math.PI;
      g.strokeStyle = "#3b2a1a"; g.globalAlpha = 0.9; g.lineWidth = 1.5 + R() * 2;
      wrapped(w, h, R() * w, R() * h, 60, (x, y) => { g.beginPath(); g.moveTo(x, y); g.lineTo(x + Math.cos(a) * len, y + Math.sin(a) * len); g.stroke(); });
    }
    g.globalAlpha = 1;
  });
}

function radialAlpha(R, inner, size = 512) {   // white inside, a ragged fade to black at the edge
  return canvasTexture(size, size, (g, w) => {
    g.fillStyle = "#000"; g.fillRect(0, 0, w, w);
    const c = w / 2;
    g.beginPath();
    for (let i = 0; i <= 180; i++) {
      const a = i / 180 * Math.PI * 2;
      const r = c * (inner + (1 - inner) * (0.55 + 0.25 * Math.sin(a * 5 + 1) * Math.sin(a * 3) + 0.2 * R()));
      g.lineTo(c + Math.cos(a) * r, c + Math.sin(a) * r);
    }
    g.closePath();
    g.fillStyle = "#fff";
    g.filter = "blur(" + Math.round(w * 0.03) + "px)";
    g.fill();
    g.filter = "none";
  }, false);
}

function ashTexture(R) {   // the scorched ground around the fire ring
  return canvasTexture(256, 256, (g, w) => {
    const c = w / 2;
    const grad = g.createRadialGradient(c, c, 0, c, c, c);
    grad.addColorStop(0, "rgba(26,24,22,1)");
    grad.addColorStop(0.45, "rgba(48,42,36,0.95)");
    grad.addColorStop(0.75, "rgba(58,44,30,0.7)");
    grad.addColorStop(1, "rgba(58,44,30,0)");
    g.fillStyle = grad; g.fillRect(0, 0, w, w);
    for (let i = 0; i < 500; i++) {
      const a = R() * Math.PI * 2, r = R() * c * 0.7;
      g.fillStyle = R() < 0.6 ? "rgba(120,115,108,0.25)" : "rgba(10,8,6,0.4)";
      g.fillRect(c + Math.cos(a) * r, c + Math.sin(a) * r, 2, 2);
    }
  });
}

function coalTexture(R) {   // glowing embers under the logs
  return canvasTexture(256, 256, (g, w) => {
    const c = w / 2;
    g.fillStyle = "#000"; g.fillRect(0, 0, w, w);
    for (let i = 0; i < 900; i++) {
      const a = R() * Math.PI * 2, r = Math.sqrt(R()) * c * 0.95, s = 3 + R() * 9;
      const hot = 1 - r / c;
      g.fillStyle = "rgba(" + (180 + 75 * hot | 0) + "," + (40 + 120 * hot * R() | 0) + ",10," + (0.25 + 0.6 * hot) + ")";
      g.beginPath(); g.arc(c + Math.cos(a) * r, c + Math.sin(a) * r, s, 0, 7); g.fill();
    }
    const fade = g.createRadialGradient(c, c, c * 0.6, c, c, c);
    fade.addColorStop(0, "rgba(0,0,0,0)"); fade.addColorStop(1, "rgba(0,0,0,1)");
    g.fillStyle = fade; g.fillRect(0, 0, w, w);
  });
}

function flameTexture() {   // a soft teardrop, brightest low in the middle
  return canvasTexture(64, 128, (g, w, h) => {
    g.beginPath();
    g.moveTo(w / 2, 0);
    g.bezierCurveTo(w * 0.62, h * 0.35, w * 0.98, h * 0.62, w * 0.82, h * 0.86);
    g.bezierCurveTo(w * 0.7, h * 1.0, w * 0.3, h * 1.0, w * 0.18, h * 0.86);
    g.bezierCurveTo(w * 0.02, h * 0.62, w * 0.38, h * 0.35, w / 2, 0);
    const grad = g.createRadialGradient(w / 2, h * 0.78, 2, w / 2, h * 0.7, h * 0.7);
    grad.addColorStop(0, "rgba(255,255,235,1)");
    grad.addColorStop(0.3, "rgba(255,200,90,0.9)");
    grad.addColorStop(0.7, "rgba(255,90,20,0.45)");
    grad.addColorStop(1, "rgba(200,30,0,0)");
    g.fillStyle = grad;
    g.filter = "blur(3px)";
    g.fill();
  });
}

function softTexture(inner, outer) {
  return canvasTexture(128, 128, (g, w) => {
    const grad = g.createRadialGradient(w / 2, w / 2, 0, w / 2, w / 2, w / 2);
    grad.addColorStop(0, inner); grad.addColorStop(1, outer);
    g.fillStyle = grad; g.fillRect(0, 0, w, w);
  });
}

function barkTexture(R) {
  return canvasTexture(128, 256, (g, w, h) => {
    g.fillStyle = "#4a3322"; g.fillRect(0, 0, w, h);
    for (let i = 0; i < 90; i++) {
      g.strokeStyle = R() < 0.5 ? "rgba(20,12,6,0.6)" : "rgba(110,80,52,0.35)";
      g.lineWidth = 1 + R() * 3;
      const x = R() * w;
      g.beginPath(); g.moveTo(x, 0);
      for (let y = 0; y <= h; y += 16) g.lineTo(x + Math.sin(y * 0.05 + i) * 3, y);
      g.stroke();
    }
  });
}

function endTexture() {   // the cut end of a log
  return canvasTexture(128, 128, (g, w) => {
    const c = w / 2;
    g.fillStyle = "#3a2716"; g.fillRect(0, 0, w, w);
    g.fillStyle = "#b08a5a"; g.beginPath(); g.arc(c, c, c * 0.86, 0, 7); g.fill();
    for (let r = 6; r < c * 0.86; r += 5) {
      g.strokeStyle = "rgba(110,75,40,0.45)"; g.lineWidth = 1.2;
      g.beginPath(); g.arc(c, c, r, 0, 7); g.stroke();
    }
  });
}

function pineRingTexture(R) {   // the woods beyond the trees, as a dark silhouette all the way round
  const t = canvasTexture(2048, 256, (g, w, h) => {
    g.fillStyle = "#04070b";
    g.fillRect(0, h * 0.82, w, h * 0.18);
    for (let i = 0; i < 170; i++) {
      const top = h * (0.08 + R() * 0.55), half = 14 + R() * 26, x = R() * w;
      wrapped(w, h, x, 0, 60, (cx) => {
        g.beginPath();
        g.moveTo(cx, top);
        for (let k = 1; k <= 6; k++) {   // jagged branch tiers down the right side, then back up the left
          const y = top + (h * 0.86 - top) * k / 6;
          g.lineTo(cx + half * k / 6 * (k % 2 ? 1.15 : 0.75), y);
        }
        for (let k = 6; k >= 1; k--) {
          const y = top + (h * 0.86 - top) * k / 6;
          g.lineTo(cx - half * k / 6 * (k % 2 ? 1.15 : 0.75), y);
        }
        g.closePath(); g.fill();
      });
    }
  });
  t.wrapS = THREE.RepeatWrapping;
  return t;
}

/* ---------------- geometry ---------------- */

// a little lumpiness, the same for vertices at the same spot (so seams stay closed)
function lumpy(geo, amount, R) {
  const p = geo.attributes.position, seen = new Map();
  for (let i = 0; i < p.count; i++) {
    const key = p.getX(i).toFixed(3) + "," + p.getY(i).toFixed(3) + "," + p.getZ(i).toFixed(3);
    if (!seen.has(key)) seen.set(key, [(R() - 0.5) * amount, (R() - 0.5) * amount, (R() - 0.5) * amount]);
    const d = seen.get(key);
    p.setXYZ(i, p.getX(i) + d[0], p.getY(i) + d[1], p.getZ(i) + d[2]);
  }
  geo.computeVertexNormals();
  return geo;
}

function merge(geos) {
  const parts = geos.map((g) => (g.index ? g.toNonIndexed() : g));
  const total = parts.reduce((n, g) => n + g.attributes.position.count, 0);
  const pos = new Float32Array(total * 3), nor = new Float32Array(total * 3);
  let o = 0;
  parts.forEach((g) => {
    pos.set(g.attributes.position.array, o * 3);
    nor.set(g.attributes.normal.array, o * 3);
    o += g.attributes.position.count;
  });
  const out = new THREE.BufferGeometry();
  out.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  out.setAttribute("normal", new THREE.BufferAttribute(nor, 3));
  return out;
}

// unit trees: 1 tall, about 1 wide at the widest; each one is scaled (r, h, r)
function pineGeometry(R) {
  const tiers = [[0.2, 0.44, 1.0], [0.38, 0.62, 0.8], [0.55, 0.8, 0.58], [0.72, 1.0, 0.36]];
  return merge(tiers.map(([b, t, r]) => lumpy(new THREE.ConeGeometry(r, t - b, 10, 2).translate(0, (b + t) / 2, 0), 0.08, R)));
}

function oakGeometry(R) {
  const blobs = [[0, 0.7, 0, 0.6, 0.24], [0.38, 0.6, 0.15, 0.42, 0.18], [-0.32, 0.62, -0.22, 0.45, 0.19],
    [0.05, 0.88, 0.04, 0.4, 0.15], [-0.12, 0.56, 0.4, 0.4, 0.16]];
  return merge(blobs.map(([x, y, z, r, ry]) => lumpy(new THREE.IcosahedronGeometry(1, 1), 0.25, R).scale(r, ry, r).translate(x, y, z)));
}

function instanced(geo, mat, items, place) {
  const mesh = new THREE.InstancedMesh(geo, mat, items.length);
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), s = new THREE.Vector3(), p = new THREE.Vector3(), c = new THREE.Color();
  items.forEach((it, i) => {
    const out = place(it, p, q, s, c);
    m.compose(p, q, s);
    mesh.setMatrixAt(i, m);
    if (out) mesh.setColorAt(i, c);
  });
  mesh.instanceMatrix.needsUpdate = true;
  if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  mesh.computeBoundingSphere();
  return mesh;
}

const yawQ = (q, deg) => q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), -deg * Math.PI / 180);

/* ---------------- the camp ---------------- */

export function buildCamp(camp, opts) {
  const R = seeded(1234);
  const k = camp.k;
  const group = new THREE.Group();
  const lights = [];
  const aniso = opts.anisotropy || 1;
  const shadows = !!opts.high;
  const std = (o) => new THREE.MeshStandardMaterial(Object.assign({ roughness: 0.9, metalness: 0 }, o));
  const add = (mesh, pos, yaw) => {
    if (pos) mesh.position.copy(toV(pos));
    if (yaw !== undefined) mesh.rotation.y = -yaw * Math.PI / 180;
    mesh.traverse((o) => { if (o.isMesh) { o.castShadow = shadows; o.receiveShadow = true; } });
    group.add(mesh);
    return mesh;
  };

  // ---- the ground: forest floor everywhere, grass in the clearing, ash around the fire ----
  const litter = litterTexture(R);
  litter.wrapS = litter.wrapT = THREE.RepeatWrapping;
  litter.repeat.setScalar(2 * camp.ground_r / (2.5 * k));
  litter.anisotropy = aniso;
  const floor = new THREE.Mesh(new THREE.CircleGeometry(camp.ground_r, 72), std({ map: litter, roughness: 1 }));
  floor.rotation.x = -Math.PI / 2;
  floor.position.copy(toV(camp.center));
  floor.receiveShadow = true;
  group.add(floor);

  const grassR = camp.clearing_r + 4 * k;
  const grass = grassTexture(R);
  grass.wrapS = grass.wrapT = THREE.RepeatWrapping;
  grass.repeat.setScalar(2 * grassR / (1.2 * k));
  grass.anisotropy = aniso;
  const lawn = new THREE.Mesh(new THREE.CircleGeometry(grassR, 96), std({
    map: grass, alphaMap: radialAlpha(R, 0.62), transparent: true, depthWrite: false, roughness: 0.95,
    polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1
  }));
  lawn.rotation.x = -Math.PI / 2;
  lawn.position.copy(toV(camp.center));
  lawn.receiveShadow = true;
  lawn.renderOrder = 1;
  group.add(lawn);

  const fire = camp.fire;
  const ash = new THREE.Mesh(new THREE.CircleGeometry(fire.r * 2.6, 48), std({
    map: ashTexture(R), transparent: true, depthWrite: false, roughness: 1,
    polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2
  }));
  ash.rotation.x = -Math.PI / 2;
  ash.position.copy(toV(fire.p));
  ash.receiveShadow = true;
  ash.renderOrder = 2;
  group.add(ash);

  // ---- the woods ----
  const pines = camp.trees.filter((t) => t.kind === "pine"), oaks = camp.trees.filter((t) => t.kind !== "pine");
  const placeTree = (t, p, q, s, c, base) => {
    toV(t.p, p); yawQ(q, t.yaw); s.set(t.r, t.h, t.r);
    c.set(base).multiplyScalar(t.tint);
    return true;
  };
  const leafMat = std({ color: 0xffffff, flatShading: true });
  const trunkMat = std({ color: 0xffffff, map: barkTexture(R) });
  const trees = [
    instanced(pineGeometry(R), leafMat, pines, (t, p, q, s, c) => placeTree(t, p, q, s, c, 0x1d4428)),
    instanced(new THREE.CylinderGeometry(0.035, 0.065, 1, 8).translate(0, 0.5, 0), trunkMat, pines,
      (t, p, q, s, c) => placeTree(t, p, q, s, c, 0x8a6a50)),
    instanced(oakGeometry(R), leafMat, oaks, (t, p, q, s, c) => placeTree(t, p, q, s, c, 0x3a5f28)),
    instanced(new THREE.CylinderGeometry(0.06, 0.11, 0.66, 8).translate(0, 0.33, 0), trunkMat, oaks,
      (t, p, q, s, c) => placeTree(t, p, q, s, c, 0x8a6a50)),
  ];
  trees.forEach((m) => { m.castShadow = shadows; m.receiveShadow = true; group.add(m); });

  group.add(instanced(lumpy(new THREE.IcosahedronGeometry(1, 1), 0.3, R), std({ color: 0xffffff, flatShading: true }), camp.bushes,
    (b, p, q, s, c) => { toV(b.p, p); p.y = 0.25 * b.r; q.identity(); s.set(b.r, 0.7 * b.r, b.r); c.set(0x2c5524).multiplyScalar(b.tint); return true; }));
  const rockGeo = lumpy(new THREE.DodecahedronGeometry(1, 0), 0.25, R);
  const rockMat = std({ color: 0xffffff, flatShading: true, roughness: 0.95 });
  group.add(instanced(rockGeo, rockMat, camp.rocks,
    (b, p, q, s, c) => { toV(b.p, p); p.y = 0.12 * b.r; yawQ(q, b.yaw); s.set(b.r, 0.55 * b.r, 0.85 * b.r); c.set(0x6a655d).multiplyScalar(0.75 + R() * 0.4); return true; }));
  group.children.slice(-2).forEach((m) => { m.castShadow = shadows; m.receiveShadow = true; });

  // the rest of the woods, as a dark ring far out, and the trunks of the woods fade into the night
  const ring = new THREE.Mesh(new THREE.CylinderGeometry(80 * k, 80 * k, 30 * k, 64, 1, true),
    new THREE.MeshBasicMaterial({ map: pineRingTexture(R), transparent: true, side: THREE.BackSide, fog: false, depthWrite: false }));
  ring.material.map.repeat.set(5, 1);
  ring.position.copy(toV(camp.center));
  ring.position.y = 15 * k - 2 * k;
  ring.renderOrder = -1;
  group.add(ring);

  // ---- the campfire ----
  const F = new THREE.Group();
  F.position.copy(toV(fire.p));
  group.add(F);
  const stoneGeo = lumpy(new THREE.DodecahedronGeometry(1, 0), 0.3, R);
  for (let i = 0; i < 12; i++) {
    const a = i / 12 * Math.PI * 2 + R() * 0.2, sz = (0.11 + R() * 0.06) * k;
    const st = new THREE.Mesh(stoneGeo, std({ color: new THREE.Color(0x6f6a62).multiplyScalar(0.7 + R() * 0.4), flatShading: true }));
    st.position.set(Math.cos(a) * fire.r, sz * 0.4, Math.sin(a) * fire.r);
    st.scale.set(sz, sz * 0.65, sz * 0.85);
    st.rotation.y = R() * 6;
    st.castShadow = shadows; st.receiveShadow = true;
    F.add(st);
  }
  const coals = new THREE.Mesh(new THREE.CircleGeometry(fire.r * 0.8, 32),
    new THREE.MeshBasicMaterial({ map: coalTexture(R), color: new THREE.Color(1.8, 1.2, 1.0), transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false }));
  coals.rotation.x = -Math.PI / 2;
  coals.position.y = 0.012 * k;
  F.add(coals);
  const charred = std({ color: 0x2a1c13, emissive: 0xff5a14, emissiveIntensity: 0.25, roughness: 1 });
  const logGeo = new THREE.CylinderGeometry(0.04 * k, 0.05 * k, 0.75 * k, 8);
  for (let i = 0; i < 5; i++) {
    const a = i / 5 * Math.PI * 2 + 0.3;
    const foot = new THREE.Vector3(Math.cos(a) * 0.33 * k, 0.03 * k, Math.sin(a) * 0.33 * k);
    const tip = new THREE.Vector3(Math.cos(a + 2.4) * 0.04 * k, 0.5 * k, Math.sin(a + 2.4) * 0.04 * k);
    const log = new THREE.Mesh(logGeo, charred);
    log.position.copy(foot).add(tip).multiplyScalar(0.5);
    log.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), tip.clone().sub(foot).normalize());
    F.add(log);   // no shadow: the fire's light is in among these logs
  }
  const flameTex = flameTexture();
  const flames = [];
  for (let i = 0; i < 11; i++) {
    const core = i >= 8;
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({
      map: flameTex, color: core ? new THREE.Color(3.2, 2.6, 1.6) : new THREE.Color(2.6, 1.25, 0.4),
      transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false
    }));
    sp.center.set(0.5, 0.04);
    const a = R() * Math.PI * 2, r = (core ? 0.04 : 0.06 + R() * 0.12) * k;
    const f = { sp, x: Math.cos(a) * r, z: Math.sin(a) * r, w: (core ? 0.22 : 0.26 + R() * 0.18) * k,
      h: (core ? 0.5 : 0.45 + R() * 0.45) * k, ph: R() * 10 };
    sp.position.set(f.x, 0.06 * k, f.z);
    F.add(sp);
    flames.push(f);
  }
  const glow = new THREE.Sprite(new THREE.SpriteMaterial({
    map: softTexture("rgba(255,170,90,1)", "rgba(255,90,20,0)"), color: new THREE.Color(1.4, 0.75, 0.35),
    transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false, opacity: 0.35
  }));
  glow.position.y = 0.4 * k;
  glow.scale.set(2.6 * k, 2.2 * k, 1);
  F.add(glow);

  // sparks: little embers rising and swirling out of the fire
  const nE = 70, ePos = new Float32Array(nE * 3), eCol = new Float32Array(nE * 3), eVel = new Float32Array(nE * 3);
  const eAge = new Float32Array(nE), eLife = new Float32Array(nE);
  const spawn = (i, age) => {
    const a = R() * Math.PI * 2, r = R() * 0.2 * k;
    ePos.set([Math.cos(a) * r, 0.15 * k, Math.sin(a) * r], i * 3);
    eVel.set([(R() - 0.5) * 0.3 * k, (0.6 + R() * 1.1) * k, (R() - 0.5) * 0.3 * k], i * 3);
    eLife[i] = 1.2 + R() * 1.8;
    eAge[i] = age;
  };
  for (let i = 0; i < nE; i++) spawn(i, R() * 2.5);
  const eGeo = new THREE.BufferGeometry();
  eGeo.setAttribute("position", new THREE.BufferAttribute(ePos, 3));
  eGeo.setAttribute("color", new THREE.BufferAttribute(eCol, 3));
  const embers = new THREE.Points(eGeo, new THREE.PointsMaterial({
    size: 0.022 * k, vertexColors: true, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false
  }));
  embers.frustumCulled = false;
  F.add(embers);

  // a thin smoke column
  const smokeTex = softTexture("rgba(150,150,165,0.9)", "rgba(150,150,165,0)");
  const smoke = [];
  for (let i = 0; i < 9; i++) {
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: smokeTex, color: 0x6a6a78, transparent: true, depthWrite: false, opacity: 0 }));
    F.add(sp);
    smoke.push({ sp, age: i / 9 * 6, ph: R() * 10 });
  }

  const fireLight = new THREE.PointLight(0xff7b30, 0, 0, 2);
  fireLight.position.y = 0.6 * k;
  if (shadows) {
    fireLight.castShadow = true;
    fireLight.shadow.mapSize.set(1024, 1024);
    fireLight.shadow.camera.near = 0.08 * k;
    fireLight.shadow.camera.far = 45 * k;
    fireLight.shadow.bias = -0.002;
    fireLight.shadow.normalBias = 0.01 * k;
  }
  F.add(fireLight);
  lights.push(fireLight);

  // ---- warm lamps ----
  const lampGlass = new THREE.MeshBasicMaterial({ color: new THREE.Color(3, 2.1, 1.0), toneMapped: false });
  const metal = std({ color: 0x1b1b1d, roughness: 0.5, metalness: 0.6 });
  const lantern = (parent, x, y, z, s) => {
    const glass = new THREE.Mesh(new THREE.CylinderGeometry(0.055 * s, 0.055 * s, 0.15 * s, 12), lampGlass);
    glass.position.set(x, y, z);
    const cap = new THREE.Mesh(new THREE.ConeGeometry(0.075 * s, 0.07 * s, 12), metal);
    cap.position.set(x, y + 0.11 * s, z);
    const foot = new THREE.Mesh(new THREE.CylinderGeometry(0.065 * s, 0.07 * s, 0.03 * s, 12), metal);
    foot.position.set(x, y - 0.09 * s, z);
    parent.add(glass, cap, foot);
  };

  // the shepherd's hook just off the left of the starting view: it lights the board
  const hook = new THREE.Group();
  hook.position.copy(toV(camp.hook.p));
  const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.012 * k, 0.014 * k, camp.hook.h, 8), metal);
  pole.position.y = camp.hook.h / 2;
  const arm = new THREE.Mesh(new THREE.BoxGeometry(camp.hook.arm, 0.015 * k, 0.015 * k), metal);
  arm.position.set(camp.hook.arm / 2, camp.hook.h, 0);
  hook.add(pole, arm);
  lantern(hook, camp.hook.arm, camp.hook.h - 0.16 * k, 0, k);
  const hookLight = new THREE.PointLight(0xffb46b, 7 * k * k, 0, 2);
  hookLight.position.set(camp.hook.arm, camp.hook.h - 0.16 * k, 0);
  hook.add(hookLight);
  lights.push(hookLight);
  add(hook);

  // ---- string lights between two trees ----
  const pts = camp.lights.map((p) => toV(p));
  const wire = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: 0x141414 }));
  group.add(wire);
  const bulbs = instanced(new THREE.SphereGeometry(0.045 * k, 10, 8),
    new THREE.MeshBasicMaterial({ color: 0xffffff, toneMapped: false }), pts,
    (p0, p, q, s, c) => { p.copy(p0); p.y -= 0.07 * k; q.identity(); s.setScalar(1); c.setRGB(2.8, 2.0 + R() * 0.3, 1.0); return true; });
  group.add(bulbs);
  const mid = pts[pts.length >> 1].clone();
  const stringLight = new THREE.PointLight(0xffc27a, 5 * k * k, 0, 2);
  stringLight.position.copy(mid).add(new THREE.Vector3(0, -0.4 * k, 0));
  group.add(stringLight);
  lights.push(stringLight);

  // ---- tents ----
  camp.tents.forEach((t) => {
    const g = new THREE.Group();
    const fabric = std({ color: t.color, side: THREE.DoubleSide, roughness: 0.85,
      emissive: new THREE.Color(0xffa04a), emissiveIntensity: t.glow || 0 });
    const door = std({ color: 0x1a1410, side: THREE.DoubleSide, emissive: new THREE.Color(0xff9a40), emissiveIntensity: (t.glow || 0) * 1.4 });
    if (t.kind === "dome") {
      const dome = new THREE.Mesh(new THREE.SphereGeometry(1, 28, 12, 0, Math.PI * 2, 0, Math.PI / 2), fabric);
      dome.scale.set(t.w / 2, t.h, t.l / 2);
      const d = new THREE.Mesh(new THREE.CircleGeometry(1, 24, 0, Math.PI), door);
      d.scale.set(t.w * 0.22, t.h * 0.62, 1);
      d.position.set(0, 0.02 * k, -t.l / 2 * 0.93);
      d.rotation.x = -0.35;
      const fly = new THREE.Mesh(new THREE.TorusGeometry(1, 0.012, 6, 32, Math.PI), std({ color: 0x2b2b2b }));
      fly.scale.set(t.w / 2, t.h, t.l / 2);
      fly.rotation.y = Math.PI / 2;
      g.add(dome, d, fly);
    } else {
      const shape = new THREE.Shape();
      shape.moveTo(-t.w / 2, 0); shape.lineTo(t.w / 2, 0); shape.lineTo(0, t.h); shape.closePath();
      const body = new THREE.Mesh(new THREE.ExtrudeGeometry(shape, { depth: t.l, bevelEnabled: false }), fabric);
      body.position.z = -t.l / 2;
      const flap = new THREE.Shape();
      flap.moveTo(-t.w * 0.28, 0); flap.lineTo(t.w * 0.28, 0); flap.lineTo(0, t.h * 0.78); flap.closePath();
      const d = new THREE.Mesh(new THREE.ShapeGeometry(flap), door);
      d.position.z = -t.l / 2 - 0.01 * k;
      g.add(body, d);
    }
    add(g, t.p, t.yaw);   // the door (local -z) faces the fire
  });

  // ---- the picnic table with a lantern on it ----
  {
    const tb = camp.table, g = new THREE.Group();
    const wood = std({ color: 0x8a6440, roughness: 0.85 });
    const plank = (w, h, d, x, y, z) => { const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), wood); m.position.set(x, y, z); g.add(m); return m; };
    plank(tb.l, 0.045 * k, tb.w, 0, tb.h, 0);
    [-1, 1].forEach((sd) => {
      plank(tb.l, 0.04 * k, 0.26 * k, 0, tb.bench, sd * (tb.w / 2 + 0.3 * k));
      [-1, 1].forEach((end) => {
        const leg = plank(0.05 * k, tb.h * 1.15, 0.07 * k, end * tb.l * 0.36, tb.h / 2, sd * 0.32 * k);
        leg.rotation.x = sd * 0.5;
      });
    });
    lantern(g, tb.l * 0.2, tb.h + 0.12 * k, 0, k);
    const tl = new THREE.PointLight(0xffb46b, 2.5 * k * k, 0, 2);
    tl.position.set(tb.l * 0.2, tb.h + 0.15 * k, 0);
    g.add(tl);
    lights.push(tl);
    add(g, tb.p, tb.yaw);
  }

  // ---- a cooler ----
  {
    const c = camp.cooler, g = new THREE.Group(), [w, d, h] = c.size;
    const body = new THREE.Mesh(new THREE.BoxGeometry(w, h * 0.82, d), std({ color: 0xb8322a, roughness: 0.5 }));
    body.position.y = h * 0.41;
    const lid = new THREE.Mesh(new THREE.BoxGeometry(w * 1.03, h * 0.18, d * 1.05), std({ color: 0xf0f0ea, roughness: 0.5 }));
    lid.position.y = h * 0.91;
    g.add(body, lid);
    add(g, c.p, c.yaw);
  }

  // ---- log seats, a woodpile and stumps ----
  const bark = barkTexture(R), ends = endTexture();
  bark.wrapS = bark.wrapT = THREE.RepeatWrapping;
  const logMats = [std({ map: bark, color: 0xb09078 }), std({ map: ends }), std({ map: ends })];
  camp.logs.forEach((l) => {
    const m = new THREE.Mesh(new THREE.CylinderGeometry(l.r, l.r * 1.05, l.len, 14), logMats);
    m.rotation.z = Math.PI / 2;
    const g = new THREE.Group();
    m.position.y = l.r * 0.9;
    g.add(m);
    add(g, l.p, l.yaw);
  });
  {
    const wp = camp.woodpile, g = new THREE.Group();
    const geo = new THREE.CylinderGeometry(wp.r, wp.r, wp.len, 9);
    [6, 5, 4].forEach((n, row) => {
      for (let i = 0; i < n; i++) {
        const m = new THREE.Mesh(geo, logMats);
        m.rotation.x = Math.PI / 2;
        m.position.set((i - (n - 1) / 2) * wp.r * 2.05, wp.r * (1 + row * 1.75), 0);
        g.add(m);
      }
    });
    add(g, wp.p, wp.yaw);
  }
  camp.stumps.forEach((s) => {
    const m = new THREE.Mesh(new THREE.CylinderGeometry(s.r, s.r * 1.15, s.h, 14), logMats);
    m.position.y = s.h / 2;
    const g = new THREE.Group(); g.add(m);
    add(g, s.p, 0);
  });

  // ---- camp chairs facing the fire ----
  camp.chairs.forEach((ch) => {
    const g = new THREE.Group(), s = ch.size;
    const cloth = std({ color: ch.color, roughness: 0.8, side: THREE.DoubleSide });
    const seat = new THREE.Mesh(new THREE.BoxGeometry(s, 0.03 * s, s * 0.85), cloth);
    seat.position.y = 0.42 * s;
    const back = new THREE.Mesh(new THREE.BoxGeometry(s, s * 0.95, 0.03 * s), cloth);
    back.position.set(0, 0.85 * s, s * 0.45);
    back.rotation.x = -0.25;
    g.add(seat, back);
    [-1, 1].forEach((sx) => [-1, 1].forEach((sz) => {
      const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.02 * s, 0.02 * s, 0.85 * s, 6), metal);
      leg.position.set(sx * s * 0.45, 0.4 * s, sz * s * 0.35);
      leg.rotation.x = sz * 0.35;
      g.add(leg);
    }));
    [-1, 1].forEach((sx) => {
      const armrest = new THREE.Mesh(new THREE.BoxGeometry(0.08 * s, 0.03 * s, s * 0.8), metal);
      armrest.position.set(sx * s * 0.52, 0.65 * s, 0.02 * s);
      g.add(armrest);
    });
    add(g, ch.p, ch.yaw);
  });

  // ---- the fire, every frame ----
  const update = (t, dt) => {
    const flick = 0.82 + 0.1 * Math.sin(t * 13.1) + 0.06 * Math.sin(t * 23.7 + 1.3) + 0.05 * Math.sin(t * 7.3 + 0.4);
    fireLight.intensity = 45 * k * k * flick;
    fireLight.position.x = Math.sin(t * 5.3) * 0.03 * k;
    glow.material.opacity = 0.28 + 0.1 * flick;
    flames.forEach((f) => {
      const h = 0.72 + 0.18 * Math.sin(t * 8.3 + f.ph) + 0.1 * Math.sin(t * 13.7 + f.ph * 2) + 0.06 * Math.sin(t * 21 + f.ph * 3);
      f.sp.scale.set(f.w * (0.9 + 0.12 * Math.sin(t * 7 + f.ph)), f.h * h, 1);
      f.sp.position.x = f.x + Math.sin(t * 3.1 + f.ph) * 0.025 * k;
      f.sp.position.z = f.z + Math.cos(t * 2.7 + f.ph) * 0.02 * k;
    });
    for (let i = 0; i < nE; i++) {
      eAge[i] += dt;
      if (eAge[i] > eLife[i]) spawn(i, 0);
      const j = i * 3;
      eVel[j] += Math.sin(t * 2.3 + i) * 0.4 * k * dt;
      eVel[j + 2] += Math.cos(t * 1.9 + i * 1.7) * 0.4 * k * dt;
      ePos[j] += eVel[j] * dt; ePos[j + 1] += eVel[j + 1] * dt; ePos[j + 2] += eVel[j + 2] * dt;
      const fade = Math.max(0, 1 - eAge[i] / eLife[i]);
      eCol[j] = 3 * fade; eCol[j + 1] = (1.1 + 0.6 * fade) * fade; eCol[j + 2] = 0.3 * fade;
    }
    eGeo.attributes.position.needsUpdate = true;
    eGeo.attributes.color.needsUpdate = true;
    smoke.forEach((s) => {
      s.age = (s.age + dt) % 6;
      const u = s.age / 6;
      s.sp.position.set(Math.sin(t * 0.4 + s.ph) * 0.3 * k * u, (0.7 + 3.2 * u) * k, Math.cos(t * 0.3 + s.ph) * 0.2 * k * u);
      const size = (0.35 + 1.4 * u) * k;
      s.sp.scale.set(size, size, 1);
      s.sp.material.opacity = 0.16 * Math.sin(Math.PI * u);
    });
  };
  update(0, 0);

  return { group, update, lights, k };
}
