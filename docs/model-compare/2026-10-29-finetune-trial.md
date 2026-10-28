# ลองเทรน LoRA บน Mac (20 iteration) — 2026-10-29

> ทำตาม `docs/MAC_TASK_FINETUNE.md` ขั้นที่ 1–4 (รอบลอง) · M1 16GB · mlx-lm 0.32.2 (Python 3.12 ผ่าน uv เพราะ python3 ของเครื่องเป็น 3.15) · `mlx-community/Qwen3-8B-4bit`
> คำสั่งตามเอกสารทุกตัว (`--num-layers 16 --max-seq-length 4096 --batch-size 1 --grad-checkpoint --mask-prompt`)

## ผล

| | ค่า |
|---|---|
| ข้อมูล | 89 dialogs, 166 replies, 0 problems · train 145 / valid 21 · ยาวสุด ~3,341 token |
| val loss เริ่มต้น | 2.494 (ใช้เวลาประเมิน **1,386s ≈ 23 นาที**) |
| train loss (iter 5/10/15/20) | 2.006 → 1.315 → 1.301 → 1.343 |
| val loss ที่ iter 20 | **1.144** (ประเมิน ~1,630s) |
| เวลารวม 20 iteration | **7,881s ≈ 2 ชม. 11 นาที** |
| เวลาต่อ iteration (ไม่นับประเมิน) | **~240s ≈ 4 นาที** |
| Peak memory footprint | 11.8 GB · swap ใช้ ~3.3 GB จาก 4 GB |

- loss ลดเร็ว (2.49 → 1.14 ใน 20 iteration) แปลว่าข้อมูลและรูปแบบใช้ได้
- **แต่ช้ามาก:** รอบจริง 450 iteration ≈ 450 × 4 นาที ≈ **30 ชั่วโมง** + ประเมิน 9 ครั้ง × ~27 นาที ≈ 4 ชั่วโมง → **~34 ชั่วโมง** เกินเกณฑ์ ~5 ชั่วโมงมาก จึงยังไม่ได้เริ่มรอบจริง
- CPU ใช้แค่ ~170s จาก 7,881s → เวลาเกือบทั้งหมดอยู่ที่ GPU และหน่วยความจำ ตัวอย่างแต่ละชุดยาว ~3,300 token เพราะมี system prompt ~3,100 token อยู่ทุกชุด (แม้ `--mask-prompt` ไม่คิด loss แต่ยังต้องคำนวณ forward/backward ทั้งหมด) และ RAM ใกล้เต็มจนใช้ swap
- adapter ของรอบลองอยู่ที่ `training/adapters-trial/` (39 MB, ไม่อยู่ใน git)

## ทางเลือก

1. **ลดภาระบน Mac:** `--num-layers 8` และลดจำนวน iteration เหลือ ~1 รอบข้อมูล (145) ยังน่าจะใช้ >8 ชั่วโมง ต้องลองวัด 5 iteration ก่อน
2. **ทำให้ตัวอย่างสั้นลง (ฝั่ง Windows แก้ `build_dataset.py`):** ใช้ system prompt ย่อในข้อมูลเทรน หรือแยกบทสนทนายาวเป็นชิ้น ถ้าเหลือ ~1,000 token ต่อชุด น่าจะเร็วขึ้น 3–4 เท่า
3. **เทรนบนเครื่องที่มี GPU NVIDIA (ฝั่ง Windows หรือคลาวด์):** ใช้ข้อมูล `training/data/*.jsonl` ชุดเดียวกัน (เช่น ด้วย Unsloth/PEFT) แล้วส่ง adapter หรือ GGUF มานำเข้า Ollama บน Mac
4. ลดตัว val set หรือ `--val-batches` ให้การประเมินไม่กิน 25 นาทีต่อครั้ง

Ciel เปิดกลับแล้วหลังรอบลอง (v0.3.16, `qwen3:8b`, warm-up ปกติ)
