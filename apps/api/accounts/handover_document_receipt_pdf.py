"""Build a print-ready, branded PDF for issued vehicle handover acknowledgments."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import os
import struct
import unicodedata
import zlib

from django.conf import settings
from django.utils import timezone
from PIL import Image


PAGE_WIDTH = 595.28
PAGE_HEIGHT = 841.89
LEFT = 29
RIGHT = 566
CONTENT_BOTTOM = 124
RED = (0.82, 0.035, 0.075)
INK = (0.055, 0.06, 0.07)
MID = (0.27, 0.29, 0.32)
MUTED = (0.39, 0.41, 0.44)
SILVER = (0.78, 0.79, 0.81)
PALE = (0.925, 0.93, 0.94)
WHITE = (1, 1, 1)


class _TrueTypeFont:
    """Read the small set of TrueType tables needed by an embedded PDF font."""

    def __init__(self, path):
        self.path = Path(path)
        self.data = self.path.read_bytes()
        table_count = struct.unpack_from(">H", self.data, 4)[0]
        self.tables = {}
        for index in range(table_count):
            offset = 12 + index * 16
            tag, _, start, length = struct.unpack_from(">4sIII", self.data, offset)
            self.tables[tag.decode("ascii")] = (start, length)
        self.units_per_em = struct.unpack_from(">H", self._table("head"), 18)[0]
        self.bbox = struct.unpack_from(">hhhh", self._table("head"), 36)
        hhea = self._table("hhea")
        self.ascent, self.descent = struct.unpack_from(">hh", hhea, 4)
        self.num_hmetrics = struct.unpack_from(">H", hhea, 34)[0]
        self.glyph_count = struct.unpack_from(">H", self._table("maxp"), 4)[0]
        self.advances = self._read_advances()
        self.cmap4, self.cmap12 = self._read_cmaps()
        self.cap_height = self._read_cap_height()

    def _table(self, name):
        start, length = self.tables[name]
        return self.data[start:start + length]

    def _read_advances(self):
        table = self._table("hmtx")
        widths = [struct.unpack_from(">H", table, index * 4)[0]
                  for index in range(self.num_hmetrics)]
        return widths + [widths[-1]] * (self.glyph_count - len(widths))

    def _read_cmaps(self):
        table = self._table("cmap")
        count = struct.unpack_from(">H", table, 2)[0]
        chosen4 = chosen12 = None
        for index in range(count):
            record = 4 + index * 8
            platform, encoding, offset = struct.unpack_from(">HHI", table, record)
            fmt = struct.unpack_from(">H", table, offset)[0]
            if fmt == 12 and (platform == 3 and encoding == 10 or chosen12 is None):
                chosen12 = table[offset:]
            elif fmt == 4 and (platform == 3 and encoding in (1, 10) or chosen4 is None):
                chosen4 = table[offset:]
        return chosen4, chosen12

    def _read_cap_height(self):
        os2 = self.tables.get("OS/2")
        if os2:
            start, length = os2
            if length >= 90 and struct.unpack_from(">H", self.data, start)[0] >= 2:
                return struct.unpack_from(">h", self.data, start + 88)[0]
        return self.ascent

    def glyph(self, codepoint):
        if codepoint < 0 or codepoint > 0xFFFF:
            return 0
        if self.cmap12:
            group_count = struct.unpack_from(">I", self.cmap12, 12)[0]
            low, high = 0, group_count
            while low < high:
                middle = (low + high) // 2
                start, end, start_glyph = struct.unpack_from(">III", self.cmap12, 16 + middle * 12)
                if codepoint < start:
                    high = middle
                elif codepoint > end:
                    low = middle + 1
                else:
                    return start_glyph + codepoint - start
        if not self.cmap4 or codepoint > 0xFFFF:
            return 0
        cmap = self.cmap4
        seg_count = struct.unpack_from(">H", cmap, 6)[0] // 2
        end_pos = 14
        start_pos = end_pos + seg_count * 2 + 2
        delta_pos = start_pos + seg_count * 2
        range_pos = delta_pos + seg_count * 2
        for segment in range(seg_count):
            end_code = struct.unpack_from(">H", cmap, end_pos + segment * 2)[0]
            if codepoint > end_code:
                continue
            start_code = struct.unpack_from(">H", cmap, start_pos + segment * 2)[0]
            if codepoint < start_code:
                return 0
            delta = struct.unpack_from(">h", cmap, delta_pos + segment * 2)[0]
            range_offset = struct.unpack_from(">H", cmap, range_pos + segment * 2)[0]
            if range_offset == 0:
                return (codepoint + delta) & 0xFFFF
            glyph_pos = range_pos + segment * 2 + range_offset + 2 * (codepoint - start_code)
            glyph_id = struct.unpack_from(">H", cmap, glyph_pos)[0]
            return (glyph_id + delta) & 0xFFFF if glyph_id else 0
        return 0

    def width(self, codepoint):
        glyph_id = self.glyph(codepoint)
        advance = self.advances[glyph_id] if glyph_id < len(self.advances) else self.advances[0]
        return advance * 1000 / self.units_per_em


def _font_paths():
    configured = {
        "regular": os.environ.get("SSP_HANDOVER_PDF_FONT_REGULAR"),
        "bold": os.environ.get("SSP_HANDOVER_PDF_FONT_BOLD"),
    }
    windows_fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    regular_candidates = [configured["regular"], windows_fonts / "arial.ttf",
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]
    bold_candidates = [configured["bold"], windows_fonts / "arialbd.ttf",
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")]
    regular = next((Path(path) for path in regular_candidates if path and Path(path).is_file()), None)
    bold = next((Path(path) for path in bold_candidates if path and Path(path).is_file()), None)
    if not regular or not bold:
        raise RuntimeError("Embedded handover PDF fonts are unavailable. Set SSP_HANDOVER_PDF_FONT_REGULAR and SSP_HANDOVER_PDF_FONT_BOLD.")
    return {"regular": _TrueTypeFont(regular), "bold": _TrueTypeFont(bold)}


def _logo_image():
    logo_path = Path(settings.REPO_ROOT) / "apps" / "web" / "public" / "branding" / "ssp-logo-display.png"
    with Image.open(logo_path) as source:
        rgba = source.convert("RGBA")
        image = Image.new("RGB", rgba.size, (8, 9, 11))
        image.paste(rgba, mask=rgba.getchannel("A"))
        image.thumbnail((1000, 420), Image.Resampling.LANCZOS)
        encoded = BytesIO()
        image.save(encoded, format="JPEG", quality=92, optimize=True)
        return image.width, image.height, encoded.getvalue()


def _display_text(value):
    value = unicodedata.normalize("NFC", str(value or ""))
    return "".join(char if ord(char) <= 0xFFFF else "?" for char in value)


def _wrap(value, font, size, width):
    lines = []
    for paragraph in _display_text(value).splitlines() or [""]:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            candidate_width = sum(font.width(ord(char) if font.glyph(ord(char)) else ord("?"))
                                  for char in candidate) * size / 1000
            if current and candidate_width > width:
                lines.append(current)
                current = word
            else:
                current = candidate
        lines.append(current)
    return lines


class _Pdf:
    def __init__(self):
        self.objects = [None]

    def reserve(self):
        self.objects.append(None)
        return len(self.objects) - 1

    def set(self, number, data):
        self.objects[number] = data

    def add(self, data):
        number = self.reserve()
        self.set(number, data)
        return number

    def stream(self, dictionary, content):
        return self.add(dictionary + b"\nstream\n" + content + b"\nendstream")

    def build(self, root):
        output = BytesIO()
        output.write(b"%PDF-1.7\n% SSP vehicle document acknowledgment\n")
        offsets = [0]
        for number, body in enumerate(self.objects[1:], 1):
            offsets.append(output.tell())
            output.write(f"{number} 0 obj\n".encode("ascii"))
            output.write(body)
            output.write(b"\nendobj\n")
        xref = output.tell()
        output.write(f"xref\n0 {len(self.objects)}\n0000000000 65535 f \n".encode("ascii"))
        for offset in offsets[1:]:
            output.write(f"{offset:010d} 00000 n \n".encode("ascii"))
        output.write(f"trailer\n<< /Size {len(self.objects)} /Root {root} 0 R >>\nstartxref\n{xref}\n%%EOF".encode("ascii"))
        return output.getvalue()


def _font_objects(pdf, font, resource_name, used_chars):
    prefix = resource_name
    font_file = pdf.stream(
        b"<< /Length1 " + str(len(font.data)).encode() + b" /Length " +
        str(len(zlib.compress(font.data))).encode() + b" /Filter /FlateDecode >>",
        zlib.compress(font.data),
    )
    scale = 1000 / font.units_per_em
    x_min, y_min, x_max, y_max = (round(value * scale) for value in font.bbox)
    descriptor = pdf.add(
        f"<< /Type /FontDescriptor /FontName /SSP{prefix} /Flags 32 /FontBBox [{x_min} {y_min} {x_max} {y_max}] "
        f"/ItalicAngle 0 /Ascent {round(font.ascent * scale)} /Descent {round(font.descent * scale)} "
        f"/CapHeight {round(font.cap_height * scale)} /StemV 90 /FontFile2 {font_file} 0 R >>".encode("ascii"))
    max_cid = max(used_chars, default=0)
    cid_to_gid = bytearray((max_cid + 1) * 2)
    widths = []
    unicode_entries = []
    for cid in sorted(used_chars):
        glyph_id = font.glyph(cid)
        struct.pack_into(">H", cid_to_gid, cid * 2, glyph_id)
        widths.append(f"{cid} [{round(font.width(cid))}]")
        unicode_entries.append(f"<{cid:04X}><{cid:04X}>")
    gid_map = pdf.stream(b"<< /Length " + str(len(cid_to_gid)).encode() + b" >>", bytes(cid_to_gid))
    cid_font = pdf.add(
        f"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /SSP{prefix} /CIDSystemInfo "
        f"<< /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> /FontDescriptor {descriptor} 0 R "
        f"/CIDToGIDMap {gid_map} 0 R /DW 1000 /W [{ ' '.join(widths) }] >>".encode("ascii"))
    chunks = [unicode_entries[index:index + 100] for index in range(0, len(unicode_entries), 100)]
    cmap = ["/CIDInit /ProcSet findresource begin", "12 dict begin", "begincmap",
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
        f"/CMapName /SSP{prefix}ToUnicode def", "/CMapType 2 def",
        "1 begincodespacerange", "<0000> <FFFF>", "endcodespacerange"]
    for chunk in chunks:
        cmap.append(f"{len(chunk)} beginbfchar")
        cmap.extend(chunk)
        cmap.append("endbfchar")
    cmap.extend(["endcmap", "CMapName currentdict /CMap defineresource pop", "end", "end"])
    cmap_bytes = "\n".join(cmap).encode("ascii")
    to_unicode = pdf.stream(b"<< /Length " + str(len(cmap_bytes)).encode() + b" >>", cmap_bytes)
    return pdf.add(f"<< /Type /Font /Subtype /Type0 /BaseFont /SSP{prefix} /Encoding /Identity-H "
        f"/DescendantFonts [{cid_font} 0 R] /ToUnicode {to_unicode} 0 R >>".encode("ascii"))


def build_handover_document_receipt_pdf(receipt):
    fonts = _font_paths()
    logo_width, logo_height, logo_data = _logo_image()
    pdf = _Pdf()
    catalog = pdf.reserve()
    pages_id = pdf.reserve()
    image_id = pdf.stream(
        f"<< /Type /XObject /Subtype /Image /Width {logo_width} /Height {logo_height} "
        f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {len(logo_data)} >>".encode("ascii"),
        logo_data,
    )
    used_chars = {"regular": set(), "bold": set()}
    pages = [[]]
    y = 0

    def add(op):
        pages[-1].append(op)

    def color(rgb, stroke=False):
        operator = "RG" if stroke else "rg"
        add(f"{rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f} {operator}")

    def rect(x, bottom, width, height, fill=None, stroke=None, line_width=0.7):
        if fill:
            color(fill)
            add(f"{x:.2f} {bottom:.2f} {width:.2f} {height:.2f} re f")
        if stroke:
            color(stroke, True)
            add(f"{line_width:.2f} w {x:.2f} {bottom:.2f} {width:.2f} {height:.2f} re S")

    def polygon(points, fill):
        color(fill)
        path = f"{points[0][0]:.2f} {points[0][1]:.2f} m "
        path += " ".join(f"{x:.2f} {y0:.2f} l" for x, y0 in points[1:]) + " h f"
        add(path)

    def line(x1, y1, x2, y2, stroke=SILVER, width=0.7):
        color(stroke, True)
        add(f"{width:.2f} w {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    def curve_path(segments, stroke, width=1.2):
        color(stroke, True)
        add(f"{width:.2f} w {segments[0][0]:.2f} {segments[0][1]:.2f} m " +
            " ".join(f"{x1:.2f} {y1:.2f} {x2:.2f} {y2:.2f} {x3:.2f} {y3:.2f} c"
                     for x1, y1, x2, y2, x3, y3 in segments[1:]) + " S")

    def text(value, x, baseline, size=9, bold=False, fill=INK):
        style = "bold" if bold else "regular"
        font = fonts[style]
        safe_chars = []
        for char in _display_text(value):
            codepoint = ord(char)
            if not font.glyph(codepoint):
                char = "?"
                codepoint = ord(char)
            used_chars[style].add(codepoint)
            safe_chars.append(char)
        value = "".join(safe_chars)
        encoded = value.encode("utf-16-be", "replace").hex().upper()
        color(fill)
        add(f"BT /{ 'F2' if bold else 'F1' } {size:.2f} Tf 1 0 0 1 {x:.2f} {baseline:.2f} Tm <{encoded}> Tj ET")

    def text_width(value, size=9, bold=False):
        font = fonts["bold" if bold else "regular"]
        return sum(font.width(ord(ch) if font.glyph(ord(ch)) else ord("?")) for ch in _display_text(value)) * size / 1000

    def wrapped(value, x, top, width, size=9, leading=12, bold=False, fill=INK, min_lines=None):
        font = fonts["bold" if bold else "regular"]
        lines = _wrap(value, font, size, width)
        for index, line_text in enumerate(lines):
            text(line_text, x, top - index * leading, size, bold, fill)
        if min_lines and len(lines) < min_lines:
            for index in range(len(lines), min_lines):
                text("", x, top - index * leading, size, bold, fill)
        return lines

    def draw_header(continued=False):
        rect(0, 760, PAGE_WIDTH, 82, fill=INK)
        # The diagonal chrome-red slash and dark automotive field replace no logo art.
        polygon([(376, 760), (414, 760), (468, 842), (430, 842)], RED)
        polygon([(408, 760), (595, 760), (595, 842), (461, 842)], (0.105, 0.025, 0.035))
        polygon([(426, 760), (438, 760), (491, 842), (479, 842)], (0.67, 0.025, 0.06))
        logo_h = 48
        logo_w = logo_h * logo_width / logo_height
        add(f"q {logo_w:.2f} 0 0 {logo_h:.2f} 34 777 cm /Logo Do Q")
        line(157, 783, 157, 824, RED, 2.3)
        text("SSP MOTOR TRADING", 174, 799, 18, True, WHITE)
        # Abstract headlamp, bonnet and grille linework, drawn as vectors.
        curve_path([(444, 782), (458, 793, 477, 797, 497, 796), (518, 794, 538, 789, 553, 779)], (0.88, 0.075, 0.12), 1.45)
        curve_path([(431, 773), (452, 769, 468, 770, 485, 774), (512, 781, 536, 784, 559, 781)], (0.65, 0.04, 0.075), 1.1)
        curve_path([(493, 790), (497, 797, 502, 804, 508, 810), (516, 817, 520, 826, 526, 837)], (0.87, 0.07, 0.12), 1.25)
        curve_path([(434, 780), (440, 785, 447, 786, 456, 785), (466, 784, 473, 780, 480, 775)], (0.95, 0.16, 0.19), 1.45)
        curve_path([(437, 780), (446, 780, 453, 779, 460, 777), (467, 776, 473, 773, 479, 772)], (0.86, 0.05, 0.1), 0.75)
        if continued:
            text("VEHICLE & DOCUMENT HANDOVER ACKNOWLEDGMENT — CONTINUED", 34, 741, 10, True, MID)

    def start_continuation():
        nonlocal y
        pages.append([])
        draw_header(continued=True)
        y = 714

    def section_banner(label):
        nonlocal y
        top = y
        rect(LEFT, top - 22, RIGHT - LEFT, 22, fill=PALE)
        polygon([(LEFT, top), (LEFT + 280, top), (LEFT + 267, top - 22), (LEFT, top - 22)], RED)
        text(label.upper(), LEFT + 16, top - 15.5, 10.2, True, WHITE)
        y = top - 34

    def draw_title():
        rect(29, 692, 6, 48, fill=RED)
        text("VEHICLE & DOCUMENT", 48, 722, 20, True, INK)
        text("HANDOVER ACKNOWLEDGMENT", 48, 697, 20, True, INK)
        rect(414, 696, 152, 48, fill=PALE)
        text("Reference Code", 426, 725, 9.2, False, INK)
        ref = _display_text(receipt.reference)
        ref_size = min(11.6, max(8, 1270 / max(1, text_width(ref, 1, True))))
        text(ref, 426, 705, ref_size, True, INK)
        rect(LEFT, 675, RIGHT - LEFT, 3.4, fill=RED)

    def draw_details():
        nonlocal y
        rows = [
            ("Receipt issued", timezone.localtime(receipt.issued_at).strftime("%Y-%m-%d %H:%M %z")),
            ("Customer", receipt.customer_name),
            ("Vehicle", receipt.vehicle_name),
            ("Vehicle reference", receipt.vehicle_reference),
            ("Sale reference", receipt.sale_reference),
            ("Handover reference", receipt.handover.reference),
            ("Delivery date", receipt.delivery_date.isoformat()),
        ]
        label_width = 162
        value_width = RIGHT - LEFT - label_width - 18
        row_heights = [max(24, len(_wrap(value, fonts["bold"], 10.4, value_width)) * 13 + 9) for _, value in rows]
        total = sum(row_heights)
        top = 659
        bottom = top - total
        rect(LEFT, bottom, RIGHT - LEFT, total, fill=WHITE, stroke=SILVER, line_width=0.8)
        rect(LEFT, bottom, label_width, total, fill=PALE)
        row_top = top
        for index, ((label, value), row_height) in enumerate(zip(rows, row_heights)):
            if index:
                line(LEFT, row_top, RIGHT, row_top, SILVER, 0.6)
            line(LEFT + label_width, row_top, LEFT + label_width, row_top - row_height, SILVER, 0.6)
            label_lines = _wrap(label, fonts["regular"], 10.2, label_width - 22)
            for label_index, label_line in enumerate(label_lines):
                text(label_line, LEFT + 17, row_top - 15 - label_index * 12, 10.2, False, INK)
            value_lines = _wrap(value, fonts["bold"], 10.4, value_width)
            for value_index, value_line in enumerate(value_lines):
                text(value_line, LEFT + label_width + 20, row_top - 15 - value_index * 13, 10.4, True, INK)
            row_top -= row_height
        y = bottom - 24

    def draw_checklist():
        nonlocal y
        section_banner("Company and vehicle items handed over")
        box_top = y + 1
        box_height = 96
        rect(LEFT, box_top - box_height, RIGHT - LEFT, box_height, fill=WHITE, stroke=SILVER, line_width=0.8)
        canonical = [
            ("keys", "Keys"),
            ("registration_documents", "Registration documents"),
            ("insurance_documents", "Insurance documents"),
            ("service_documents", "Service documents"),
        ]
        completed = set()
        labels = {"Keys": "keys", "Registration documents": "registration_documents",
                  "Insurance documents": "insurance_documents", "Service documents": "service_documents"}
        for item in receipt.items_handed_over or []:
            if isinstance(item, dict):
                key = item.get("key") or labels.get(item.get("label"))
                if key:
                    completed.add(key)
        for index, (key, label) in enumerate(canonical):
            row_top = box_top - 16 - index * 20
            if key in completed:
                rect(LEFT + 20, row_top - 9, 11, 11, fill=RED, stroke=RED, line_width=0.8)
                # White vector tick, never an X glyph.
                line(LEFT + 22.2, row_top - 4.4, LEFT + 24.5, row_top - 6.8, WHITE, 1.45)
                line(LEFT + 24.5, row_top - 6.8, LEFT + 29.5, row_top - 1.6, WHITE, 1.45)
            else:
                rect(LEFT + 20, row_top - 9, 11, 11, stroke=RED, line_width=1.1)
            text(label, LEFT + 46, row_top, 10.5, False, INK)
        y = box_top - box_height - 20

    def draw_acknowledgment():
        nonlocal y
        label = "Customer acknowledgment"
        content = _display_text(receipt.customer_acknowledgement or "I acknowledge receipt of the items listed above.")
        section_banner(label)
        font = fonts["regular"]
        lines = _wrap(content, font, 11, RIGHT - LEFT - 38)
        first = True
        while lines:
            available = y - CONTENT_BOTTOM - 19
            max_lines = max(1, int((available - 18) / 14))
            if not first or max_lines < 2:
                start_continuation()
                section_banner(label + " (continued)")
                available = y - CONTENT_BOTTOM - 19
                max_lines = max(1, int((available - 18) / 14))
            chunk, lines = lines[:max_lines], lines[max_lines:]
            box_height = max(48, len(chunk) * 14 + 23)
            if box_height > y - CONTENT_BOTTOM:
                start_continuation()
                section_banner(label + " (continued)")
                continue
            top = y - 2
            rect(LEFT, top - box_height, RIGHT - LEFT, box_height, fill=WHITE, stroke=SILVER, line_width=0.8)
            for index, line_text in enumerate(chunk):
                text(line_text, LEFT + 18, top - 18 - index * 14, 11, False, INK)
            y = top - box_height - 18
            first = False

    def draw_signatures():
        nonlocal y
        if y - 77 < CONTENT_BOTTOM:
            start_continuation()
        top = y - 5
        col2 = LEFT + 284
        text("Customer name", LEFT + 2, top, 10.3, False, INK)
        line(LEFT + 92, top - 2, LEFT + 263, top - 2, MUTED, 0.75)
        text("Signature", col2 + 2, top, 10.3, False, INK)
        line(col2 + 69, top - 2, RIGHT - 2, top - 2, MUTED, 0.75)
        second = top - 31
        text("Date", LEFT + 2, second, 10.3, False, INK)
        line(LEFT + 92, second - 2, LEFT + 263, second - 2, MUTED, 0.75)
        text("Issued by", col2 + 2, second, 10.3, False, INK)
        text(receipt.issued_by_name, col2 + 69, second, 10.3, True, INK)
        line(col2 + 69, second - 2, RIGHT - 2, second - 2, MUTED, 0.75)
        y = second - 20

    draw_header()
    draw_title()
    draw_details()
    draw_checklist()
    draw_acknowledgment()
    draw_signatures()

    # Add the footer only after pagination has settled, so the page count is accurate.
    page_count = len(pages)
    for index, operations in enumerate(pages, 1):
        operations.extend(_footer_ops(receipt, index, page_count, fonts, used_chars, LEFT, RIGHT,
                                      PAGE_WIDTH, RED, INK, MUTED, SILVER))

    regular_font = _font_objects(pdf, fonts["regular"], "Regular", used_chars["regular"])
    bold_font = _font_objects(pdf, fonts["bold"], "Bold", used_chars["bold"])
    resources = f"<< /Font << /F1 {regular_font} 0 R /F2 {bold_font} 0 R >> /XObject << /Logo {image_id} 0 R >> >>"
    page_refs = []
    for operations in pages:
        page_id = pdf.reserve()
        content_id = pdf.reserve()
        page_refs.append(f"{page_id} 0 R")
        content = "\n".join(operations).encode("ascii")
        pdf.set(page_id, (f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_WIDTH:.2f} {PAGE_HEIGHT:.2f}] "
                          f"/Resources {resources} /Contents {content_id} 0 R >>").encode("ascii"))
        pdf.set(content_id, b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"\nendstream")
    pdf.set(pages_id, (f"<< /Type /Pages /Kids [{' '.join(page_refs)}] /Count {len(pages)} >>").encode("ascii"))
    pdf.set(catalog, f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("ascii"))
    return pdf.build(catalog)


def _footer_ops(receipt, page_number, page_count, fonts, used_chars, left, right,
                page_width, red, ink, muted, silver):
    # Footer drawing is collected separately so adding it cannot disturb content-flow decisions.
    ops = []

    def set_color(rgb, stroke=False):
        op = "RG" if stroke else "rg"
        ops.append(f"{rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f} {op}")

    def line(x1, y1, x2, y2, color, width):
        set_color(color, True)
        ops.append(f"{width:.2f} w {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    def curve(segments, color, width):
        set_color(color, True)
        ops.append(f"{width:.2f} w {segments[0][0]:.2f} {segments[0][1]:.2f} m " +
                   " ".join(f"{a:.2f} {b:.2f} {c:.2f} {d:.2f} {e:.2f} {f:.2f} c"
                            for a, b, c, d, e, f in segments[1:]) + " S")

    def rect(x, y, w, h, color):
        set_color(color)
        ops.append(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re f")

    def poly(points, color):
        set_color(color)
        ops.append(f"{points[0][0]:.2f} {points[0][1]:.2f} m " +
                   " ".join(f"{x:.2f} {y:.2f} l" for x, y in points[1:]) + " h f")

    def text(value, x, y, size, bold, color):
        style = "bold" if bold else "regular"
        font = fonts[style]
        value = _display_text(value)
        output = []
        for char in value:
            codepoint = ord(char)
            if not font.glyph(codepoint):
                codepoint = ord("?")
            used_chars[style].add(codepoint)
            output.append(f"{codepoint:04X}")
        set_color(color)
        ops.append(f"BT /{'F2' if bold else 'F1'} {size:.2f} Tf 1 0 0 1 {x:.2f} {y:.2f} Tm <{''.join(output)}> Tj ET")

    line(left, 112, right, 112, red, 1.2)
    text("This document acknowledges delivery of the listed vehicle/company items only.", left, 92, 9.3, False, ink)
    text("It is not a payment receipt and does not evidence payment or settlement of any sale balance.", left, 76, 9.3, True, ink)
    curve([(427, 48), (447, 67, 462, 72, 482, 72), (502, 72, 520, 65, 533, 53)], (0.74, 0.75, 0.77), 1.6)
    curve([(413, 43), (432, 57, 446, 60, 461, 59), (485, 57, 503, 47, 518, 43)], (0.80, 0.81, 0.83), 1.2)
    curve([(475, 46), (488, 62, 503, 66, 519, 63), (534, 60, 547, 54, 560, 49)], (0.79, 0.80, 0.82), 1.1)
    rect(0, 0, page_width, 26, ink)
    poly([(328, 0), (347, 26), (374, 26), (356, 0)], red)
    poly([(351, 0), (369, 26), (page_width, 26), (page_width, 0)], (0.76, 0.025, 0.065))
    if page_count > 1:
        text(f"{receipt.reference}  |  Page {page_number} of {page_count}", right - 142, 36, 7.2, False, muted)
    return ops
