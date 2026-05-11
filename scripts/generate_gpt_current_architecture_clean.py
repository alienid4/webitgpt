from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont


OUT = Path(r"F:\ClaudeHome\webitgpt\docs\architecture_diagrams")
OUT.mkdir(parents=True, exist_ok=True)
PATH = OUT / "00_gpt_current_deployed_architecture_clean_v2.png"

C = {
    "bg": "#FAF9F5",
    "white": "#FFFFFF",
    "line": "#BEBEBE",
    "text": "#141413",
    "muted": "#555555",
    "green": "#26A889",
    "green_dark": "#0D5C47",
    "green_light": "#EBF7E8",
    "orange": "#E87C07",
    "gray": "#F5F5F5",
}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        r"C:\Windows\Fonts\NotoSansTC-VF.ttf",
        r"C:\Windows\Fonts\msjhbd.ttc" if bold else r"C:\Windows\Fonts\msjh.ttc",
        r"C:\Windows\Fonts\mingliub.ttc" if bold else r"C:\Windows\Fonts\mingliu.ttc",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


FT = font(38, True)
FH = font(27, True)
FB = font(21, True)
F = font(18)
FS = font(15)

W, H = 1900, 1220
img = Image.new("RGB", (W, H), C["bg"])
d = ImageDraw.Draw(img)


def wrap(text: str, max_width: int, fnt: ImageFont.FreeTypeFont) -> list[str]:
    lines: list[str] = []
    for para in str(text).split("\n"):
        line = ""
        for ch in para:
            test = line + ch
            if d.textbbox((0, 0), test, font=fnt)[2] <= max_width or not line:
                line = test
            else:
                lines.append(line)
                line = ch
        lines.append(line)
    return lines


def box(xy, title: str, lines=(), fill=None, outline=None, title_color=None) -> None:
    x1, y1, x2, y2 = xy
    d.rounded_rectangle(xy, radius=18, fill=fill or C["white"], outline=outline or C["line"], width=2)
    d.text((x1 + 18, y1 + 14), title, font=FB, fill=title_color or C["green_dark"])
    y = y1 + 52
    for line in lines:
        for segment in wrap(line, x2 - x1 - 36, F):
            d.text((x1 + 18, y), segment, font=F, fill=C["text"])
            y += 28


def group(xy, title: str, subtitle: str = "") -> None:
    x1, y1, x2, y2 = xy
    d.rounded_rectangle(xy, radius=24, fill=C["white"], outline=C["line"], width=3)
    d.rounded_rectangle((x1, y1, x2, y1 + 62), radius=24, fill=C["green_light"], outline=None)
    d.rectangle((x1, y1 + 36, x2, y1 + 62), fill=C["green_light"])
    d.rounded_rectangle(xy, radius=24, outline=C["line"], width=3)
    d.text((x1 + 22, y1 + 13), title, font=FH, fill=C["green_dark"])
    if subtitle:
        d.text((x1 + 22, y1 + 44), subtitle, font=FS, fill=C["muted"])


def arrow(a, b, color=None, text: Optional[str] = None, text_pos=None, width: int = 4) -> None:
    import math

    color = color or C["text"]
    d.line((a, b), fill=color, width=width)
    x1, y1 = a
    x2, y2 = b
    angle = math.atan2(y2 - y1, x2 - x1)
    length = 15
    points = [
        (x2, y2),
        (x2 - length * math.cos(angle - 0.45), y2 - length * math.sin(angle - 0.45)),
        (x2 - length * math.cos(angle + 0.45), y2 - length * math.sin(angle + 0.45)),
    ]
    d.polygon(points, fill=color)
    if text:
        tx, ty = text_pos or ((x1 + x2) // 2, (y1 + y2) // 2)
        bbox = d.textbbox((tx, ty), text, font=FS)
        d.rounded_rectangle((bbox[0] - 8, bbox[1] - 4, bbox[2] + 8, bbox[3] + 4), radius=7, fill=C["bg"], outline=C["line"])
        d.text((tx, ty), text, font=FS, fill=color)


d.text((55, 35), "GPT 目前實際已部署架構", font=FT, fill=C["text"])
d.text((57, 88), "只描述目前已部署的 webitgpt，不包含 Claude 版、災備、三機房終態。", font=F, fill=C["muted"])

group((55, 150, 610, 815), "Windows PC 與 Codex", "目前開發與測試環境")
box((95, 240, 570, 360), "程式碼工作區", [r"F:\ClaudeHome\webitgpt", "在此修改程式並產生修補包"], fill=C["green_light"], outline=C["green"])
box((95, 410, 570, 540), "本機驗證", ["執行語法檢查", "執行單元測試", "本機不直接跑需要 MongoDB 的完整頁面"])
box((95, 590, 570, 740), "使用者瀏覽器入口", ["正式網址：http://192.168.1.221:8002", "直接連到 221 上的 webitgpt 服務", "這是目前使用者實際應使用的入口"], fill=C["green_light"], outline=C["green"])

group((760, 150, 1810, 1040), "192.168.1.221 secansible", "Rocky Linux 9.7，Python 3.9.25")
box((1310, 90, 1760, 135), "正式入口：http://192.168.1.221:8002", [], fill=C["green_light"], outline=C["green"])
box((810, 240, 1220, 390), "webitgpt 網站服務", ["路徑：/opt/webitgpt/webapp", "服務：gunicorn 0.0.0.0:8002", "systemd：webitgpt.service"], fill=C["green_light"], outline=C["green"])
box((1310, 240, 1760, 390), "Edge Agent", ["路徑：/opt/webitgpt/edge", "連接埠：9444", "systemd：webitgpt-edge.service"], outline=C["green"])
box((810, 470, 1220, 660), "MongoDB", ["執行方式：podman container", "位址：localhost:27017", "資料庫：webitgpt", "目前為單節點，尚未是 replica set"], outline=C["orange"], title_color=C["orange"])
box((1310, 470, 1760, 660), "資料與日誌", ["資料目錄：/opt/webitgpt/data", "包含 hosts、reports、settings", "日誌目錄：/opt/webitgpt/logs", "包含 access、error、install_audit"])
box((810, 740, 1760, 940), "目前功能狀態", ["網站介面：主機管理、系統管理、開發後台可開啟", "開發期預設以 superadmin 自動登入", "OTP 與 MFA 驗證已停用", "phase_readonly_mode 為啟用狀態，監控主機寫入類動作應封鎖"])

group((55, 880, 610, 1135), "受監控 Demo 主機", "Phase 1 採集測試目標")
box((90, 960, 250, 1075), "主機 221", ["secansible", "192.168.1.221", "本機 Linux"], fill=C["gray"])
box((275, 960, 435, 1075), "主機 222", ["secclient1", "192.168.1.222", "Linux SSH"], fill=C["gray"])
box((460, 960, 590, 1075), "主機 223", ["sec9c2", "192.168.1.223", "Linux SSH"], fill=C["gray"])

arrow((570, 660), (810, 305), C["green_dark"], "HTTP 8002", (640, 370))
arrow((570, 300), (810, 305), C["orange"], "修補包、SCP、install.sh", (590, 260))
arrow((1015, 390), (1015, 470), C["orange"], "MongoDB 連線", (1035, 425))
arrow((1220, 315), (1310, 315), C["green_dark"], "Edge API", (1235, 280))
arrow((1015, 390), (1480, 470), C["green_dark"], "寫入檔案與日誌", (1200, 430))
arrow((1015, 740), (335, 880), C["green_dark"], "SSH、Ansible、Runner 只讀採集", (525, 790))

box((760, 1080, 1810, 1165), "目前不等於終態", ["尚未是三機房高可用架構；MongoDB 尚未是 replica set；Claude 版不包含在本圖。Codex 測試時可另外用 127.0.0.1:8002 SSH 通道，但不列為正式入口。"], outline=C["orange"], title_color=C["orange"])
d.text((55, H - 40), "檔案：00_gpt_current_deployed_architecture_clean_v2.png；此版本使用 UTF-8 腳本與繁中字型重產。", font=FS, fill=C["muted"])

img.save(PATH)
print(PATH)
