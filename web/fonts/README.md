# Fonts

| ไฟล์ | ฟอนต์ | ที่มา | ไลเซนส์ |
|---|---|---|---|
| `Monocraft.otf`, `Monocraft-Bold.otf` | Monocraft v4.2.1 — ตัวอักษรละติน/กรีกสไตล์ Minecraft | https://github.com/IdreesInc/Monocraft | SIL OFL 1.1 (`OFL.txt`) |
| `Unifont-Thai.otf` | GNU Unifont 18.0.01 ตัดเหลือเฉพาะตัวอักษรไทย (U+0E00–0E7F) | https://unifoundry.com/unifont/ | SIL OFL 1.1 หรือ GNU GPLv2+ with Font Embedding Exception |

สร้าง `Unifont-Thai.otf` ใหม่ได้ด้วยคำสั่ง:

```bash
pip install fonttools
pyftsubset unifont-18.0.01.otf --unicodes="U+0E00-0E7F,U+200B-200D,U+25CC" \
  --layout-features='*' --name-IDs='*' --output-file=Unifont-Thai.otf
```
