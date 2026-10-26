# Live2D

ที่นี่คือที่วางโมเดล Live2D ของ Ciel (จะเชื่อมเข้ากับหน้า UI ในเฟส 5)

## เตรียมไว้ได้เลย

1. วางโฟลเดอร์โมเดลไว้ใน `models/` เช่น `models/ciel/ciel.model3.json`
   (ต้องเป็นโมเดลแบบ **Cubism 3/4/5** ที่มีไฟล์ `.model3.json`)
2. เช็กว่าโมเดลมี parameter เหล่านี้ (ส่วนใหญ่มีอยู่แล้ว):
   - `ParamMouthOpenY` — ขยับปากตามเสียง (lip sync)
   - `ParamEyeBallX`, `ParamEyeBallY`, `ParamAngleX`, `ParamAngleY` — มองตาม/หันหน้า
   - motion group `Idle` และถ้ามี expression เช่น ยิ้ม เขิน ตกใจ จะใช้แสดงอารมณ์ได้
3. เช็กไลเซนส์ของโมเดลก่อนนำไปใช้ — `models/` ถูกตั้งไว้ใน `.gitignore` จึงไม่ถูกอัปขึ้น GitHub

## วิธีเชื่อม (เฟส 5)

`web/avatar.js` กำหนดไว้ว่า avatar ใดๆ ต้องมี `setState()` และ `setLevel()`
ตัว Live2D จะใช้ `pixi-live2d-display` + Cubism Core แล้ว map:

| Ciel | Live2D |
|---|---|
| `setState("idle")` | เล่น motion `Idle` |
| `setState("thinking")` | expression ครุ่นคิด / มองขึ้น |
| `setState("speaking")` | เปิด lip sync |
| `setLevel(v)` | `ParamMouthOpenY = v` (จากความดังของเสียง TTS) |
