# คู่มือติดตั้ง Ciel บน Mac (สำหรับ Claude)

> **วิธีใช้:** เปิด Claude Code บน Mac แล้วพิมพ์
> `ทำตาม https://github.com/PUTTIPONG-Boss/Ciel/blob/main/docs/SETUP_MAC.md ให้หน่อย`
> หรือคัดลอกทั้งไฟล์นี้ไปวางในแชท

---

## ถึง Claude

ช่วยติดตั้ง **Ciel** ผู้ช่วย AI ส่วนตัวที่รันบน Mac เครื่องนี้ให้ผู้ใช้ด้วย
Ciel ประกอบด้วย backend FastAPI (Python) + หน้าเว็บ PWA และใช้ Ollama เป็นโมเดลภาษา
เป้าหมายคือ Mac เครื่องนี้เปิดทิ้งไว้เป็นเซิร์ฟเวอร์ แล้วผู้ใช้คุยกับ Ciel ได้จากมือถือหรือคอมเครื่องอื่นผ่าน Tailscale

**ข้อกำหนดในการทำงาน**

- ทำทีละขั้นตามลำดับ แต่ละขั้นมีหัวข้อ **ตรวจสอบ** ให้รันเช็กจนผ่านก่อนไปขั้นถัดไป
- ถ้าขั้นไหนไม่ผ่าน ให้หาสาเหตุและแก้ก่อน อย่าข้ามขั้น
- ขั้นที่เขียนว่า **👤 ผู้ใช้ทำเอง** (ล็อกอินบัญชี, ใส่รหัสผ่าน, ตั้งค่าระบบ) ให้อธิบายวิธีทำแล้วรอผู้ใช้ทำเสร็จ ห้ามทำแทน
- ห้ามรันคำสั่ง `sudo` และห้ามแก้ System Settings เอง
- ติดตั้งโปรเจกต์ไว้ที่ `~/Ciel`
- คุยกับผู้ใช้เป็นภาษาไทย
- จบแล้วรายงานตามหัวข้อ "สรุปผลให้ผู้ใช้" ท้ายไฟล์

---

## ขั้นที่ 1: เช็กเครื่อง

```bash
sysctl -n machdep.cpu.brand_string
sysctl -n hw.memsize | awk '{print $1/1073741824 " GB"}'
sw_vers -productVersion
df -h ~ | tail -1
```

จดชิปและ RAM ไว้ เพราะใช้เลือกโมเดลในขั้นที่ 3

**ตรวจสอบ:** ต้องเป็น Apple Silicon (M1 ขึ้นไป), RAM 16GB ขึ้นไป และพื้นที่ว่างไม่น้อยกว่า 15GB
ถ้า RAM 8GB ให้แจ้งผู้ใช้ว่าจะต้องใช้โมเดลเล็ก (`qwen3:4b`) แล้วทำต่อได้

## ขั้นที่ 2: เครื่องมือพื้นฐาน

ต้องมี **Homebrew**, **git** และ **Python 3.10 ขึ้นไป**
(`python3` ที่มากับ macOS มักเป็น 3.9 ซึ่ง **ใช้กับ Ciel ไม่ได้**)

```bash
brew --version
git --version
python3 --version
```

- ไม่มี Homebrew → 👤 **ผู้ใช้ทำเอง:** ให้ผู้ใช้รันคำสั่งติดตั้งจาก https://brew.sh ใน Terminal เพราะต้องใส่รหัสผ่านเครื่อง จากนั้นทำตามคำแนะนำที่ขึ้นท้ายการติดตั้ง (เพิ่ม brew ลง PATH)
- Python ต่ำกว่า 3.10 → `brew install python@3.12` แล้วใช้ `python3.12` แทน `python3` ในขั้นต่อๆ ไป

**ตรวจสอบ:** `python3.12 --version` (หรือ `python3 --version`) ได้ 3.10 ขึ้นไป

## ขั้นที่ 3: ติดตั้ง Ollama และโหลดโมเดล

```bash
brew install --cask ollama
open -a Ollama
```

เมื่อเปิด Ollama ครั้งแรก แอปจะถามว่าให้ติดตั้งคำสั่ง `ollama` ไหม → 👤 ให้ผู้ใช้กดยืนยัน
(Ollama เปิดเองอัตโนมัติตอนล็อกอิน มีไอคอนรูปลามะบนแถบเมนู)

เลือกโมเดลตาม RAM จากขั้นที่ 1:

| RAM | โมเดล |
|---|---|
| 8GB | `qwen3:4b` |
| 16GB | `qwen3:8b` |
| 32GB | `qwen3:14b` |
| 64GB ขึ้นไป | `qwen3:32b` |

```bash
ollama pull qwen3:8b   # เปลี่ยนตามตาราง
```

ไฟล์โมเดลมีขนาดหลาย GB ให้รันแบบ background แล้วรอจนเสร็จ

**ตรวจสอบ:**

```bash
ollama --version            # ควรเป็น 0.9 ขึ้นไป (รองรับการปิดโหมด think)
ollama list                 # ต้องเห็นโมเดลที่เพิ่งโหลด
curl -s http://127.0.0.1:11434/api/tags | head -c 200
ollama run qwen3:8b "ตอบสั้นๆ: สวัสดี" --think=false
```

## ขั้นที่ 4: ดาวน์โหลด Ciel และติดตั้ง

```bash
git clone https://github.com/PUTTIPONG-Boss/Ciel.git ~/Ciel
cd ~/Ciel
python3.12 -m venv .venv   # หรือ python3 ถ้าเวอร์ชัน 3.10 ขึ้นไปอยู่แล้ว
.venv/bin/pip install -q -r requirements.txt
cp .env.example .env
```

ถ้ามี `~/Ciel` อยู่แล้ว ให้ใช้ `cd ~/Ciel && git pull` แทนการ clone ใหม่

## ขั้นที่ 5: ตั้งค่า `.env`

แก้ไฟล์ `~/Ciel/.env` ดังนี้

- `CIEL_LLM=ollama`
- `CIEL_MODEL=` ใส่ชื่อโมเดลที่โหลดในขั้นที่ 3
- `CIEL_HOST=127.0.0.1` (คงค่านี้ไว้ เพราะ Tailscale serve จะส่งต่อการเชื่อมต่อมาที่ localhost ให้เอง ซึ่งปลอดภัยกว่าการเปิดให้ทั้งวง Wi-Fi)
- `CIEL_PASSWORD` 👤 **ผู้ใช้ทำเอง:** บอกผู้ใช้ให้เปิดไฟล์ด้วย `open -e ~/Ciel/.env` แล้วตั้งรหัสผ่านเอง ห้ามคิดรหัสผ่านให้ และห้ามขอให้ผู้ใช้พิมพ์รหัสผ่านในแชท

**ตรวจสอบ:** `grep -E '^CIEL_(LLM|MODEL|HOST)=' ~/Ciel/.env` (ห้ามแสดงบรรทัดรหัสผ่าน)

## ขั้นที่ 6: ทดลองรันและทดสอบ

```bash
cd ~/Ciel && .venv/bin/python -m ciel
```

รันแบบ background แล้วทดสอบดังนี้

```bash
curl -s http://127.0.0.1:8080/api/health
```

ต้องได้ `"ok": true` และชื่อโมเดลถูกต้อง

จากนั้นทดสอบแชทจริงผ่าน WebSocket ถ้าตั้งรหัสผ่านไว้ ให้ปิดรหัสชั่วคราวก่อน หรือให้ผู้ใช้ทดสอบเองผ่านเบราว์เซอร์ที่ http://localhost:8080

```bash
cd ~/Ciel && .venv/bin/python - <<'EOF'
import json
from websockets.sync.client import connect
with connect("ws://127.0.0.1:8080/ws") as ws:
    print("hello:", json.loads(ws.recv()))
    ws.send(json.dumps({"type": "chat", "text": "เธอเป็นใคร"}))
    while True:
        m = json.loads(ws.recv())
        if m["type"] in ("end", "error"):
            print(m); break
EOF
```

**ตรวจสอบ:**

- ได้ `type: end` พร้อมคำตอบภาษาไทยที่แนะนำตัวว่าเป็น Ciel ไม่ใช่ `error`
- ในคำตอบต้องไม่มีแท็ก `<think>`
- จดไว้ว่าตอบเสร็จภายในกี่วินาที

เสร็จแล้วให้หยุดเซิร์ฟเวอร์ที่รันทดสอบไว้

## ขั้นที่ 7: ให้ Ciel เปิดเองทุกครั้งที่เปิดเครื่อง (LaunchAgent)

สร้างไฟล์ `~/Library/LaunchAgents/com.ciel.server.plist` โดยแทน `HOME_DIR` ด้วยผลของ `echo $HOME`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.ciel.server</string>
  <key>ProgramArguments</key>
  <array>
    <string>HOME_DIR/Ciel/.venv/bin/python</string>
    <string>-m</string>
    <string>ciel</string>
  </array>
  <key>WorkingDirectory</key><string>HOME_DIR/Ciel</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>EnvironmentVariables</key>
  <dict><key>PYTHONUNBUFFERED</key><string>1</string></dict>
  <key>StandardOutPath</key><string>HOME_DIR/Library/Logs/Ciel.log</string>
  <key>StandardErrorPath</key><string>HOME_DIR/Library/Logs/Ciel.log</string>
</dict>
</plist>
```

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ciel.server.plist
```

**ตรวจสอบ:**

```bash
launchctl print gui/$(id -u)/com.ciel.server | grep -E 'state|pid'
curl -s http://127.0.0.1:8080/api/health
tail -20 ~/Library/Logs/Ciel.log
```

ข้อมูลสำหรับบอกผู้ใช้ไว้ใช้ภายหลัง:

- **รีสตาร์ท Ciel** (เช่น หลังแก้ `.env` หรือ `git pull`):
  ```bash
  launchctl kickstart -k gui/$(id -u)/com.ciel.server
  ```
- **ปิด Ciel ถาวร:**
  ```bash
  launchctl bootout gui/$(id -u)/com.ciel.server
  ```
- **แก้นิสัยใน `persona/ciel.yaml`:** ไม่ต้องรีสตาร์ท แค่กดปุ่ม "แชทใหม่" ในหน้าเว็บ

## ขั้นที่ 8: Tailscale (คุยกับ Ciel จากที่ไหนก็ได้)

```bash
brew install --cask tailscale
open -a Tailscale
```

👤 **ผู้ใช้ทำเอง:**

1. ล็อกอิน Tailscale บน Mac (เช่น ด้วยบัญชี Google)
2. ติดตั้งแอป Tailscale บนมือถือ แล้วล็อกอินบัญชีเดียวกัน
3. เปิด **MagicDNS** และ **HTTPS Certificates** ในหน้า https://login.tailscale.com/admin/dns (จำเป็น เพราะเบราว์เซอร์จะให้ใช้ไมโครโฟนได้เฉพาะบน HTTPS)

เมื่อผู้ใช้ทำครบแล้ว:

```bash
# CLI ของแอป Tailscale บน Mac
TS=/Applications/Tailscale.app/Contents/MacOS/Tailscale
$TS status
$TS serve --bg 8080
$TS serve status
```

**ตรวจสอบ:** `serve status` ต้องแสดง URL แบบ `https://<ชื่อเครื่อง>.<tailnet>.ts.net` ที่ชี้ไปยัง `http://127.0.0.1:8080`
ให้ผู้ใช้เปิด URL นั้นบนมือถือ (ต้องเปิด Tailscale บนมือถือไว้) แล้ว:

- ล็อกอินด้วยรหัสผ่านที่ตั้งไว้
- ทักทาย Ciel ว่าตอบกลับได้
- กด Share → **Add to Home Screen** (iPhone) หรือ ⋮ → **Install app** (Android)

`tailscale serve --bg` จะจำค่าไว้ เปิดเครื่องใหม่ก็ยังใช้งานได้

## ขั้นที่ 9: ให้ Mac เปิดทิ้งไว้ได้

👤 **ผู้ใช้ทำเอง** (Claude อธิบายวิธีทำให้ผู้ใช้):

1. **System Settings → Battery → Options →** เปิด *Prevent automatic sleeping on power adapter when the display is off*
2. **ถ้าจะพับจอ MacBook:** ติดตั้ง **Amphetamine** จาก App Store แล้วเปิดโหมดที่ให้เครื่องทำงานต่อเมื่อพับจอ (Closed-Display Mode) ควรวางเครื่องในที่ระบายความร้อนได้ดี
3. **ถนอมแบต:** ติดตั้ง **AlDente** (`brew install --cask aldente`) แล้วตั้งให้ชาร์จไม่เกิน 80%
4. **System Settings → General → Login Items:** เช็กว่ามี Ollama และ Tailscale อยู่ในรายการ

---

## สรุปผลให้ผู้ใช้

เมื่อเสร็จทุกขั้น ให้สรุปให้ผู้ใช้เป็นภาษาไทย:

- ชิป, RAM และโมเดลที่เลือก พร้อมเวลาตอบโดยประมาณจากขั้นที่ 6
- URL สำหรับคุยกับ Ciel: บนเครื่องนี้ (`http://localhost:8080`) และจากที่อื่น (`https://….ts.net`)
- ขั้นไหนผ่านแล้ว ขั้นไหนยังรอผู้ใช้ทำ
- คำสั่งรีสตาร์ท Ciel, ตำแหน่งไฟล์ log (`~/Library/Logs/Ciel.log`) และวิธีอัปเดต:
  ```bash
  cd ~/Ciel && git pull && .venv/bin/pip install -q -r requirements.txt && launchctl kickstart -k gui/$(id -u)/com.ciel.server
  ```
- ปัญหาที่เจอระหว่างติดตั้ง และวิธีที่ใช้แก้
