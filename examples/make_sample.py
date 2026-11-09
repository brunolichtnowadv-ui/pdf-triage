# Builds an invented sample PDF: native text, repeated logo, vector chart, scanned page with stamp.
import io, random
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from PIL import Image, ImageDraw, ImageFont

W, H = A4
def font(sz):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf"):
        try: return ImageFont.truetype(f, sz)
        except Exception: pass
    return ImageFont.load_default()

logo = Image.new("RGB", (300, 300), "white"); d = ImageDraw.Draw(logo)
d.ellipse((20, 20, 280, 280), outline=(20, 60, 140), width=14); d.rectangle((110, 110, 190, 190), fill=(20, 60, 140))
bl = io.BytesIO(); logo.save(bl, "PNG"); bl.seek(0); logo_reader = ImageReader(bl)

scan = Image.new("RGB", (1654, 2339), "white"); d = ImageDraw.Draw(scan)
f = font(34); y = 160
for ln in ["SERVICES AGREEMENT - SAMPLE", "", "Clause 1. The supplier shall deliver the monthly report",
           "within ten business days after the end of each month.", "", "Clause 2. Late delivery incurs a fixed penalty of two",
           "percent of the monthly fee, limited to ten percent.", "", "Clause 3. Either party may terminate this agreement",
           "with thirty days written notice to the other party.", "", "Signed in the city of Exampleville, on the first day of March."]:
    d.text((150, y), ln, fill=(20, 20, 20), font=f); y += 62
d.ellipse((1000, 1500, 1450, 1950), outline=(190, 20, 40), width=12)
d.text((1070, 1690), "RECEIVED", fill=(190, 20, 40), font=font(60))
random.seed(1); pts = [(300 + i * 18, 1900 + random.randint(-35, 35)) for i in range(40)]
d.line(pts, fill=(10, 20, 120), width=7)
bs = io.BytesIO(); scan.save(bs, "PNG"); bs.seek(0); scan_reader = ImageReader(bs)

c = canvas.Canvas("sample.pdf", pagesize=A4)
for p in range(1, 5):
    c.drawImage(logo_reader, 40, H - 90, 50, 50)
    if p in (1, 2):
        c.setFont("Helvetica", 12); c.drawString(100, H - 130, f"Native text page {p}. This page is plain digital text.")
        for k in range(30): c.drawString(60, H - 170 - 16 * k, "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor.")
    if p == 3:
        c.setFont("Helvetica", 12); c.drawString(100, H - 130, "Page 3: a vector chart drawn inside the PDF.")
        c.setLineWidth(2)
        import math
        for i in range(24):  # separate curve segments so the page counts as a vector chart
            x = 80 + i * 20; y = 300 + 120 * math.sin(i / 3)
            pth = c.beginPath(); pth.moveTo(x, y); pth.curveTo(x + 6, y + 30, x + 14, y + 30, x + 20, y + 10); c.drawPath(pth, stroke=1, fill=0)
    if p == 4:
        c.drawImage(scan_reader, 0, 0, W, H)
    c.showPage()
c.save()
