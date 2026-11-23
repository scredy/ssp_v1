"""Build printable PDFs for issued vehicle document acknowledgments."""
from io import BytesIO
import textwrap
import unicodedata

from django.utils import timezone


def _safe(value):
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_handover_document_receipt_pdf(receipt):
    ops = []

    def text(value, x, y, size=10, bold=False):
        font = "F2" if bold else "F1"
        ops.append(f"0.12 0.14 0.17 rg BT /{font} {size} Tf 1 0 0 1 {x} {y} Tm ({_safe(value)}) Tj ET")

    def line(x1, y1, x2, y2, color="0.72 0.74 0.77"):
        ops.append(f"{color} RG 0.8 w {x1} {y1} m {x2} {y2} l S")

    def paragraph(value, y, width=91, size=9.5, leading=13):
        for raw in str(value or "").splitlines() or [""]:
            for chunk in textwrap.wrap(raw, width=width, break_long_words=True, break_on_hyphens=True) or [""]:
                text(chunk, 48, y, size)
                y -= leading
        return y

    ops.append("0.93 0.94 0.95 rg 0 755 595 87 re f")
    ops.append("0.78 0.04 0.08 rg 0 751 595 4 re f")
    text("SSP MOTOR TRADING", 44, 807, 12, True)
    text("VEHICLE & DOCUMENT HANDOVER ACKNOWLEDGMENT", 44, 781, 13, True)
    text(receipt.reference, 442, 807, 9, True)
    y = 720
    text("Receipt issued", 48, y, 9)
    text(timezone.localtime(receipt.issued_at).strftime("%Y-%m-%d %H:%M %Z"), 145, y, 9, True)
    y -= 28

    for label, value in (("Customer", receipt.customer_name), ("Vehicle", receipt.vehicle_name),
                         ("Vehicle reference", receipt.vehicle_reference), ("Sale reference", receipt.sale_reference),
                         ("Handover reference", receipt.handover.reference), ("Delivery date", receipt.delivery_date.isoformat())):
        text(label, 48, y, 9)
        text(value, 185, y, 10, True)
        y -= 21

    y -= 5
    text("Company and vehicle items handed over", 48, y, 10, True)
    y -= 17
    for item in receipt.items_handed_over:
        text("[x]", 56, y, 10, True)
        y = paragraph(item.get("label", ""), y, width=78, size=10, leading=14)
        y -= 3

    y -= 6
    text("Customer acknowledgment", 48, y, 10, True)
    y -= 16
    y = paragraph(receipt.customer_acknowledgement or "I acknowledge receipt of the items listed above.", y, width=92, size=9)
    y -= 28
    text("Customer name", 48, y, 9)
    line(145, y - 3, 320, y - 3)
    text("Signature", 345, y, 9)
    line(405, y - 3, 548, y - 3)
    y -= 30
    text("Date", 48, y, 9)
    line(145, y - 3, 250, y - 3)
    text("Issued by", 345, y, 9)
    text(receipt.issued_by_name, 405, y, 9, True)

    line(48, 92, 548, 92, "0.78 0.04 0.08")
    text("This document acknowledges delivery of the listed vehicle/company items only.", 48, 75, 8)
    text("It is not a payment receipt and does not evidence payment or settlement of any sale balance.", 48, 61, 8, True)

    objects = [b"", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"]
    content = "\n".join(ops).encode("latin-1", "replace")
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = b"<< /Type /Pages /Kids [5 0 R] /Count 1 >>"
    page = b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents 6 0 R >>"
    stream = b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream"
    objects.extend([page, stream])

    output = BytesIO()
    output.write(b"%PDF-1.4\n% SSP vehicle document acknowledgment\n")
    offsets = [0]
    for number, body in enumerate(objects, 1):
        offsets.append(output.tell())
        output.write(f"{number} 0 obj\n".encode())
        output.write(body)
        output.write(b"\nendobj\n")
    xref = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode())
    output.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return output.getvalue()
