# งานสำหรับ Claude บน Mac: fine-tune Ciel ด้วย LoRA (v0.3.18)

> **วิธีใช้:** เปิด Claude Code บน Mac แล้วพิมพ์
> `cd ~/Ciel && git pull แล้วทำตาม docs/MAC_TASK_FINETUNE.md`

---

## ถึง Claude

มาสเตอร์อยากให้ Ciel เข้าใจภาษาไทยดีขึ้น ตัวอย่างที่พลาดคือ "แต่**เรา**พูดถึง**เธอ**นะ" ซึ่ง Ciel ไม่เข้าใจว่าเรา = มาสเตอร์ และเธอ = Ciel และ "เมื่อกี้ที่บอกให้ระวัง หมายถึงใคร" ที่ตอบไม่ตรง

ฝั่ง Windows เตรียมไว้แล้ว:

- ข้อมูลเทรน `training/dialogs/*.yaml`: บทสนทนาหลายรอบ 60 ชุด + ตัวอย่างจาก persona 29 ชุด รวม 166 คำตอบ
- `training/build_dataset.py`: ตรวจและสร้างไฟล์เทรน
- `scripts/eval_thai.py` + `training/eval.yaml`: ใช้ทดสอบเทียบโมเดล
- `CIEL_TUNED`: ให้โมเดลที่เทรนแล้วใช้ system prompt สั้นแบบเดียวกับตอนเทรน และไม่มีตัวอย่างใน prompt

### รอบที่ 3 (v0.3.18) ต่อจาก `2026-10-29-2005-thai-eval.md` — ไม่ต้องเทรนใหม่

รอบที่ 2 ใช้ checkpoint 100 (val ต่ำสุด) แต่ยังไม่ครบหนึ่งรอบข้อมูล รูปแบบคำตอบจึงพัง: บรรทัดญี่ปุ่นบรรทัดเดียวยาวๆ แล้วมี `>> 2` ที่ไม่มีประโยคคู่ รอบนี้ **ลอง checkpoint 300 และ 450** ที่มีอยู่แล้ว

1. **Fuse checkpoint ทีละตัว:** copy `training/adapters/0000300_adapters.safetensors` (ชื่อจริงดูจาก `ls training/adapters`) ไปทับ `training/adapters/adapters.safetensors` แล้วทำขั้นที่ 5–6 ซ้ำ (fuse → แปลง GGUF แบบเดียวกับรอบที่แล้ว → `llama-quantize` Q4_K_M) แต่สร้างเป็น **`ciel-qwen3:300`** ทำเหมือนกันกับ 450 (`training/adapters/final_450.safetensors`) เป็น **`ciel-qwen3:450`**
   - ใช้ไฟล์ชั่วคราวชื่อเดิม (`training/fused/`, `ciel-f16.gguf`) ทับได้เลย พื้นที่จะได้ไม่เพิ่ม
2. **ทดสอบ** (`eval_thai.py` จะ unload โมเดลอื่นให้เองก่อนแต่ละโมเดล ไม่ต้องหยุด Ciel แต่ต้องทำตอนไม่มีใครคุย และ **ปิด OrbStack ระหว่างทดสอบ** ถ้าไม่ได้ใช้):
   ```bash
   cd ~/Ciel && git pull --ff-only && .venv/bin/python scripts/eval_thai.py qwen3:8b ciel-qwen3@tuned ciel-qwen3:300@tuned ciel-qwen3:450@tuned
   ```
   - รายงานมีตาราง **"รูปแบบคำตอบ"** ที่ตรวจให้อัตโนมัติ (x/24 คำตอบที่แอปจะพูดและขึ้นซับถูก) และมี ⚠️ บอกปัญหาข้างคำตอบที่พัง
   - เวลาในวงเล็บควรกลับมาเป็นไม่กี่วินาที ถ้ายังเป็นหลักร้อย ให้ดู `memory_pressure` แล้วรายงาน
3. **รายงาน:** ใช้ตารางสรุป ✅/⚠️/❌ เหมือนรอบที่แล้ว (เพิ่มคอลัมน์ 300 และ 450) พร้อมตารางรูปแบบคำตอบ แล้วระบุว่า checkpoint ไหนดีที่สุด และดีกว่า `qwen3:8b` หรือยัง
4. **ห้ามเปลี่ยน `CIEL_MODEL`** เหมือนเดิม หลังทดสอบเปิดหน้าเว็บ Ciel หนึ่งครั้ง (หรือรอ keep-warm ≤ 5 นาที) เพื่อโหลด qwen3:8b กลับ
5. **ลบไฟล์ใหญ่:** หลังได้ผลแล้ว ถามมาสเตอร์ว่าจะลบ `training/fused/` และ `training/*.gguf` (~36 GB) หรือไม่ ส่วน adapters และ cache ของ Hugging Face เก็บไว้

### รอบที่ 2 (v0.3.17) ต่อจาก `2026-10-29-finetune-trial.md`

- **รอบลองแรก:** 20 iteration ใช้ 2 ชม. 11 นาที (~4 นาที/iteration) peak 11.8 GB และใช้ swap เพราะทุกตัวอย่างยาว ~3,300 token (system prompt เต็ม ~3,100)
- **ตอนนี้ข้อมูลเทรนใช้ system prompt สั้น** (`Persona.tuned_prompt` ~630 token) ตัวอย่างยาวสุด ~920 token (สั้นลง 3.6 เท่า) จึงลด `--max-seq-length` เหลือ 1024
- **การประเมิน (val):** ใช้ `--val-batches 10` และประเมินทุก 100 iteration (เดิมประเมินทั้งชุดทุกครั้ง ~25 นาที)
- **ใช้ venv เดิมได้:** `~/ciel-train` (Python 3.12 ผ่าน uv) ข้ามขั้นที่ 2 ถ้ายังอยู่
- **adapter ของรอบลองแรก (`training/adapters-trial/`)** เทรนกับ prompt เต็ม ใช้กับ prompt สั้นไม่ได้ ลบได้
- **รัน `--iters 20` ก่อนเสมอ** แล้วรายงานเวลาต่อ iteration และ peak mem ถ้ารอบจริงคาดว่าเกิน ~5 ชั่วโมง ให้ถามมาสเตอร์ก่อน (ทางเลือก: `--num-layers 8` หรือลด iteration)

งานนี้คือเทรน LoRA ด้วย **MLX** แล้วนำเข้า Ollama เป็นโมเดลใหม่ชื่อ `ciel-qwen3` จากนั้นทดสอบเทียบกับ `qwen3:8b`

**ห้ามเปลี่ยน `CIEL_MODEL` ใน `.env`** ให้ส่งรายงานเทียบ แล้วมาสเตอร์จะตัดสินใจเอง

**ข้อกำหนด:**
- ห้ามแก้ไฟล์โค้ด แก้และ commit ได้เฉพาะไฟล์ใน `docs/`
- ห้ามแสดงรหัสผ่าน
- คุยกับผู้ใช้เป็นภาษาไทย
- ถ้าคำสั่งไหนไม่ตรงกับเวอร์ชัน mlx-lm ที่ติดตั้ง (เช่น ชื่อ flag เปลี่ยน) ให้ดู `--help` แล้วปรับเฉพาะ flag ห้ามแก้สคริปต์

### ⚠️ ต้องขออนุญาตมาสเตอร์ก่อนเริ่ม (ถามครั้งเดียวให้ครบ)

1. **ดาวน์โหลด:**
   - `mlx-lm` (pip)
   - `mlx-community/Qwen3-8B-4bit` จาก Hugging Face (~4.6 GB)
   - อาจต้องใช้ `llama.cpp` (git clone ~100 MB) ถ้า Ollama นำเข้าเองไม่ได้
2. **พื้นที่ดิสก์:** ต้องว่าง **≥ 30 GB** (โมเดลที่รวม LoRA แล้วแบบเต็ม ~16 GB + GGUF ~16 GB ชั่วคราว) เช็กด้วย `df -h ~`
3. **Ciel จะออฟไลน์ระหว่างเทรน** (รอบแรกใช้ ~4 นาที/iteration รอบนี้ตัวอย่างสั้นลง 3.6 เท่า คาดว่า ≤ 1 นาที/iteration → 450 iteration ≈ 4–7 ชั่วโมง ยืนยันจากรอบลอง 20 iteration) เพราะ RAM 16 GB ไม่พอรันทั้ง Ollama และการเทรน แนะนำให้เทรนตอนกลางคืน

## ขั้นที่ 1: สร้างข้อมูล

```bash
cd ~/Ciel && git pull --ff-only
.venv/bin/python training/build_dataset.py
```

ต้องได้ `0 problems` และ `train: 145 samples, longest ~919 tokens` / `valid: 21 samples` (หรือใกล้เคียง) ถ้า longest ยัง ~3,300 แปลว่ายังไม่ได้ pull v0.3.17

## ขั้นที่ 2: ติดตั้ง (venv แยก ไม่ปนกับของแอป)

```bash
python3 -m venv ~/ciel-train && ~/ciel-train/bin/pip install -U mlx-lm
~/ciel-train/bin/python -c "import mlx_lm; print(mlx_lm.__version__)"
```

## ขั้นที่ 3: หยุด Ciel และ Ollama เพื่อคืน RAM

```bash
launchctl bootout gui/$UID/com.ciel.server     # หยุดเซิร์ฟเวอร์ (keep-warm จะได้ไม่โหลดโมเดลกลับมา)
ollama stop qwen3:8b
ollama ps                                       # ต้องว่าง
```

ถ้าชื่อ service หรือวิธีรันต่างจากนี้ ให้ดูจาก `ls ~/Library/LaunchAgents/` แล้วจดคำสั่งเปิดกลับไว้ก่อน

## ขั้นที่ 4: เทรน

**ลองสั้นๆ ก่อน 20 iteration** เพื่อดูเวลาและ RAM:

```bash
cd ~/Ciel && ~/ciel-train/bin/python -m mlx_lm.lora \
  --model mlx-community/Qwen3-8B-4bit --train --data training/data \
  --adapter-path training/adapters --mask-prompt --grad-checkpoint \
  --batch-size 1 --num-layers 16 --max-seq-length 1024 \
  --learning-rate 1e-5 --iters 20 --steps-per-report 5 \
  --steps-per-eval 20 --val-batches 10
```

- จดเวลาต่อ iteration และ `Peak mem`
- ถ้า RAM ไม่พอ (swap หนัก หรือ crash) ลด `--num-layers 8`
- **ถ้าคาดว่ารอบจริงเกิน ~5 ชั่วโมง ให้ถามมาสเตอร์ก่อน**

**รอบจริง** ประมาณ 3 รอบข้อมูล (145 × 3 ≈ 450 iteration) รันแบบ background:

```bash
cd ~/Ciel && nohup ~/ciel-train/bin/python -m mlx_lm.lora \
  --model mlx-community/Qwen3-8B-4bit --train --data training/data \
  --adapter-path training/adapters --mask-prompt --grad-checkpoint \
  --batch-size 1 --num-layers 16 --max-seq-length 1024 \
  --learning-rate 1e-5 --iters 450 --steps-per-report 10 \
  --steps-per-eval 100 --val-batches 10 --save-every 50 > training/train.log 2>&1 &
```

- ดู `Val loss` ทุก 100 iteration ใน `training/train.log`
- ถ้า val loss เริ่มขึ้นหลังจุดต่ำสุด (overfit) ให้ใช้ checkpoint ที่ val loss ต่ำสุด โดย copy `training/adapters/00000NNN_adapters.safetensors` ไปทับ `training/adapters/adapters.safetensors`
- จด train/val loss ทุกจุดไว้ใส่รายงาน

## ขั้นที่ 5: รวม LoRA เข้ากับโมเดล

```bash
cd ~/Ciel && ~/ciel-train/bin/python -m mlx_lm.fuse \
  --model mlx-community/Qwen3-8B-4bit --adapter-path training/adapters \
  --save-path training/fused --dequantize
```

`--dequantize` ให้ได้ safetensors แบบเต็ม (~16 GB) สำหรับนำเข้า Ollama แล้วค่อย quantize ใหม่เป็น q4_K_M

## ขั้นที่ 6: นำเข้า Ollama

```bash
ollama serve >/dev/null 2>&1 &   # ถ้า Ollama ยังไม่รัน (ปกติแอป Ollama รันอยู่แล้ว)
cd ~/Ciel && ollama create ciel-qwen3 --quantize q4_K_M -f training/Modelfile
ollama list | grep ciel-qwen3      # ควรประมาณ 5 GB
```

**ถ้า Ollama นำเข้า safetensors ของ Qwen3 ไม่ได้** ให้ใช้ llama.cpp แปลงก่อน (ต้องขออนุญาต clone ก่อน):

```bash
cd ~/Ciel/training && git clone --depth 1 https://github.com/ggml-org/llama.cpp
~/ciel-train/bin/pip install -r llama.cpp/requirements/requirements-convert_hf_to_gguf.txt
~/ciel-train/bin/python llama.cpp/convert_hf_to_gguf.py fused --outtype f16 --outfile ciel-f16.gguf
```

จากนั้นสร้าง Modelfile ชั่วคราวนอก repo ที่มี `FROM ~/Ciel/training/ciel-f16.gguf` + `PARAMETER stop` สองบรรทัดเหมือน `training/Modelfile` แล้ว `ollama create ciel-qwen3 --quantize q4_K_M -f <ไฟล์นั้น>` (ห้ามแก้ `training/Modelfile` ใน repo)

## ขั้นที่ 7: เปิด Ciel กลับ แล้วทดสอบ

```bash
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.ciel.server.plist
curl -s http://127.0.0.1:47080/api/health; echo    # ต้องตอบ และยังเป็น qwen3:8b
```

**ทดสอบเทียบ** ทำตอนไม่มีใครคุย เพราะโมเดลจะสลับเข้าออก RAM ใช้เวลาประมาณ 10–15 นาที:

```bash
cd ~/Ciel && .venv/bin/python scripts/eval_thai.py qwen3:8b ciel-qwen3@tuned
```

- `qwen3:8b` = แบบที่ใช้อยู่ตอนนี้ (prompt เต็ม + ตัวอย่าง)
- `ciel-qwen3@tuned` = โมเดลเทรนแล้ว + prompt สั้นแบบที่เทรนมา (แบบที่ตั้งใจจะใช้)

หลังทดสอบ โหลด qwen3:8b กลับเข้า RAM ด้วยการเปิดหน้าเว็บ Ciel หนึ่งครั้ง หรือรอ keep-warm (≤ 5 นาที)

## ขั้นที่ 8: รายงาน

เขียนต่อท้ายไฟล์ `docs/model-compare/<วันที่>-thai-eval.md` ที่สคริปต์สร้าง:

1. **ตาราง "สรุป":** ให้คะแนนแต่ละชุด ✅ / ⚠️ / ❌ ตาม "ควรเป็น" ของชุดนั้น
2. **การเทรน:**
   - เวลาทั้งหมด และเวลาต่อ iteration
   - Peak mem
   - train/val loss ทุก 50 iteration และ checkpoint ที่เลือก
3. **ความเร็ว:**
   - เวลาตอบแต่ละโมเดล (ตัวเลขในวงเล็บ)
   - tok/s ของ `ciel-qwen3` เทียบ `qwen3:8b`: ดูจาก `~/.ollama/logs/server.log` หรือรัน `ollama run ciel-qwen3 --verbose "สวัสดี"`
4. **คุณภาพภาษาญี่ปุ่น/รูปแบบ:**
   - ประโยคแปลกไหม
   - ซับตรงคู่ไหม
   - แท็กอารมณ์ถูกไหม
   - ลอกประโยคจากข้อมูลเทรน (`training/dialogs`) มาทั้งประโยคไหม
5. **ข้อเสนอ:** ควรเปลี่ยนไปใช้ไหม หรือควรเพิ่มข้อมูลเทรนแบบไหน (ดูว่าชุดไหนยังพลาด)

จากนั้น commit และ push เฉพาะ `docs/`:

```bash
cd ~/Ciel && git add docs/ && git commit -m "Fine-tune: ciel-qwen3 vs qwen3:8b Thai eval" && git push
```

**ลบไฟล์ใหญ่หลังนำเข้าสำเร็จ (ถามมาสเตอร์ก่อน):** `training/fused/` (~16 GB) และ `training/ciel-f16.gguf` ส่วน `training/adapters/` เก็บไว้ได้ (เล็ก)

## ถ้ามาสเตอร์ตัดสินใจใช้ (มาสเตอร์ทำเอง หรือสั่งให้ทำ)

ใน `~/Ciel/.env`:

```
CIEL_MODEL=ciel-qwen3
CIEL_TUNED=true
```

แล้วรีสตาร์ท `launchctl kickstart -k gui/$UID/com.ciel.server` จากนั้นวัด `scripts/measure_latency.py --turns 16` ตาม `docs/MAC_TASK_LATENCY.md`

prompt สั้นลงจาก ~6,600 เหลือ ~630 token จึงคาดว่า prefill ตอน cache หลุดจะเร็วขึ้นมาก และตัดประวัติน้อยลง
