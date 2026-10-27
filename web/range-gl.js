/* 3D Target Range renderer (Three.js / WebGL).
 *
 * World units are yards. Game positions are [downrange, right, height];
 * Three.js uses x = right, y = up, z = toward the hitter, so downrange is -z.
 * The camera director (director.js) decides what the camera does; this file
 * only draws.
 */
import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";

const toV = (p, out) => (out || new THREE.Vector3()).set(p[1], p[2] || 0, -p[0]);
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const FIELD_WIDTH = 56;
const FIELD_DEPTH = 272;
const TRACER_SEGMENTS = 240;
const TRACER_RADIAL = 6;

function canvasTexture(w, h, draw, srgb = true) {
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  draw(c.getContext("2d"), w, h);
  const t = new THREE.CanvasTexture(c);
  if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

function glowTexture() {
  return canvasTexture(128, 128, (g, w) => {
    const grad = g.createRadialGradient(w / 2, w / 2, 0, w / 2, w / 2, w / 2);
    grad.addColorStop(0, "rgba(255,255,240,1)");
    grad.addColorStop(0.25, "rgba(255,245,220,0.55)");
    grad.addColorStop(1, "rgba(255,240,200,0)");
    g.fillStyle = grad; g.fillRect(0, 0, w, w);
  });
}

class RangeGL {
  constructor(canvas, opts) {
    this.canvas = canvas;
    this.targets = opts.targets;
    this.inner = opts.inner;
    this.center = opts.center;
    this.idleCamera = opts.idleCamera;
    this.high = opts.quality !== "low";

    const r = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
    r.setPixelRatio(Math.min(window.devicePixelRatio || 1, this.high ? 2 : 1));
    r.toneMapping = THREE.ACESFilmicToneMapping;
    r.toneMappingExposure = 1.05;
    r.shadowMap.enabled = this.high;
    r.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer = r;

    this.scene = new THREE.Scene();
    this.scene.fog = new THREE.FogExp2(0x101a38, 0.0021);
    this.camera = new THREE.PerspectiveCamera(36, 1, 0.05, 4000);
    this.look = new THREE.Vector3();
    this.size = [0, 0];
    this.lastNow = 0;
    this.camKey = null;
    this.shotId = null;
    this.flashUntil = 0;

    this.buildSky();
    this.buildGround();
    this.buildNets();
    this.buildLights();
    this.buildSigns();
    this.buildTargets();
    this.buildBay();
    this.buildBall();
    this.buildTracer();
    this.buildParticles();
    this.buildMarkers();
    this.cornhole = null;   // Golf Cornhole's board and bags, built when a cornhole game shows

    if (this.high) {
      this.composer = new EffectComposer(r);
      this.composer.addPass(new RenderPass(this.scene, this.camera));
      this.bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.6, 0.4, 0.92);
      this.composer.addPass(this.bloom);
      this.composer.addPass(new OutputPass());
    }
  }

  /* ---------------- scene building ---------------- */

  buildSky() {
    const sky = new THREE.Mesh(
      new THREE.SphereGeometry(1800, 32, 16),
      new THREE.ShaderMaterial({
        side: THREE.BackSide, depthWrite: false, fog: false,
        uniforms: {
          top: { value: new THREE.Color(0x050916) },
          mid: { value: new THREE.Color(0x1a2352) },
          low: { value: new THREE.Color(0x4b3b72) }
        },
        vertexShader: "varying vec3 vDir; void main(){ vDir = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }",
        fragmentShader: "uniform vec3 top; uniform vec3 mid; uniform vec3 low; varying vec3 vDir;" +
          "void main(){ float h = vDir.y; vec3 c = mix(low, mid, smoothstep(-0.02, 0.18, h)); c = mix(c, top, smoothstep(0.18, 0.7, h)); gl_FragColor = vec4(c,1.0); }"
      })
    );
    sky.renderOrder = -2;
    this.scene.add(sky);

    const starPos = [];
    for (let i = 0; i < 900; i++) {
      const a = Math.random() * Math.PI * 2, y = 0.06 + Math.random() * 0.94, rr = Math.sqrt(1 - y * y);
      starPos.push(Math.cos(a) * rr * 1600, y * 1600, Math.sin(a) * rr * 1600);
    }
    const sg = new THREE.BufferGeometry();
    sg.setAttribute("position", new THREE.Float32BufferAttribute(starPos, 3));
    this.scene.add(new THREE.Points(sg, new THREE.PointsMaterial({ color: 0xffffff, size: 1.6, sizeAttenuation: false, fog: false, transparent: true, opacity: 0.8 })));

    // tree line silhouette all around the horizon
    const trees = canvasTexture(1024, 128, (g, w, h) => {
      g.fillStyle = "#08130e";
      g.beginPath(); g.moveTo(0, h);
      for (let x = 0; x <= w; x += 6) {
        const top = h * (0.45 + 0.18 * Math.sin(x * 0.013) + 0.12 * Math.sin(x * 0.051 + 2) + 0.08 * Math.random());
        g.lineTo(x, top);
      }
      g.lineTo(w, h); g.closePath(); g.fill();
    });
    trees.wrapS = THREE.RepeatWrapping; trees.repeat.set(6, 1);
    const treeRing = new THREE.Mesh(
      new THREE.CylinderGeometry(1300, 1300, 90, 64, 1, true),
      new THREE.MeshBasicMaterial({ map: trees, transparent: true, side: THREE.BackSide, fog: false, depthWrite: false })
    );
    treeRing.position.y = 30;
    treeRing.renderOrder = -1;
    this.scene.add(treeRing);
  }

  buildGround() {
    const tex = canvasTexture(256, 256, (g, w, h) => {
      g.fillStyle = "#2f7d45"; g.fillRect(0, 0, w, h / 2);
      g.fillStyle = "#28703d"; g.fillRect(0, h / 2, w, h / 2);
      for (let i = 0; i < 5000; i++) {
        g.fillStyle = Math.random() < 0.5 ? "rgba(0,0,0,0.06)" : "rgba(255,255,255,0.04)";
        g.fillRect(Math.random() * w, Math.random() * h, 1, 2);
      }
    });
    tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
    tex.repeat.set(2400 / 20, 2400 / 20);
    tex.anisotropy = this.renderer.capabilities.getMaxAnisotropy();
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(2400, 2400),
      new THREE.MeshStandardMaterial({ map: tex, roughness: 0.95, metalness: 0 })
    );
    ground.rotation.x = -Math.PI / 2;
    ground.position.z = -300;
    ground.receiveShadow = true;
    this.scene.add(ground);

    // faint yardage lines
    const lineMat = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.12, depthWrite: false });
    for (let d = 50; d < FIELD_DEPTH; d += 50) {
      const m = new THREE.Mesh(new THREE.PlaneGeometry(FIELD_WIDTH * 2, 0.35), lineMat);
      m.rotation.x = -Math.PI / 2;
      m.position.set(0, 0.01, -d);
      this.scene.add(m);
    }
  }

  buildNets() {
    const grid = canvasTexture(64, 64, (g, w) => {
      g.strokeStyle = "rgba(220,230,255,0.55)"; g.lineWidth = 2;
      g.strokeRect(0, 0, w, w);
    });
    grid.wrapS = grid.wrapT = THREE.RepeatWrapping;
    const netMat = (len) => {
      const t = grid.clone(); t.needsUpdate = true;
      t.repeat.set(len / 2.5, 26 / 2.5);
      return new THREE.MeshBasicMaterial({ map: t, transparent: true, opacity: 0.45, side: THREE.DoubleSide, depthWrite: false });
    };
    [-1, 1].forEach((side) => {
      const net = new THREE.Mesh(new THREE.PlaneGeometry(FIELD_DEPTH + 10, 26), netMat(FIELD_DEPTH + 10));
      net.rotation.y = Math.PI / 2;
      net.position.set(side * FIELD_WIDTH, 13, -(FIELD_DEPTH - 10) / 2);
      this.scene.add(net);
    });
    const back = new THREE.Mesh(new THREE.PlaneGeometry(FIELD_WIDTH * 2, 26), netMat(FIELD_WIDTH * 2));
    back.position.set(0, 13, -FIELD_DEPTH);
    this.scene.add(back);

    const poles = [];
    for (let d = 0; d <= FIELD_DEPTH; d += 30) poles.push([d, -FIELD_WIDTH], [d, FIELD_WIDTH]);
    for (let l = -FIELD_WIDTH + 28; l < FIELD_WIDTH; l += 28) poles.push([FIELD_DEPTH, l]);
    const pm = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.22, 0.32, 27, 8),
      new THREE.MeshStandardMaterial({ color: 0x9aa3b5, roughness: 0.6, metalness: 0.4 }), poles.length);
    const m = new THREE.Matrix4();
    poles.forEach((p, i) => { m.makeTranslation(p[1], 13.5, -p[0]); pm.setMatrixAt(i, m); });
    pm.castShadow = true;
    this.scene.add(pm);
  }

  buildLights() {
    this.scene.add(new THREE.HemisphereLight(0x7d8cff, 0x1b3a25, 0.65));
    const key = new THREE.DirectionalLight(0xfff1dc, 1.7);
    key.position.set(40, 140, 60);
    key.target.position.set(0, 0, -130);
    key.castShadow = this.high;
    key.shadow.mapSize.set(2048, 2048);
    Object.assign(key.shadow.camera, { left: -80, right: 80, top: 200, bottom: -200, near: 10, far: 500 });
    key.shadow.bias = -0.0008;
    this.scene.add(key, key.target);

    // light towers along both sides - the glowing heads sell the night range look
    const glow = glowTexture();
    const poleGeo = new THREE.CylinderGeometry(0.35, 0.5, 30, 8);
    const poleMat = new THREE.MeshStandardMaterial({ color: 0x6f7787, metalness: 0.5, roughness: 0.5 });
    const headGeo = new THREE.BoxGeometry(5, 2.2, 0.6);
    const headMat = new THREE.MeshBasicMaterial({ color: new THREE.Color(2.6, 2.5, 2.2), toneMapped: false });
    [20, 110, 200].forEach((d) => [-1, 1].forEach((side) => {
      const x = side * (FIELD_WIDTH + 8);
      const pole = new THREE.Mesh(poleGeo, poleMat);
      pole.position.set(x, 15, -d);
      pole.castShadow = true;
      const head = new THREE.Mesh(headGeo, headMat);
      head.position.set(x, 30.5, -d);
      head.lookAt(0, 0, -d - 30);
      const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: glow, color: 0xfff4dd, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0.7 }));
      halo.position.copy(head.position);
      halo.scale.set(9, 9, 1);
      this.scene.add(pole, head, halo);
    }));
  }

  buildSigns() {
    for (let d = 50; d < FIELD_DEPTH; d += 50) {
      const tex = canvasTexture(256, 128, (g, w, h) => {
        g.fillStyle = "#f4f6f2"; g.fillRect(0, 0, w, h);
        g.fillStyle = "#1c3a29"; g.fillRect(6, 6, w - 12, h - 12);
        g.fillStyle = "#ffffff";
        g.font = "900 84px Segoe UI, Arial, sans-serif";
        g.textAlign = "center"; g.textBaseline = "middle";
        g.fillText(String(d), w / 2, h / 2 + 4);
      });
      [-1, 1].forEach((side) => {
        const sign = new THREE.Mesh(new THREE.PlaneGeometry(7, 3.5), new THREE.MeshBasicMaterial({ map: tex }));
        sign.position.set(side * (FIELD_WIDTH - 7), 3, -d);
        const post = new THREE.Mesh(new THREE.BoxGeometry(0.3, 1.5, 0.3), new THREE.MeshStandardMaterial({ color: 0x444444 }));
        post.position.set(side * (FIELD_WIDTH - 7), 0.6, -d);
        this.scene.add(sign, post);
      });
    }
  }

  badgeTexture(T) {
    return canvasTexture(128, 128, (g, w) => {
      g.beginPath(); g.arc(w / 2, w / 2, w / 2 - 6, 0, Math.PI * 2);
      g.fillStyle = T.color; g.fill();
      g.lineWidth = 8; g.strokeStyle = "#ffffff"; g.stroke();
      g.fillStyle = T.color === "#f2f2f2" || T.color === "#ffd23f" ? "#1a1a1a" : "#ffffff";
      g.font = "900 72px Segoe UI, Arial, sans-serif";
      g.textAlign = "center"; g.textBaseline = "middle";
      g.fillText(String(T.pts), w / 2, w / 2 + 4);
    });
  }

  buildTargets() {
    this.targetObjs = this.targets.map((T) => {
      const color = new THREE.Color(T.color);
      const grp = new THREE.Group();
      grp.position.set(T.l, 0, -T.d);
      const flat = (geo, mat, y) => {
        const m = new THREE.Mesh(geo, mat);
        m.rotation.x = -Math.PI / 2; m.position.y = y; m.receiveShadow = true;
        grp.add(m); return m;
      };
      const baseMat = new THREE.MeshStandardMaterial({ color: color.clone().multiplyScalar(0.28), emissive: color, emissiveIntensity: 0.06, roughness: 0.9 });
      const innerMat = new THREE.MeshStandardMaterial({ color: color.clone().multiplyScalar(0.55), emissive: color, emissiveIntensity: 0.18, roughness: 0.8 });
      flat(new THREE.CircleGeometry(T.r, 72), baseMat, 0.02);
      flat(new THREE.CircleGeometry(T.r * this.inner, 56), innerMat, 0.04);
      flat(new THREE.CircleGeometry(this.center, 32), new THREE.MeshStandardMaterial({ color: 0x8a8a8a, emissive: 0xffffff, emissiveIntensity: 0.06 }), 0.06);
      flat(new THREE.CircleGeometry(0.55, 24), new THREE.MeshBasicMaterial({ color: 0x050505 }), 0.08);

      const rimMat = new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 1.8, roughness: 0.4 });
      const rim = new THREE.Mesh(new THREE.TorusGeometry(T.r, 0.16, 8, 128), rimMat);
      rim.rotation.x = Math.PI / 2; rim.position.y = 0.12;
      const innerRim = new THREE.Mesh(new THREE.TorusGeometry(T.r * this.inner, 0.09, 6, 96), rimMat);
      innerRim.rotation.x = Math.PI / 2; innerRim.position.y = 0.1;
      grp.add(rim, innerRim);

      const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 4.2, 6), new THREE.MeshStandardMaterial({ color: 0xffffff }));
      pole.position.y = 2.1; pole.castShadow = true;
      const flagGeo = new THREE.PlaneGeometry(1.6, 1, 12, 2);
      flagGeo.translate(0.8, 0, 0);
      const flag = new THREE.Mesh(flagGeo, new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0.5, side: THREE.DoubleSide }));
      flag.position.y = 3.7;
      flag.userData.base = flagGeo.attributes.position.array.slice();
      grp.add(pole, flag);

      // slightly dimmed so the bloom pass leaves the numbers crisp
      const badge = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.badgeTexture(T), color: 0xd0d0d0, transparent: true, depthWrite: false }));
      badge.position.y = 6.5;
      grp.add(badge);

      const beacon = new THREE.Mesh(
        new THREE.CylinderGeometry(T.r * 0.92, T.r * 0.92, 60, 48, 1, true),
        new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.08, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide })
      );
      beacon.position.y = 30;
      beacon.visible = false;
      grp.add(beacon);

      this.scene.add(grp);
      return { T, grp, rimMat, flag, badge, beacon, flash: 0 };
    });
  }

  buildBay() {
    const floor = new THREE.Mesh(new THREE.BoxGeometry(16, 0.4, 9), new THREE.MeshStandardMaterial({ color: 0x3a3f47, roughness: 0.9 }));
    floor.position.set(0, -0.2, 5.3);
    floor.receiveShadow = true;
    const mat = new THREE.Mesh(new THREE.BoxGeometry(3.2, 0.06, 1.8), new THREE.MeshStandardMaterial({ color: 0x1f5a2f, roughness: 1 }));
    mat.position.set(0, 0.03, 0.2);
    const edge = new THREE.Mesh(new THREE.BoxGeometry(16, 0.5, 0.25), new THREE.MeshStandardMaterial({ color: 0xffd23f, emissive: 0xffd23f, emissiveIntensity: 0.4 }));
    edge.position.set(0, 0.05, 0.85);
    this.scene.add(floor, mat, edge);
  }

  buildBall() {
    this.ball = new THREE.Mesh(new THREE.SphereGeometry(1, 24, 16),
      new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xffffff, emissiveIntensity: 0.45, roughness: 0.3 }));
    this.blob = new THREE.Mesh(new THREE.CircleGeometry(1, 24),
      new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.45, depthWrite: false }));
    this.blob.rotation.x = -Math.PI / 2;
    this.scene.add(this.ball, this.blob);
  }

  buildTracer() {
    this.tracerMat = new THREE.MeshBasicMaterial({ color: 0xffffff, toneMapped: false, transparent: true, opacity: 0.95 });
    this.tracer = new THREE.Mesh(new THREE.BufferGeometry(), this.tracerMat);
    this.tracer.frustumCulled = false;
    this.scene.add(this.tracer);
  }

  setTracer(shot, color) {
    const pts = shot.flight.points.map((q) => toV([q[0], q[1], q[2] / 3]));
    pts[pts.length - 1] = toV([shot.flight.carry_yd, shot.flight.offline_yd, 0]);
    if (pts.length < 2) pts.push(pts[0].clone().add(new THREE.Vector3(0, 0.01, -0.01)));
    const curve = new THREE.CatmullRomCurve3(pts);
    this.tracer.geometry.dispose();
    this.tracer.geometry = new THREE.TubeGeometry(curve, TRACER_SEGMENTS, 0.06, TRACER_RADIAL, false);
    this.tracerMat.color.set(color).multiplyScalar(1.6);
    this.tracer.geometry.setDrawRange(0, 0);
  }

  buildParticles() {
    const n = 260;
    this.pCount = n;
    this.pVel = new Float32Array(n * 3);
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(n * 3), 3));
    g.setAttribute("color", new THREE.BufferAttribute(new Float32Array(n * 3), 3));
    this.pMat = new THREE.PointsMaterial({ size: 0.35, map: glowTexture(), vertexColors: true, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false });
    this.particles = new THREE.Points(g, this.pMat);
    this.particles.frustumCulled = false;
    this.scene.add(this.particles);
    this.pAge = 99;
  }

  burst(at, colors, power) {
    const pos = this.particles.geometry.attributes.position, col = this.particles.geometry.attributes.color;
    const c = colors.map((x) => new THREE.Color(x).multiplyScalar(2));
    for (let i = 0; i < this.pCount; i++) {
      pos.setXYZ(i, at.x, at.y + 0.2, at.z);
      const a = Math.random() * Math.PI * 2, s = (2 + Math.random() * 5) * power;
      this.pVel[i * 3] = Math.cos(a) * s;
      this.pVel[i * 3 + 1] = (6 + Math.random() * 9) * power;
      this.pVel[i * 3 + 2] = Math.sin(a) * s;
      const cc = c[i % c.length];
      col.setXYZ(i, cc.r, cc.g, cc.b);
    }
    pos.needsUpdate = col.needsUpdate = true;
    this.pAge = 0;
  }

  buildMarkers() {
    const geo = new THREE.SphereGeometry(0.3, 12, 8);
    this.markers = [];
    for (let i = 0; i < 40; i++) {
      const m = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xffffff, emissiveIntensity: 0.4 }));
      m.visible = false;
      this.scene.add(m);
      this.markers.push(m);
    }
  }

  /* Golf Cornhole: the board (positions from the server, in yards) and a pool of bags. */
  setCornhole(info) {
    const key = JSON.stringify(info);
    if (this.cornhole && this.cornhole.key === key) return;
    if (this.cornhole) this.scene.remove(this.cornhole.group);
    const group = new THREE.Group();
    const slope = info.slope_deg * Math.PI / 180;
    const n = new THREE.Vector3(0, Math.cos(slope), Math.sin(slope));  // the top's normal
    const top = toV(info.center);
    const wood = new THREE.MeshStandardMaterial({ color: 0x8a5a2b, roughness: 0.8 });
    const paint = new THREE.MeshStandardMaterial({ color: 0x1d4f91, roughness: 0.55 });
    const box = (w, h, d, mat, center) => {
      const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
      m.rotation.x = slope;
      m.position.copy(center);
      m.castShadow = m.receiveShadow = true;
      group.add(m);
      return m;
    };
    // the 2x4 frame, then the painted top a little inside it
    box(info.width, info.frame, info.length, wood, top.clone().addScaledVector(n, -info.frame / 2 - 0.002 * info.length));
    box(info.width * 0.94, info.bag_t * 0.3, info.length * 0.97, paint, top.clone().addScaledVector(n, -info.bag_t * 0.15));
    const stripe = box(info.width * 0.94, info.bag_t * 0.31, info.length * 0.05,
      new THREE.MeshStandardMaterial({ color: 0xf2f2f2, roughness: 0.6 }),
      top.clone().add(new THREE.Vector3(0, Math.sin(slope), -Math.cos(slope)).multiplyScalar(info.length * 0.3))
        .addScaledVector(n, -info.bag_t * 0.15));
    stripe.castShadow = false;
    const hole = new THREE.Mesh(new THREE.CircleGeometry(info.hole_r, 48), new THREE.MeshBasicMaterial({ color: 0x050505 }));
    hole.rotation.x = -Math.PI / 2 + slope;
    hole.position.copy(toV(info.hole)).addScaledVector(n, 0.002 * info.length + info.bag_t * 0.02);
    group.add(hole);
    // back legs
    const legH = info.back[2] - 1.5 * info.frame;  // up to the underside of the frame
    [-1, 1].forEach((side) => {
      const leg = new THREE.Mesh(new THREE.BoxGeometry(info.frame * 0.8, legH, info.frame * 0.8), wood);
      leg.position.set(side * info.width * 0.42, legH / 2, -(info.back[0] - 1.5 * info.frame));
      leg.castShadow = true;
      group.add(leg);
    });
    const bags = [];
    const bagGeo = new THREE.BoxGeometry(info.bag, info.bag_t, info.bag);
    for (let i = 0; i < 12; i++) {
      const m = new THREE.Mesh(bagGeo, new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.95 }));
      m.castShadow = m.receiveShadow = true;
      m.visible = false;
      m.rotation.order = "XYZ";
      group.add(m);
      bags.push(m);
    }
    this.scene.add(group);
    this.cornhole = { key, group, bags };
  }

  showCornhole(c) {
    const on = !!c;
    if (on) this.setCornhole(c.board);
    if (this.cornhole) this.cornhole.group.visible = on;
    this.targetObjs.forEach((o) => { o.grp.visible = !on; });
    if (!on) return;
    this.cornhole.bags.forEach((m, i) => {
      const b = c.bags[i];
      m.visible = !!(b && b.pose[5]);
      if (!m.visible) return;
      const p = b.pose;
      m.position.copy(toV(p));
      m.rotation.set(p[4] * Math.PI / 180, -p[3] * Math.PI / 180, 0);
      m.scale.setScalar(p[6] || 1);
      m.material.color.set(b.color);
    });
  }

  /* ---------------- per frame ---------------- */

  resize(w, h) {
    if (w === this.size[0] && h === this.size[1]) return;
    this.size = [w, h];
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / Math.max(1, h);
    this.camera.updateProjectionMatrix();
    if (this.composer) {
      this.composer.setSize(w, h);
      this.bloom.setSize(w, h);
    }
  }

  /* frame: {now (ms), plan (GarageShotPlan.player), wall (s), shot, shotId, color, highlight, markers:[{p,color}]} */
  render(frame) {
    const now = frame.now;
    const dt = clamp((now - (this.lastNow || now)) / 1000, 0, 0.1);
    this.lastNow = now;
    const plan = frame.plan;
    const ch = frame.cornhole;
    this.showCornhole(ch);

    if (frame.shotId !== this.shotId) {
      this.shotId = frame.shotId;
      this.cupDone = false;
      if (frame.shot && !ch) this.setTracer(frame.shot, frame.color);
      else this.tracer.geometry.setDrawRange(0, 0);
    }

    // ball
    let ballPos = [0, 0, 0], ballVisible = true;
    if (plan) {
      const b = plan.ball(frame.wall);
      ballPos = b.pos; ballVisible = b.visible;
      const prog = plan.tracerProgress(frame.wall);
      this.tracer.geometry.setDrawRange(0, ch ? 0 : Math.floor(prog * TRACER_SEGMENTS) * TRACER_RADIAL * 6);
      if (b.phase === "cup" && !this.cupDone) {
        this.cupDone = true;
        const cupAt = toV(b.pos);
        const hitObj = this.targetObjs.find((o) => Math.abs(o.T.d - b.pos[0]) < 0.5 && Math.abs(o.T.l - b.pos[1]) < 0.5);
        if (hitObj) hitObj.flash = 1;
        const big = plan.drama && plan.drama.celebrate;
        this.burst(cupAt, big ? ["#ffd23f", "#ff6b6b", "#4ea8ff", "#3ddc84", "#c77dff"] : [hitObj ? hitObj.T.color : "#ffffff", "#ffffff"], big ? 1.5 : 1);
      }
    }

    // camera (the server's plan already includes the camera smoothing)
    let cam;
    if (plan) {
      cam = plan.camera(frame.wall);
      this.camKey = frame.shotId + ":" + cam.cut;
      this.camera.position.copy(toV(cam.pos));
      this.look.copy(toV(cam.look));
    } else {
      const idle = ch ? ch.idleCamera : this.idleCamera;
      cam = { pos: idle.pos.slice(), look: idle.look.slice(), fov: idle.fov };
      if (!ch) {  // the golfer's cornhole view stays still: it is life-size on the screen
        cam.pos[1] += Math.sin(now / 9000) * 3;
        cam.pos[2] += Math.sin(now / 7000) * 1.2;
      }
      const key = ch ? "idle-cornhole" : "idle";
      const want = toV(cam.pos);
      if (this.camKey !== key) { this.camera.position.copy(want); this.look.copy(toV(cam.look)); }
      else this.camera.position.lerp(want, 1 - Math.exp(-2 * dt));
      this.camKey = key;
    }
    if (this.camera.fov !== cam.fov) { this.camera.fov = cam.fov; this.camera.updateProjectionMatrix(); }
    this.camera.lookAt(this.look);

    // ball size: a real ball is tiny, so grow it with distance to stay visible
    const bp = toV(ballPos);
    const camDist = this.camera.position.distanceTo(bp);
    const rad = clamp(camDist * 0.0045, 0.03, 0.6);
    this.ball.visible = this.blob.visible = ballVisible && !ch;  // in cornhole the bags are the ball
    this.ball.scale.setScalar(rad);
    this.ball.position.set(bp.x, Math.max(bp.y, 0) + rad, bp.z);
    this.blob.position.set(bp.x, 0.03, bp.z);
    this.blob.scale.setScalar(rad * 1.3 * (1 + bp.y * 0.02));
    this.blob.material.opacity = clamp(0.5 - bp.y * 0.01, 0.1, 0.5);

    // targets: highlight, flash, waving flags, badges sized for the camera
    const t = now / 1000;
    this.targetObjs.forEach((o, i) => {
      const hl = frame.highlight === i, dim = frame.highlight >= 0 && !hl;
      o.flash = Math.max(0, o.flash - dt * 0.7);
      o.rimMat.emissiveIntensity = (dim ? 0.35 : hl ? 2.2 + Math.sin(t * 5) * 0.8 : 1.8) + o.flash * 6;
      o.beacon.visible = hl || o.flash > 0;
      o.beacon.material.opacity = 0.06 + o.flash * 0.25 + (hl ? 0.04 * Math.sin(t * 4) : 0);
      o.badge.material.opacity = dim ? 0.35 : 1;
      const d = this.camera.position.distanceTo(o.grp.position);
      const s = clamp(d * 0.04, 2.2, 13);
      o.badge.scale.set(s, s, 1);
      o.badge.position.y = 4.6 + s * 0.6;
      const arr = o.flag.geometry.attributes.position.array, base = o.flag.userData.base;
      for (let k = 0; k < arr.length; k += 3) {
        const x = base[k];
        arr[k + 2] = base[k + 2] + Math.sin(t * 4 + x * 3 + i) * 0.12 * x;
      }
      o.flag.geometry.attributes.position.needsUpdate = true;
    });

    // landing markers from earlier shots
    const mk = frame.markers || [];
    this.markers.forEach((m, i) => {
      const info = mk[i];
      m.visible = !!info;
      if (!info) return;
      m.position.set(info.p[1], 0.3, -info.p[0]);
      m.material.color.set(info.color);
      m.material.emissive.set(info.color);
    });

    // particles
    if (this.pAge < 3) {
      this.pAge += dt;
      const pos = this.particles.geometry.attributes.position;
      for (let i = 0; i < this.pCount; i++) {
        this.pVel[i * 3 + 1] -= 10.7 * dt;
        pos.setXYZ(i, pos.getX(i) + this.pVel[i * 3] * dt, Math.max(0.05, pos.getY(i) + this.pVel[i * 3 + 1] * dt), pos.getZ(i) + this.pVel[i * 3 + 2] * dt);
      }
      pos.needsUpdate = true;
      this.pMat.opacity = clamp(1 - this.pAge / 2.2, 0, 1);
    }

    if (this.composer) this.composer.render();
    else this.renderer.render(this.scene, this.camera);
  }
}

window.GarageRangeGL = {
  create(canvas, opts) { return new RangeGL(canvas, opts); }
};
window.dispatchEvent(new Event("garage-gl-ready"));
