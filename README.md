# ✦ Ciel

ผู้ช่วย AI ส่วนตัวที่รันบนเครื่องของเราเอง มีตัวตน มีนิสัย และ (เร็วๆ นี้) มีเสียงกับร่าง Live2D
เปิดเครื่องที่บ้านทิ้งไว้ แล้วคุยกับ Ciel ได้จากมือถือหรือคอมเครื่องไหนก็ได้

```
📱 มือถือ / 💻 คอมเครื่องอื่น ──► Tailscale ──► 🖥️ Mac ที่บ้าน
                                                 ├─ Ciel (หน้าเว็บ + สมอง + นิสัย)
                                                 └─ Ollama (โมเดลภาษา)
```

## เริ่มใช้งาน

> ติดตั้งบน Mac แบบให้ Claude ทำให้: ดู [docs/SETUP_MAC.md](docs/SETUP_MAC.md)

### 1. ติดตั้ง Ollama และโหลดโมเดล

ดาวน์โหลดจาก <https://ollama.com> แล้วรัน:

```bash
ollama pull qwen3:8b
```

> M1/M2 RAM 16GB แนะนำ `qwen3:8b` · อยากได้ภาษาไทยเป็นธรรมชาติขึ้นลองโมเดล Typhoon · RAM 32GB+ ลอง `qwen3:14b` หรือใหญ่กว่า

### 2. รัน Ciel

**macOS / Linux**

```bash
./run.sh
```

**Windows**

```powershell
.\run.ps1
```

ครั้งแรกจะสร้าง `.venv`, ติดตั้ง dependency และคัดลอก `.env.example` เป็น `.env` ให้อัตโนมัติ
จากนั้นเปิด <http://localhost:8080>

> ยังไม่มี Ollama? ตั้ง `CIEL_LLM=mock` ใน `.env` เพื่อลองหน้า UI ได้ก่อน

## ปรับนิสัย Ciel

ทุกอย่างอยู่ใน [`persona/ciel.yaml`](persona/ciel.yaml) — ชื่อ วิธีเรียกเรา คำลงท้าย นิสัย กฎ และตัวอย่างบทสนทนา
แก้แล้วกดปุ่ม **＋ (แชทใหม่)** ในหน้าเว็บ มีผลทันที ไม่ต้องรีสตาร์ท

เคล็ดลับ: **ตัวอย่างบทสนทนา (`examples`) มีผลต่อนิสัยมากที่สุด** โดยเฉพาะกับโมเดลขนาดเล็ก
ถ้า Ciel พูดไม่เหมือนที่อยากได้ ให้เพิ่มตัวอย่างที่ตอบแบบที่ต้องการแทนการเขียนคำบรรยายยาวๆ

## คุยจากมือถือ / ที่ไหนก็ได้

1. ติดตั้ง [Tailscale](https://tailscale.com) บนเครื่องที่รัน Ciel และบนมือถือ ล็อกอินบัญชีเดียวกัน
2. บนเครื่องที่รัน Ciel:
   ```bash
   tailscale serve --bg 8080
   ```
3. เปิด `https://<ชื่อเครื่อง>.<tailnet>.ts.net` จากมือถือ แล้วกด **เพิ่มลงหน้าจอหลัก** จะได้ Ciel เป็นแอป

ใช้ HTTPS ของ Tailscale เพราะเบราว์เซอร์อนุญาตให้ใช้ไมโครโฟนเฉพาะบน HTTPS (จำเป็นตอนเพิ่มระบบเสียง)
แนะนำให้ตั้ง `CIEL_PASSWORD` ใน `.env` ด้วย

### เปิด Mac ทิ้งไว้

- System Settings → Battery → Options → เปิด *Prevent automatic sleeping when the display is off*
- พับจอ: ใช้แอป **Amphetamine** (โหมด Closed-Display)
- ถนอมแบต: ใช้ **AlDente** จำกัดการชาร์จที่ 80%

## เวอร์ชันและการอัปเดต

- เวอร์ชันอยู่ในไฟล์ [`VERSION`](VERSION) และแสดงที่แถบล่างของหน้าเว็บเป็น `v0.1.0 · <commit>` ดูประวัติได้ที่ [CHANGELOG.md](CHANGELOG.md)
- บนเครื่องเซิร์ฟเวอร์ ตั้ง `CIEL_AUTO_UPDATE=true` แล้ว push ขึ้น GitHub ได้เลย เซิร์ฟเวอร์จะดึงโค้ดใหม่และโหลดใหม่เอง (รายละเอียดใน [docs/MAC_SERVER.md](docs/MAC_SERVER.md))

## โครงสร้างโปรเจกต์

```
ciel/            backend (FastAPI)
  main.py        API + WebSocket แชท
  persona.py     แปลง persona/*.yaml เป็น system prompt
  llm.py         เชื่อม Ollama (หรือ mock) — เปลี่ยนสมองได้โดยไม่กระทบส่วนอื่น
  updater.py     อัปเดตอัตโนมัติจาก GitHub
  version.py     เวอร์ชัน + commit ที่กำลังรัน
  auth.py        รหัสผ่านหน้าเว็บ
  config.py      อ่านค่าจาก .env
persona/         ไฟล์นิสัยของ Ciel
web/             หน้า UI (PWA ติดตั้งเป็นแอปได้)
  avatar.js      ร่างของ Ciel (ตอนนี้เป็นวงเวท → Live2D จะยืนอยู่หน้าวงเวทในอนาคต)
  live2d/        ที่วางโมเดล Live2D
```

## Roadmap

- [x] **เฟส 1 — Ciel คุยได้ (v0.1):** หน้า UI วงเวท, สตรีมคำตอบ, นิสัยจาก YAML, PWA, รหัสผ่าน, อัปเดตอัตโนมัติ
- [ ] **เฟส 2 — Ciel จำได้:** เก็บประวัติแชท + ความจำระยะยาว (SQLite + vector search)
- [ ] **เฟส 3 — Ciel พูดได้:** TTS ภาษาไทยทีละประโยค (Edge TTS → F5-TTS-THAI เสียงเฉพาะของ Ciel)
- [ ] **เฟส 4 — Ciel ฟังได้:** กดค้างพูด (Whisper) → wake word "Ciel"
- [ ] **เฟส 5 — Ciel มีร่าง:** Live2D + lip sync + แสดงอารมณ์ตามบทสนทนา
- [ ] **เฟส 6 — Ciel ทำงานได้:** tools เช่น ปฏิทิน ไฟล์ ค้นเว็บ แจ้งเตือน
