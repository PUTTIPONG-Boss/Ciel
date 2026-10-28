# งานสำหรับ Claude บน Mac: อัปเดตเป็น v0.1.2 และเปิดระบบอัปเดตอัตโนมัติ

> **วิธีใช้:** เปิด Claude Code บน Mac แล้วพิมพ์
> `cd ~/Ciel && git pull แล้วทำตาม docs/MAC_UPDATE.md`
> หรือ `ทำตาม https://github.com/PUTTIPONG-Boss/Ciel/blob/main/docs/MAC_UPDATE.md`

---

## ถึง Claude

### สถานะตอนนี้ (ตรวจจากฝั่ง Windows เมื่อ 2026-10-26)

- Ciel บน Mac ยังรัน **โค้ดชุดแรก (Phase 1)** อยู่ เพราะ `/api/health` ตอบกลับเป็น `{"ok":true,"llm":"ollama","model":"qwen3:8b"}` ซึ่งไม่มีฟิลด์ `version`
- บน GitHub มีโค้ดใหม่ถึง **v0.1.2** แล้ว ดูรายละเอียดใน `CHANGELOG.md`
  - หน้าตาใหม่: วงเวทและ terminal แบบ pixel (ฟอนต์ Monocraft + Unifont ไทย)
  - แสดงเวอร์ชันบนหน้าเว็บ
  - **ระบบอัปเดตอัตโนมัติ** (`ciel/updater.py`) ซึ่งเปิดใช้ด้วย `CIEL_AUTO_UPDATE=true`

### เป้าหมาย

ทำครั้งนี้ครั้งเดียว แล้วต่อจากนี้เมื่อฝั่ง Windows push ขึ้น `main` เครื่อง Mac จะอัปเดตเองภายใน 1 นาที โดยไม่ต้องมีคนมาสั่ง

**ข้อกำหนดในการทำงาน**

- ทำทีละขั้น และรันเช็กในหัวข้อ **ตรวจสอบ** ให้ผ่านก่อนไปขั้นถัดไป
- ห้ามใช้ `sudo` ห้ามแก้ไฟล์ใน `~/Ciel` ที่ git ติดตามอยู่ ยกเว้นในขั้นที่ 5
- ห้ามแสดงค่า `CIEL_PASSWORD`
- คุยกับผู้ใช้เป็นภาษาไทย

---

## ขั้นที่ 1: เช็กว่าเครื่องพร้อมดึงโค้ด

```bash
cd ~/Ciel
git status --short
git log --oneline -1
git fetch origin main && git log --oneline HEAD..origin/main
```

**ตรวจสอบ:**

- `git status --short` ต้องว่าง ถ้ามีไฟล์ที่ถูกแก้ ให้ดูว่าแก้อะไรแล้วแจ้งผู้ใช้ก่อน ห้ามลบทิ้งเอง
- ถ้ามี commit บน Mac ที่ยังไม่ได้ push (`git log origin/main..HEAD` มีผลลัพธ์) ให้ push ก่อน หรือแจ้งผู้ใช้

## ขั้นที่ 2: ดึงโค้ดใหม่

```bash
cd ~/Ciel && git pull --ff-only
cat VERSION                       # ต้องได้ 0.1.2 หรือใหม่กว่า
.venv/bin/pip install -q -r requirements.txt
```

## ขั้นที่ 3: เปิดระบบอัปเดตอัตโนมัติ

```bash
cd ~/Ciel
grep -q '^CIEL_AUTO_UPDATE=' .env \
  && sed -i '' 's/^CIEL_AUTO_UPDATE=.*/CIEL_AUTO_UPDATE=true/' .env \
  || printf '\n# อัปเดตอัตโนมัติจาก GitHub\nCIEL_AUTO_UPDATE=true\n' >> .env
grep -E '^CIEL_(LLM|MODEL|HOST|AUTO_UPDATE)=' .env
```

**ตรวจสอบ:** ต้องเห็น `CIEL_AUTO_UPDATE=true`

## ขั้นที่ 4: รีสตาร์ท Ciel แล้วตรวจสอบ

```bash
launchctl kickstart -k gui/$(id -u)/com.ciel.server
sleep 3
curl -s http://127.0.0.1:47080/api/health; echo
git -C ~/Ciel rev-parse --short HEAD
grep -E 'updater|auto-update' ~/Library/Logs/Ciel.log | tail -3
curl -s -o /dev/null -w '%{http_code} %{content_type}\n' http://127.0.0.1:47080/fonts/Monocraft.otf
```

**ตรวจสอบ:**

- `/api/health` ต้องมี `"version":"0.1.2"` (หรือใหม่กว่า) และค่า `"commit"` ต้องตรงกับ `git rev-parse --short HEAD`
- log ต้องมี `auto-update on: checking origin/main every 60s`
- ไฟล์ฟอนต์ต้องตอบ `200`
- ถ้าใช้ `sleep` ไม่ได้ ให้รอสักครู่แล้วค่อยรันคำสั่ง `curl`

จากนั้นให้ผู้ใช้เปิด https://boss-puttipong.tail6857ad.ts.net บนมือถือแล้วเช็กว่า:

- หน้าตาเป็นวงเวท + terminal แบบ pixel
- แถบล่างขวาแสดง `v0.1.2 · <commit>`
- ถ้าเป็นแอปที่ติดตั้งไว้แล้วยังเห็นหน้าตาเก่า ให้ปิดแอปแล้วเปิดใหม่หนึ่งครั้ง

## ขั้นที่ 5: รายงานกลับให้ฝั่ง Windows

แก้ `docs/MAC_SERVER.md` ส่วน **สรุปผล** ให้เป็นปัจจุบัน:

- เพิ่มบรรทัด `| เวอร์ชัน | v0.1.2 (<commit>) อัปเดตอัตโนมัติ: เปิด |`
- เปลี่ยน **ขั้นที่เสร็จแล้ว / ที่เหลือ** ให้ตรงกับสถานะจริง และบอกด้วยว่าขั้นที่ 9 (ตั้งค่าไม่ให้ Mac sleep) ทำแล้วหรือยัง

แล้ว commit และ push **ทันที** เพราะระบบอัปเดตจะข้ามการอัปเดตถ้ามี commit บน Mac ที่ยังไม่ได้ push:

```bash
cd ~/Ciel && git add docs/MAC_SERVER.md && git commit -m "Mac: v0.1.2 running, auto-update on" && git push
```

**ตรวจสอบ:** `git status --short` ว่าง และ `git log origin/main..HEAD` ไม่มีผลลัพธ์

---

## กฎหลังจากนี้ (สำหรับ Claude บน Mac ในอนาคต)

- **ห้ามแก้โค้ดหรือไฟล์อื่นใน `~/Ciel` บน Mac:** การพัฒนาทำฝั่ง Windows แล้ว push ขึ้นมา ถ้าแก้ไฟล์บน Mac ระบบจะหยุดอัปเดตจนกว่าจะเคลียร์ไฟล์ที่แก้
- **ข้อยกเว้น:** แก้ไฟล์ใน `docs/` ได้ แต่ต้อง commit และ push ทันที
- **ถ้าแก้ `.env`:** ไฟล์นี้ git ไม่ได้ติดตาม จึงแก้ได้ แต่ต้องรีสตาร์ทเองด้วย `launchctl kickstart -k gui/$(id -u)/com.ciel.server`
- **ถ้าอัปเดตไม่ขึ้น:** ดู `grep updater ~/Library/Logs/Ciel.log | tail`
  - `local file edits present` → มีไฟล์ที่ถูกแก้บน Mac
  - `local commits not on GitHub` → มี commit ที่ยังไม่ได้ push
  - `git fetch failed` → เน็ตหรือสิทธิ์เข้า GitHub มีปัญหา
