# Dig van-phong-ao-3d — patterns áp vào claude-live-dashboard

**Repo gốc**: `~/Downloads/van-phong-ao-3d/` (public MIT, VinAIChatBot/vinaichatbot-rgb — fork từ VinMKTHub).
**Mục đích gốc**: biến các phiên Claude Code + Codex thành công ty AI 3D sống động, có 8 phòng, bàn, nhân viên robot, tin bay giữa bàn, họp tự động.
**Phạm vi áp cho dashboard**: KHÔNG clone full office simulator — chỉ lấy đúng patterns phù hợp với bối cảnh dashboard observability (giữ main focus là data, không entertainment).

---

## 1. Phân việc giữa các vai

File `mau/DOI-NGU.md` + `mau/CAP-BAC.md` định nghĩa cơ cấu:

```
Chủ văn phòng (ba) → Quản lý → Điều phối → Kỹ sư (Backend / Frontend / QA)
```

- **Chủ (ceo)**: quyết production, tiền ngoài trần, khóa/secret mới, xóa dữ liệu thật, đổi luật. Hỏi qua sổ "Cần anh".
- **Quản lý (manager, Claude)**: giữ thứ tự việc, giao việc, duyệt, báo cáo chủ. KHÔNG tự code.
- **Điều phối (coord, Claude)**: chia việc cho kỹ sư, gỡ chặn, giữ hàng chờ DEV.
- **Kỹ sư Backend (codex)**: API, database.
- **Kỹ sư Frontend (codex)**: giao diện.
- **Kiểm tra QA (claude)**: chạy thử thật, duyệt gói trước khi lên DEV.

Phòng được tự detect từ tên phiên qua heuristic (file `README.md` phần "Phụ lục C"):
- có từ "quản lý / manager / lead" → Phòng Quản lý;
- "điều phối / trợ lý / coordinator" → Phòng Điều phối;
- "review / duyệt / kiểm tra / test / QA" → Kiểm tra & duyệt;
- còn lại → Studio Claude hoặc Khu Codex (tuỳ platform).

**Thứ tự việc**: `mau/UU-TIEN.json` — một nguồn duy nhất, chỉ Quản lý/Điều phối sửa bằng `vp viec`. Format:

```json
{
  "dang_lam": [
    {"thu_tu": 1, "viec": "...", "chu": "<vai>", "muc": ["<gói>:<MÃ>"], "han": "..."}
  ],
  "tam_dung": []
}
```

**Hệ ưu tiên**: dãy `dang_lam` SẮP XẾP SẴN theo `thu_tu` ↑. Không có weight/score — flat ordered list, Quản lý quyết thứ tự.

---

## 2. Flow pipeline live — session trigger event thế nào

Server (`server.js` + `lib/`) **chỉ đọc**:
- `~/.claude/projects/<slug>/*.jsonl` — Claude Code sessions
- `~/.codex/sessions/*.json` — Codex sessions
- `data/*` — sổ điều phối

Mỗi 1 giây đẩy trạng thái tổng hợp qua endpoint `/state` (dashboard thì poll).

### Robot "đi lại" khi tin nhắn gửi (lib `fly()` trong `public/index.html`)

Khi phát hiện event tin nhắn giữa 2 phiên (SendMessage từ Claude, `[PEER MESSAGE]` từ Codex):

1. Người gửi `A` **đứng dậy đi sang bàn người nhận `B`**, nói đủ nội dung, rồi quay về. Set `A.visit = {to: e.to, until: Date.now() + 16000}`.
2. Vẽ `QuadraticBezierCurve3(A, mid, B)` với `mid.y = 10 + distance*0.14` (parabola bay cao).
3. Vẽ **đường chấm chạy** (LineDashedMaterial) từ A→B.
4. Spawn orb `SphereGeometry` + `PointLight` ở mid-arc để sáng.
5. Tooltip `.ml` label gắn với `CSS2DObject` ở midpoint hiển thị 52-char title.
6. Màu theo kind: `ceo` → `#ecc970` vàng, `GẤP|CHẶN` → `#e8a39b` đỏ, còn lại → `#7ccf9b` xanh.

### Phòng DEV lock — hàng chờ

`data/DEV.lock` + `data/DEV-LUOT.jsonl`:
- `vp luot cho --goi <gói> --vai <vai>` → xếp hàng chờ.
- `vp luot lay --goi <gói> --vai <vai>` → lấy lượt, ghi lock.
- `vp luot nha --vai <vai> --ket-qua dat|hong [--usd 0.3]` → nhả, log kết quả + tiền.

Trong 3D: ai đang giữ DEV đứng giữa `Phòng DEV`, có `TorusGeometry` ring hào quang xoay quanh + `OctahedronGeometry` holo bay bên trên. Ai chờ xếp hàng tuyến tính.

### Phòng họp — khi nào tụ tập (lib `handle()` + `startMeet()`)

4 loại họp tự động trigger:
- **ceo**: chủ giao việc, có `from === "ceo"` hoặc `to === "ceo"` → kéo cả Quản lý + Điều phối + người nhận vào.
- **incident**: tin có `GẤP|CHẶN|sự cố` → người báo + người nhận.
- **review**: tin có `REVIEW|duyệt` → người nộp + người duyệt.
- **assign**: cùng người gửi gửi cho ≥2 người trong 5 phút → cả nhóm.

Trong họp: Bezier curve `arc()` dẫn người đi vòng quanh bàn (không xuyên qua bàn), ngồi vào `SLOT(i)` theo radius 8.8 (ghế) hoặc 11.2 (chỗ đứng). Chủ trì đọc từng việc, người nhận xác nhận. Hết giờ chốt "ai làm gì" rồi về bàn.

### Message bay giữa desks — rendering

```js
const curve = new THREE.QuadraticBezierCurve3(p0, p1, p2);
const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(curve.getPoints(48)),
  new THREE.LineDashedMaterial({color: col, dashSize: .6, gapSize: .45, transparent: true, opacity: .8}));
line.computeLineDistances();
const orb = new THREE.Mesh(new THREE.SphereGeometry(0.45, 16, 12), new THREE.MeshBasicMaterial({color: col}));
orb.add(new THREE.PointLight(col, 6, 12));
// Animate t 0→1 along curve, update orb.position.copy(curve.getPointAt(t))
```

Timing: 2.5-3.5s cho 1 chuyến bay (ease), orb fade-out ở điểm đến. Label gắn ở midpoint cao để không che bàn.

---

## 3. Scene composition — 8 phòng + camera

### Layout 8 phòng (bảng ROOMS trong `public/index.html`)

```js
const ROOMS = [
  { id: "ceo",     label: "Phòng Giám đốc",   x: 20,  y: 20,  w: 220, h: 170, tone: 0x8a6a3a },
  { id: "manager", label: "Phòng Quản lý",    x: 256, y: 20,  w: 240, h: 170, tone: 0x5c6470 },
  { id: "coord",   label: "Phòng Điều phối",  x: 512, y: 20,  w: 350, h: 170, tone: 0x5c6470 },
  { id: "g1",      label: "Kiểm tra & duyệt", x: 878, y: 20,  w: 302, h: 300, tone: 0x4d6a86 },
  { id: "claude",  label: "Studio Claude",    x: 20,  y: 206, w: 390, h: 250, tone: 0x8a5a44 },
  { id: "dev",     label: "Phòng DEV",        x: 426, y: 206, w: 436, h: 250, tone: 0x3a3a40 },
  { id: "codex",   label: "Khu kỹ sư Codex",  x: 20,  y: 472, w: 842, h: 290, tone: 0x3f5a78 },
  { id: "lounge",  label: "Phòng họp",        x: 878, y: 336, w: 302, h: 426, tone: 0x6a6e74 },
];
```

Phòng = thảm BoxGeometry với carpetTex + 3 vách kính (glassWall) + nhãn CSS2DObject.

### Camera + lighting

```js
camera = new THREE.PerspectiveCamera(45, 1, 0.1, 800);
HOME_CAM = { pos: (0, 58, 158), target: (0, 32, -20) };  // nhìn cao: 3 màn hình chiếm nửa trên, văn phòng nửa dưới
controls.maxPolarAngle = 1.38;  // không cho ngóc lên qua trần
controls.minDistance = 14; controls.maxDistance = 340;

scene.fog = new THREE.Fog(0x0a0e14, 300, 520);
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
scene.add(new THREE.HemisphereLight(0xdfe8ff, 0x2a1f16, 0.35));
const key = new THREE.DirectionalLight(0xfff1dc, 1.7);
key.position.set(-60, 110, 70); key.castShadow = true;
key.shadow.mapSize.set(2048, 2048);
```

Materials: wood texture canvas (`woodTex`) procedural với HSL rows + grain lines. Carpet texture noise. Glass pha trộn với `transparent + opacity 0.16 + depthWrite:false`.

### 3 màn hình lớn trong văn phòng (CSS3D iframe trick)

Mỗi màn hình = `PlaneGeometry` trong suốt (hole) + `CSS3DObject(iframe)` cùng vị trí + rotation. Cho phép **click vào iframe trực tiếp** từ view 3D, không cần `postMessage`.

```js
function wallScreen(cfg) {
  const hole = new THREE.Mesh(new THREE.PlaneGeometry(w, h), 
    new THREE.MeshBasicMaterial({color: 0, opacity: 0, blending: THREE.NoBlending}));
  const ifr = document.createElement("iframe"); ifr.src = page;
  const obj = new CSS3DObject(ifr); obj.scale.setScalar(w / pxw);
  cssScene.add(obj);
}
```

3 lớp vẽ: `CSS3DRenderer` (iframe màn hình dưới) + `WebGLRenderer alpha:true` (giữa) + `CSS2DRenderer` (nhãn trên).

---

## 4. Hệ sổ điều phối

### UU-TIEN.json

Đã mô tả ở §1. 1 nguồn truth, flat ordered.

### Hòm thư JSONL — `data/hop-thu/<vai>.jsonl`

Append-only, 1 dòng = 1 message. Lệnh:
- `vp gui --toi "<vai>" --tu "<vai mình>" "[VIỆC] ..."` → ghi vào hộp người nhận.
- `vp tiep --toi "<vai mình>"` → đọc batch cuối (mỗi lượt).
- `vp xong <mã> --ghi-chu "..."` → đóng tin.
- `vp ds` → liệt kê.

Mỗi phiên AI PHẢI đọc hòm thư cuối mỗi lượt (ép qua `AGENTS.md`/`CLAUDE.md` dán vào).

### Phòng DEV lock

`data/DEV.lock` giữ chủ hiện tại, `data/DEV-LUOT.jsonl` log mọi lượt + kết quả + chi phí.

### Cần anh — `data/CAN-ANH.md`

Markdown có list `## [CA-N] <vai> hỏi: ...` + checkbox hoặc trả lời.

### Tiền AI

Config `prices` (USD/1M token): `claude: {in:3, cache:0.3, out:15}`, `codex: {in:1.25, cache:0.125, out:10}`. Dashboard tính tổng = token × giá + lượt DEV (`vp luot nha --usd 0.3`). Vượt 80% `aiCapUsd` → ô chuyển đỏ.

---

## 5. "Cần anh" & nhịp 3 giờ

**Cần anh** = cách thức báo cho user:
- `vp cananh hoi --tu "<vai>" "..." --lua-chon "a / b"` → tạo entry `CA-N`.
- Dashboard ô "Cần anh" badge số câu hỏi open.
- Dán tag `[CẦN ANH]` vào tin → cũng tính.

**Nhịp 3 giờ** = session renewal — mỗi phiên AI thực thi gần đạt ngưỡng tool call hoặc token, pause để chủ xem. Trong văn phòng ảo render dưới dạng heartbeat visual (robot cúi đầu / ngủ gật ở bàn). Không có code enforcer, chỉ convention.

---

## 6. Top 5 patterns áp cho claude-live-dashboard

### Pattern 1: **Role spawn → "phòng" trigger flash**
Khi stage trigger (review/debug/verify/test) → "phòng" tương ứng flash emissive 1s. BoxGeometry wireframe + CSS2DObject label.

```js
function flashPhong(stage) {
  const p = phongs[stage]; if (!p) return;
  p.material.emissive.setHex({review:0xffb547, debug:0xff5c5a, verify:0x4ad9e4, test:0x22d19a}[stage]);
  p.material.emissiveIntensity = 2.0;
  gsap.to(p.material, {emissiveIntensity: 0.2, duration: 1.0});
}
```

### Pattern 2: **Orbit around central node = subagent spawn**
Agent tree panel: main session = sphere center, subagents/bg orbit CatmullRomCurve3 với `t = i/N`. Tương tự ghế quanh bàn họp (SLOT(i) → ring 8.8).

```js
const n = allAgents.length;
allAgents.forEach((a, i) => {
  const theta = (i / n) * Math.PI * 2;
  const r = 2.4;
  mesh.position.set(Math.cos(theta) * r, 0, Math.sin(theta) * r);
});
```

### Pattern 3: **CSS2DObject label floating** — reusable
Mỗi mesh có label HTML gắn vào trên đỉnh, auto-track position với `labelRenderer.render(scene, camera)`. Mobile-friendly (text sharp, không stretch).

### Pattern 4: **Fallback 2D khi WebGL fail** — probe + swap
```js
let webglOk = true;
try {
  const c = document.createElement('canvas');
  if (!(c.getContext('webgl') || c.getContext('experimental-webgl'))) webglOk = false;
} catch { webglOk = false; }
if (!webglOk) { fallback.style.display = 'block'; return; }
```

Dashboard phải giữ 2D (SVG ring, DOM bars) hidden-via-CSS, show when 3D fail.

### Pattern 5: **Emissive decay animation loop** — persistent liveness
Mỗi mesh có `userData.baseEmissive`, tick giảm `emissiveIntensity` dần về base. Giữ scene luôn "sống" mà không re-render:

```js
function animate() {
  for (const id in nodes) {
    const m = nodes[id];
    const base = m.userData.baseEmissive;
    if (m.material.emissiveIntensity > base) {
      m.material.emissiveIntensity = Math.max(base, m.material.emissiveIntensity - 0.04);
    }
  }
}
```

---

## Áp cho dashboard v13 (quyết định cuối)

**LẤY** (fit observability):
- Pattern 1 — "phòng ảo" wireframe cho Kiểm tra/Dev/Test ở side của pipeline, flash khi stage trigger.
- Pattern 2 — orbit subagents quanh main cho **Agent tree panel 3D**.
- Pattern 3 — CSS2DObject label floating cho mọi panel 3D.
- Pattern 4 — WebGL probe + 2D fallback cho mỗi panel.
- Pattern 5 — emissive decay giữ scene sống.

**BỎ** (ngoài scope dashboard observability):
- Full 8-room office simulator — dashboard là observability pane, không phải entertainment.
- Robot bots với capsule body + head + visor — quá nặng cho 4 panel nhỏ, dùng geometric nodes thay.
- Message bay QuadraticBezierCurve3 giữa bàn — dashboard đã có timeline + edit log + command log, không cần replay.
- Phòng họp họp tự động — chủ trì / member / log cycle quá phức tạp cho use case.
- CSS3DObject iframe màn hình — dashboard không có nested view.
- Hòm thư JSONL + sổ `vp` — dashboard chỉ display, không ghi.

**MỞ RỘNG**:
- Harness skills 3D bar chart (không có trong văn phòng ảo — thêm cho dashboard metrics).
- Event kinds 3D donut (TorusGeometry segments).
- Loops lifecycle 3D ring (TorusGeometry progress rotation).
