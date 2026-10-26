# สถานะเซิร์ฟเวอร์ Ciel บน Mac

> บันทึกผลการติดตั้งตาม [SETUP_MAC.md](SETUP_MAC.md) เมื่อ 2026-10-26
> ไว้ให้ฝั่ง Windows (ที่พัฒนาหน้าตาโปรแกรม) รู้ว่าเครื่องเซิร์ฟเวอร์ตั้งค่าไว้อย่างไร และจะส่งงานขึ้นเครื่องจริงได้อย่างไร

## สรุปผล

| หัวข้อ | ค่า |
|---|---|
| เครื่อง | MacBook Apple M1, RAM 16GB, macOS 26.6.2 |
| โมเดล | `qwen3:8b` ผ่าน Ollama (ปิดโหมด think) |
| เวลาตอบ | ข้อความแรกหลังโหลดโมเดล ~24 วินาที, ข้อความถัดไป ~9 วินาที |
| Python | 3.12 (venv ที่ `~/Ciel/.venv`) |
| บนเครื่อง Mac | http://localhost:8080 |
| จากมือถือ/เครื่องอื่น | https://boss-puttipong.tail6857ad.ts.net (ใช้ได้เฉพาะเครื่องที่ล็อกอิน Tailscale บัญชีเดียวกัน) |

**ขั้นที่เสร็จแล้ว:** 1–8 (เครื่องมือ, Ollama, Ciel, `.env`, ทดสอบแชท, LaunchAgent, Tailscale Serve)
**ที่เหลือ:** ทดสอบบนมือถือ Android และตั้งค่าให้ Mac ไม่ sleep (ขั้นที่ 9)

## สิ่งที่ฝั่ง Windows ควรรู้

### ค่าใน `.env` บนเซิร์ฟเวอร์

```
CIEL_LLM=ollama
CIEL_MODEL=qwen3:8b
CIEL_THINK=false
CIEL_HOST=127.0.0.1
CIEL_PORT=8080
CIEL_PASSWORD=<ตั้งไว้แล้ว ไม่เก็บใน repo>
```

- ตั้งรหัสผ่านไว้ หน้าเว็บจึงต้องผ่าน `/api/login` ก่อน และ WebSocket ที่ไม่มี cookie จะถูกปิดด้วยรหัส `4401`
- เซิร์ฟเวอร์ฟังที่ `127.0.0.1` เท่านั้น การเข้าจากข้างนอกต้องผ่าน Tailscale Serve (HTTPS)
- ตอนพัฒนาบน Windows ใช้ `CIEL_LLM=mock` ทดสอบหน้า UI ได้โดยไม่ต้องมีโมเดล

### API ที่หน้าเว็บใช้

| Endpoint | หน้าที่ |
|---|---|
| `GET /api/health` | `{"ok": true, "llm": "ollama", "model": "qwen3:8b"}` |
| `GET /api/me` | เช็กว่าล็อกอินอยู่ไหม |
| `POST /api/login` | ล็อกอินด้วยรหัสผ่าน (ได้ cookie) |
| `WS /ws` | แชท |

ข้อความใน WebSocket:

- ส่งไป: `{"type": "chat", "text": "..."}` และ `{"type": "reset"}` (เริ่มแชทใหม่และโหลด persona ใหม่)
- รับกลับ: `hello` (ชื่อ + คำทักทาย) → `start` → `delta` (ข้อความทีละส่วน) → `end` (คำตอบเต็ม) หรือ `error`

### หน้าเว็บต้องเป็น HTTPS

เบราว์เซอร์บนมือถือจะให้ใช้ไมโครโฟนเฉพาะบน HTTPS ซึ่ง Tailscale Serve จัดการให้แล้ว
ฟีเจอร์ที่ต้องใช้ไมค์ให้ทดสอบผ่าน URL `https://….ts.net` ไม่ใช่ `http://` ตรงๆ

## ส่งงานขึ้นเครื่อง Mac

### ⚠️ ทำครั้งเดียว: เปิดระบบอัปเดตอัตโนมัติ (ตั้งแต่ v0.1.0)

**ถึง Claude บน Mac:** ทำขั้นตอนนี้ครั้งเดียว หลังจากนี้ไม่ต้องรันคำสั่งอัปเดตเองอีก

```bash
cd ~/Ciel && git pull
grep -q '^CIEL_AUTO_UPDATE=' .env || printf '\n# อัปเดตอัตโนมัติจาก GitHub\nCIEL_AUTO_UPDATE=true\n' >> .env
.venv/bin/pip install -q -r requirements.txt
launchctl kickstart -k gui/$(id -u)/com.ciel.server
```

**ตรวจสอบ:**

- `curl -s http://127.0.0.1:8080/api/health` ต้องมี `"version": "0.1.0"` และ `"commit"` ตรงกับ `git rev-parse --short HEAD`
- `grep updater ~/Library/Logs/Ciel.log | tail -3` ต้องเห็น `auto-update on: checking origin/main every 60s`
- ห้ามแก้ไฟล์ใน `~/Ciel` ที่ git ติดตามอยู่ และห้าม commit บน Mac (ยกเว้นไฟล์ docs ที่ push ขึ้นไปทันที) เพราะระบบจะข้ามการอัปเดตถ้ามีการแก้ไฟล์ในเครื่องที่ยังไม่ได้ push

### หลังจากนี้

ฝั่ง Windows push ขึ้น `main` แล้ว Mac จะดึงโค้ดใหม่เองภายใน 1 นาที

| สิ่งที่แก้ | ผล |
|---|---|
| `web/` (หน้าตา) | มีผลทันที หน้าเว็บที่เปิดอยู่จะโหลดใหม่เอง |
| `persona/ciel.yaml` | กด "แชทใหม่" ในหน้าเว็บ |
| `ciel/` (โค้ด Python), `requirements.txt` | Ciel รอให้ตอบข้อความที่ค้างอยู่จบก่อน แล้วรีสตาร์ทตัวเอง (และติดตั้ง dependency ใหม่ให้) |
| `.env` บน Mac | ต้องรีสตาร์ทเอง: `launchctl kickstart -k gui/$(id -u)/com.ciel.server` |

- ดูว่าอัปเดตแล้วจริงไหมได้ที่แถบล่างของหน้าเว็บ ซึ่งแสดง `v0.1.0 · <commit>` เป็นรหัสเดียวกับ commit ล่าสุดบน GitHub
- ถ้าเพิ่ม dependency ใหม่ ต้องรองรับ Python 3.12
- log การอัปเดต: `grep updater ~/Library/Logs/Ciel.log`

## คำสั่งดูแลเซิร์ฟเวอร์ (บน Mac)

```bash
# รีสตาร์ท Ciel
launchctl kickstart -k gui/$(id -u)/com.ciel.server

# ปิด Ciel ถาวร
launchctl bootout gui/$(id -u)/com.ciel.server

# ดู log
tail -f ~/Library/Logs/Ciel.log

# สถานะ Tailscale Serve
/Applications/Tailscale.app/Contents/MacOS/Tailscale serve status
```

ไฟล์ที่เกี่ยวข้อง (อยู่นอก repo):

- LaunchAgent: `~/Library/LaunchAgents/com.ciel.server.plist` (เปิดเองตอนล็อกอิน, ล่มแล้วเปิดใหม่อัตโนมัติ)
- Log: `~/Library/Logs/Ciel.log`

## ปัญหาที่เจอระหว่างติดตั้ง

| ปัญหา | วิธีแก้ |
|---|---|
| `python3` ในเครื่องเป็น 3.15 แพ็กเกจยังไม่มี wheel ทำให้ `pip install` ค้าง | `brew install python@3.12` แล้วสร้าง venv ใหม่ด้วย `python3.12` |
| ติดตั้ง Tailscale ผ่าน brew ไม่สำเร็จ (ใส่รหัสเครื่องผิด) แต่ brew จำว่าติดตั้งแล้ว | `brew reinstall --cask tailscale-app` |
| `tailscale serve` ขึ้น "Serve is not enabled on your tailnet" | เปิดลิงก์ที่คำสั่งให้มาแล้วกด Enable ในบัญชี Tailscale |
