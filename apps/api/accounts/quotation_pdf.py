"""Small dependency-free A4 PDF renderer for issued quotation snapshots."""
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from pathlib import Path
import re
import textwrap
import unicodedata

from django.conf import settings
from PIL import Image


def _safe(value):
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _money(value):
    return f"LKR {Decimal(str(value or 0)):,.2f}"


def _image_jpeg():
    logo = settings.BASE_DIR.parent / "web" / "public" / "branding" / "ssp-logo-display.png"
    with Image.open(logo) as source:
        source.load()
        rgba = source.convert("RGBA")
        background = Image.new("RGB", rgba.size, (8, 9, 11))
        background.paste(rgba, mask=rgba.getchannel("A"))
        output = BytesIO()
        background.save(output, format="JPEG", quality=88, optimize=True)
        return output.getvalue(), background.width, background.height


class _Page:
    def __init__(self):
        self.ops = []
        self.y = 730

    def rect(self, x, y, w, h, rgb):
        self.ops.append(f"{rgb[0]} {rgb[1]} {rgb[2]} rg {x} {y} {w} {h} re f")

    def line(self, x1, y1, x2, y2, rgb=(0.72, 0.74, 0.77), width=0.7):
        self.ops.append(f"{rgb[0]} {rgb[1]} {rgb[2]} RG {width} w {x1} {y1} m {x2} {y2} l S")

    def text(self, value, x, y, size=10, bold=False, rgb=(0.12, 0.14, 0.17)):
        self.ops.append(f"{rgb[0]} {rgb[1]} {rgb[2]} rg BT /{'F2' if bold else 'F1'} {size} Tf 1 0 0 1 {x} {y} Tm ({_safe(value)}) Tj ET")

    def paragraph(self, value, x=42, width=98, size=9.5, leading=13, bold=False):
        for raw in str(value or "").splitlines() or [""]:
            lines = textwrap.wrap(raw, width=width, break_long_words=True, break_on_hyphens=True) or [""]
            for line in lines:
                if self.y < 54:
                    self.y = 770
                self.text(line, x, self.y, size, bold)
                self.y -= leading


def build_quotation_pdf(snapshot):
    jpeg, image_width, image_height = _image_jpeg()
    pages = [_Page()]
    page = pages[0]

    def new_page():
        nonlocal page
        page = _Page()
        pages.append(page)
        page.rect(0, 831, 595, 11, (0.035, 0.04, 0.05))
        page.rect(0, 827, 595, 4, (0.78, 0.04, 0.08))
        page.text(f"QUOTATION {snapshot['reference']} - CONTINUED", 42, 805, 10, True)
        page.y = 780

    def ensure_room(height):
        if page.y - height < 52:
            new_page()

    def paragraph(value, x=42, width=98, size=9.5, leading=13, bold=False):
        nonlocal page
        for raw in str(value or "").splitlines() or [""]:
            lines = textwrap.wrap(raw, width=width, break_long_words=True, break_on_hyphens=True) or [""]
            for line in lines:
                ensure_room(leading)
                page.text(line, x, page.y, size, bold)
                page.y -= leading

    def section(label):
        ensure_room(42)
        page.y -= 10
        page.text(label.upper(), 42, page.y, 9, True, (0.70, 0.07, 0.10))
        page.y -= 8
        page.line(42, page.y, 553, page.y)
        page.y -= 20

    def row(label, value):
        ensure_room(18)
        page.text(label, 42, page.y, 9, False, (0.38, 0.41, 0.45))
        page.text(value, 230, page.y, 9, True)
        page.y -= 17

    page.rect(0, 755, 595, 87, (0.035, 0.04, 0.05))
    page.rect(0, 751, 595, 4, (0.78, 0.04, 0.08))
    page.ops.append("q 175 0 0 76 39 761 cm /Im1 Do Q")
    page.text("VEHICLE QUOTATION", 351, 802, 13, True, (1, 1, 1))
    page.text(snapshot["reference"], 351, 779, 10, True, (0.86, 0.87, 0.89))
    page.y = 723
    page.text("Issue date", 42, page.y, 9, False, (0.38, 0.41, 0.45))
    page.text(snapshot["issue_date"], 112, page.y, 9, True)
    page.text("Valid until", 340, page.y, 9, False, (0.38, 0.41, 0.45))
    page.text(snapshot["expiry_date"], 398, page.y, 9, True)
    page.y -= 22

    section("Prepared for")
    customer = snapshot.get("customer", {})
    page.text(customer.get("full_name", ""), 42, page.y, 12, True)
    page.y -= 17
    contact = " | ".join(v for v in (customer.get("email", ""), customer.get("phone", "")) if v)
    if contact:
        paragraph(contact, width=105, size=9)
    page.y -= 3

    section("Vehicle details")
    paragraph(snapshot.get("vehicle_description", ""), size=10, bold=True)
    for key, value in (snapshot.get("vehicle_specifications") or {}).items():
        if value not in (None, "", []):
            row(re.sub(r"_", " ", key).title(), str(value))
    page.y -= 2

    section("Price breakdown")
    row("Vehicle selling price", _money(snapshot["vehicle_selling_price_lkr"]))
    if Decimal(snapshot.get("additional_charges_lkr", "0")):
        row("Additional charges", _money(snapshot["additional_charges_lkr"]))
    if Decimal(snapshot.get("discount_lkr", "0")):
        row("Discount", f"- {_money(snapshot['discount_lkr'])}")
    ensure_room(50)
    page.rect(42, page.y - 7, 511, 34, (0.08, 0.09, 0.11))
    page.text("QUOTATION TOTAL", 54, page.y + 5, 10, True, (1, 1, 1))
    page.text(_money(snapshot["quotation_total_lkr"]), 407, page.y + 5, 12, True, (1, 1, 1))
    page.y -= 51

    finance_estimates = snapshot.get("finance_estimates")
    if finance_estimates is None:
        legacy_estimate = snapshot.get("finance_estimate")
        finance_estimates = [legacy_estimate] if legacy_estimate else []
    if finance_estimates:
        section("Illustrative finance estimates")
        for finance in finance_estimates:
            row("Product / term", finance["term_label"])
            row("Amount financed", _money(finance["financed_amount_lkr"]))
            rate = Decimal(str(finance["rate_per_100k_lkr"]))
            row("Formula / rate", f"Financed / LKR 100,000 x {_money(rate)} / month")
            row("Estimated monthly payment", _money(finance["monthly_estimate_lkr"]))
        paragraph("All figures are illustrative estimates, not a confirmed lender offer, approval, or guaranteed payment. Amount financed is vehicle price less down payment. The monthly formula uses the stated rate per LKR 100,000 financed.", width=112, size=8.5, leading=11)

    terms = snapshot.get("customer_terms", "").strip()
    if terms:
        section("Customer-visible terms")
        paragraph(terms, width=112, size=9, leading=12)
    page.y -= 10
    ensure_room(28)
    page.line(42, max(38, page.y), 553, max(38, page.y), (0.78, 0.04, 0.08), 1.2)
    page.text("This quotation records the prices and terms listed above.", 42, max(24, page.y - 15), 8, False, (0.45, 0.47, 0.50))

    objects = []
    def add(data):
        objects.append(data if isinstance(data, bytes) else data.encode("latin-1", "replace"))
        return len(objects)

    catalog_id = add(b"")
    pages_id = add(b"")
    font_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    bold_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    image_id = add(b"")
    page_ids = []
    for current in pages:
        content = "\n".join(current.ops).encode("latin-1", "replace")
        page_id = len(objects) + 1
        content_id = page_id + 1
        page_ids.append(page_id)
        add(f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 {font_id} 0 R /F2 {bold_id} 0 R >> /XObject << /Im1 {image_id} 0 R >> >> /Contents {content_id} 0 R >>")
        add(b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream")
    add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>")
    # Catalog and Pages are first for stable object numbering; replace their placeholders.
    objects[catalog_id - 1] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode()
    kids = " ".join(f"{item} 0 R" for item in page_ids)
    objects[pages_id - 1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode()
    objects[image_id - 1] = (f"<< /Type /XObject /Subtype /Image /Width {image_width} /Height {image_height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {len(jpeg)} >>\nstream\n".encode() + jpeg + b"\nendstream")

    output = BytesIO()
    output.write(b"%PDF-1.4\n% SSP quotation\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(output.tell())
        output.write(f"{number} 0 obj\n".encode())
        output.write(body)
        output.write(b"\nendobj\n")
    xref = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode())
    output.write(f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return output.getvalue()
