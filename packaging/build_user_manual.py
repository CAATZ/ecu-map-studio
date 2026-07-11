from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
SCREENSHOTS = ROOT / "tmp" / "pdfs" / "screenshots"
OUTPUT = ROOT / "output" / "pdf" / "ECU_Map_Studio_User_Manual.pdf"
ICON = ROOT / "assets" / "ECUMapStudio.png"
EXE = ROOT / "dist" / "ECUMapStudio.exe"

NAVY = colors.HexColor("#080D18")
NAVY_2 = colors.HexColor("#111827")
INK = colors.HexColor("#162033")
MUTED = colors.HexColor("#5F6F84")
CYAN = colors.HexColor("#20BFD0")
CYAN_LIGHT = colors.HexColor("#E8FAFC")
AMBER = colors.HexColor("#B87808")
AMBER_LIGHT = colors.HexColor("#FFF5DD")
RED_LIGHT = colors.HexColor("#FDECEC")
GRID = colors.HexColor("#D7DEE8")
PAPER = colors.HexColor("#F7F9FC")


def register_fonts() -> tuple[str, str]:
    regular = Path("C:/Windows/Fonts/segoeui.ttf")
    semibold = Path("C:/Windows/Fonts/seguisb.ttf")
    if regular.exists() and semibold.exists():
        pdfmetrics.registerFont(TTFont("ManualSans", str(regular)))
        pdfmetrics.registerFont(TTFont("ManualSansBold", str(semibold)))
        return "ManualSans", "ManualSansBold"
    return "Helvetica", "Helvetica-Bold"


FONT, FONT_BOLD = register_fonts()


def stylesheet():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            "ManualTitle",
            fontName=FONT_BOLD,
            fontSize=30,
            leading=35,
            textColor=colors.white,
            alignment=TA_CENTER,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            "CoverSub",
            fontName=FONT,
            fontSize=13,
            leading=18,
            textColor=colors.HexColor("#B9C8DA"),
            alignment=TA_CENTER,
        )
    )
    styles.add(
        ParagraphStyle(
            "H1Manual",
            fontName=FONT_BOLD,
            fontSize=22,
            leading=27,
            textColor=INK,
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            "H2Manual",
            fontName=FONT_BOLD,
            fontSize=13,
            leading=17,
            textColor=INK,
            spaceBefore=7,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            "BodyManual",
            fontName=FONT,
            fontSize=9.4,
            leading=13.5,
            textColor=INK,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            "SmallManual",
            fontName=FONT,
            fontSize=7.8,
            leading=10.5,
            textColor=MUTED,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            "BulletManual",
            fontName=FONT,
            fontSize=9.2,
            leading=13,
            leftIndent=12,
            firstLineIndent=-8,
            textColor=INK,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            "StepNumber",
            fontName=FONT_BOLD,
            fontSize=13,
            leading=16,
            textColor=colors.white,
            alignment=TA_CENTER,
        )
    )
    styles.add(
        ParagraphStyle(
            "StepText",
            fontName=FONT,
            fontSize=9.2,
            leading=13,
            textColor=INK,
        )
    )
    styles.add(
        ParagraphStyle(
            "Caption",
            fontName=FONT,
            fontSize=7.5,
            leading=10,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceBefore=3,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            "TableHeader",
            fontName=FONT_BOLD,
            fontSize=8,
            leading=10.5,
            textColor=colors.white,
        )
    )
    styles.add(
        ParagraphStyle(
            "CodeManual",
            fontName="Courier",
            fontSize=7.7,
            leading=10.5,
            textColor=colors.HexColor("#E6EEF8"),
        )
    )
    return styles


STYLES = stylesheet()


def body(text: str) -> Paragraph:
    return Paragraph(text, STYLES["BodyManual"])


def h1(text: str) -> Paragraph:
    return Paragraph(text, STYLES["H1Manual"])


def h2(text: str) -> Paragraph:
    return Paragraph(text, STYLES["H2Manual"])


def bullet(text: str) -> Paragraph:
    return Paragraph(f"- {text}", STYLES["BulletManual"])


def box(text: str, kind: str = "info") -> Table:
    background, border = {
        "info": (CYAN_LIGHT, CYAN),
        "warning": (AMBER_LIGHT, AMBER),
        "danger": (RED_LIGHT, colors.HexColor("#C74444")),
    }[kind]
    table = Table([[Paragraph(text, STYLES["BodyManual"])]], colWidths=[174 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("BOX", (0, 0), (-1, -1), 0.8, border),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def step(number: int, title: str, text: str) -> Table:
    number_cell = Table(
        [[Paragraph(str(number), STYLES["StepNumber"])]],
        colWidths=[11 * mm],
        rowHeights=[11 * mm],
    )
    number_cell.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), CYAN),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOX", (0, 0), (-1, -1), 0, CYAN),
            ]
        )
    )
    text_cell = Paragraph(f"<b>{title}</b><br/>{text}", STYLES["StepText"])
    result = Table([[number_cell, text_cell]], colWidths=[15 * mm, 159 * mm])
    result.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return result


def screenshot(filename: str, caption: str, max_height: float = 112 * mm):
    path = SCREENSHOTS / filename
    with PILImage.open(path) as image:
        width, height = image.size
    max_width = 174 * mm
    scale = min(max_width / width, max_height / height)
    picture = Image(str(path), width=width * scale, height=height * scale)
    frame = Table([[picture]], colWidths=[width * scale])
    frame.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.7, GRID),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return KeepTogether([frame, Paragraph(caption, STYLES["Caption"])])


def data_table(rows, widths, header=True) -> Table:
    converted = []
    for row_index, row in enumerate(rows):
        style = STYLES["TableHeader"] if header and row_index == 0 else STYLES["SmallManual"]
        converted.append([Paragraph(str(cell), style) for cell in row])
    table = Table(converted, colWidths=widths, repeatRows=1 if header else 0)
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.45, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PAPER]),
    ]
    if header:
        commands.extend(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY_2),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
            ]
        )
    table.setStyle(TableStyle(commands))
    return table


def code_block(lines: list[str]) -> Table:
    content = "<br/>".join(line.replace("&", "&amp;").replace("<", "&lt;") for line in lines)
    table = Table([[Paragraph(content, STYLES["CodeManual"])]], colWidths=[174 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), NAVY_2),
                ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#33445E")),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def page_header_footer(canvas, document) -> None:
    canvas.saveState()
    width, height = A4
    canvas.setFillColor(NAVY)
    canvas.rect(0, height - 17 * mm, width, 17 * mm, fill=1, stroke=0)
    canvas.setFont(FONT_BOLD, 8.5)
    canvas.setFillColor(colors.white)
    canvas.drawString(18 * mm, height - 10.8 * mm, "ECU Map Studio")
    canvas.setFont(FONT, 8)
    canvas.setFillColor(colors.HexColor("#AFC0D5"))
    canvas.drawRightString(width - 18 * mm, height - 10.8 * mm, "User Manual | Version 1.1.0")
    canvas.setStrokeColor(GRID)
    canvas.line(18 * mm, 13 * mm, width - 18 * mm, 13 * mm)
    canvas.setFont(FONT, 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(
        18 * mm, 8.5 * mm, "Numerical calibration aid - validate every change on the vehicle"
    )
    canvas.drawRightString(width - 18 * mm, 8.5 * mm, f"Page {document.page}")
    canvas.restoreState()


def cover_page(canvas, document) -> None:
    canvas.saveState()
    width, height = A4
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, width, height, fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor("#102033"))
    canvas.circle(width * 0.15, height * 0.12, 95 * mm, fill=1, stroke=0)
    canvas.setStrokeColor(CYAN)
    canvas.setLineWidth(2)
    canvas.line(42 * mm, 38 * mm, width - 42 * mm, 38 * mm)
    canvas.restoreState()


def file_metadata() -> tuple[str, str, str]:
    if not EXE.exists():
        return "Not built", "Not available", "Not available"
    digest = hashlib.sha256()
    with EXE.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    size = f"{EXE.stat().st_size / (1024 * 1024):.2f} MB"
    modified = datetime.fromtimestamp(EXE.stat().st_mtime).strftime("%Y-%m-%d")
    return size, modified, digest.hexdigest().upper()


def build_story():
    story = []
    size, build_date, checksum = file_metadata()

    # Cover
    story.extend(
        [
            Spacer(1, 28 * mm),
            Image(str(ICON), width=43 * mm, height=43 * mm, hAlign="CENTER"),
            Spacer(1, 9 * mm),
            Paragraph("ECU Map Studio", STYLES["ManualTitle"]),
            Paragraph("Friendly User Manual", STYLES["ManualTitle"]),
            Spacer(1, 4 * mm),
            Paragraph(
                "Resize, inspect, edit, smooth, compare, and copy ECU calibration tables "
                "without using Excel as an intermediate step.",
                STYLES["CoverSub"],
            ),
            Spacer(1, 22 * mm),
            Table(
                [
                    [
                        Paragraph("Version 1.1.0", STYLES["CoverSub"]),
                        Paragraph(f"Windows build {build_date}", STYLES["CoverSub"]),
                    ]
                ],
                colWidths=[82 * mm, 82 * mm],
            ),
            Spacer(1, 15 * mm),
            Table(
                [
                    [
                        Paragraph(
                            "IMPORTANT: This software performs numerical transformations. It cannot "
                            "determine whether ignition, fuel, boost, or another calibration is safe "
                            "for an engine. Review, log, instrument, and validate every result.",
                            ParagraphStyle(
                                "CoverWarning",
                                parent=STYLES["BodyManual"],
                                textColor=colors.HexColor("#FFE0A0"),
                                alignment=TA_CENTER,
                            ),
                        )
                    ]
                ],
                colWidths=[155 * mm],
                style=TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#2B2415")),
                        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#8C651D")),
                        ("LEFTPADDING", (0, 0), (-1, -1), 11),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 11),
                        ("TOPPADDING", (0, 0), (-1, -1), 10),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                    ]
                ),
                hAlign="CENTER",
            ),
            PageBreak(),
        ]
    )

    # 2 - install and quick start
    story.extend(
        [
            h1("1. Start here"),
            body(
                "ECU Map Studio is supplied as one Windows executable. It does not require "
                "Python, Excel, or a separate installer on the destination computer."
            ),
            h2("Run the application"),
            step(
                1,
                "Locate the file",
                "Open the <b>dist</b> folder and find <b>ECUMapStudio.exe</b>.",
            ),
            step(
                2,
                "Start it",
                "Double-click the executable. The first launch can take a few seconds while the single-file package is prepared.",
            ),
            step(
                3,
                "Keep the trusted original",
                "The build is not code-signed. If Windows shows an Unknown publisher message, verify that the file came from your trusted project copy and compare its checksum.",
            ),
            Spacer(1, 2 * mm),
            box(
                f"<b>Build identity</b><br/>Version: 1.1.0<br/>Size: {size}<br/>"
                f"SHA-256: <font name='Courier'>{checksum}</font>",
                "info",
            ),
            h2("Six-step quick start"),
            step(1, "Copy", "In RomRaider, use <b>Copy Table</b> for the complete map or curve."),
            step(2, "Paste", "In ECU Map Studio, choose <b>Paste RomRaider / Excel table</b>."),
            step(
                3,
                "Choose the target",
                "Set the new axis limits and table size, or enter custom breakpoints.",
            ),
            step(
                4,
                "Choose the method",
                "Start with Bilinear and Hold edge values unless the map requires something else.",
            ),
            step(
                5,
                "Generate and review",
                "Inspect the Result, VS BILINEAR, extrapolated cells, slices, and safety report.",
            ),
            step(
                6,
                "Copy back",
                "Choose <b>Copy to RR</b>, paste into RomRaider, and validate the calibration.",
            ),
            PageBreak(),
        ]
    )

    # 3 - interface
    story.extend(
        [
            h1("2. Main interface"),
            screenshot(
                "01-main-source.png",
                "The main 3D map workspace with a source map loaded.",
                max_height=110 * mm,
            ),
            data_table(
                [
                    ["Area", "Purpose"],
                    [
                        "Source map",
                        "Paste a complete table, create a blank map, load the demo, or start a clean session.",
                    ],
                    [
                        "Target grid",
                        "Choose Automatic Range for constant spacing or Custom Axes for explicit breakpoints.",
                    ],
                    [
                        "Resampling",
                        "Choose the interpolation method, boundary policy, edge limit, and display precision.",
                    ],
                    [
                        "SOURCE",
                        "Edit original Z values, axes, smoothing, selection math, comparisons, and source copy.",
                    ],
                    [
                        "RESULT",
                        "Review and fine-tune generated values, run the safety report, then copy to RomRaider or TSV.",
                    ],
                    [
                        "VS BILINEAR",
                        "See how the chosen method differs from bilinear at every target cell.",
                    ],
                ],
                [34 * mm, 140 * mm],
            ),
            box(
                "<b>Table zoom:</b> Use the controls below each table, Ctrl plus the mouse "
                "wheel, Ctrl+- / Ctrl++, Ctrl+0, or Fit. Zoom changes presentation only; "
                "it never changes calibration values.",
                "info",
            ),
            PageBreak(),
        ]
    )

    # 4 - clipboard
    story.extend(
        [
            h1("3. Import from RomRaider or Excel"),
            h2("Complete 3D maps"),
            body(
                "Use RomRaider's Copy Table command. A complete 3D clipboard payload contains "
                "the marker, one X-axis row, then one Y value plus a full Z row on each line."
            ),
            code_block(
                [
                    "[Table3D]",
                    "800    1400    2200    3000",
                    "0.20   29.05   31.41   34.72   36.81",
                    "0.35   27.22   29.62   32.90   34.98",
                ]
            ),
            h2("Selections are different"),
            bullet(
                "[Selection3D] contains Z cells but no axes. Load a complete source map first, select the destination top-left cell, then paste."
            ),
            bullet("Cells marked x in a RomRaider selection are left unchanged."),
            bullet(
                "Internal block copy/paste also supports normal TSV for Excel and exact unrounded values inside ECU Map Studio."
            ),
            h2("Extended tables with repeated breakpoints"),
            body(
                "A larger table can repeat its last X or Y coordinate so it behaves like the "
                "smaller original map. ECU Map Studio preserves the full dimensions, every "
                "repeated breakpoint, and every Z cell. Copy source remains an exact round-trip."
            ),
            box(
                "When repeated coordinates still contain matching Z values, calculations use "
                "the equivalent unique-coordinate surface without changing the source. Use "
                "<b>Edit axes</b> to assign the new breakpoints. If values at one repeated "
                "coordinate already differ, surface operations pause until those breakpoints "
                "are made distinct.",
                "warning",
            ),
            h2("Excel layout"),
            body(
                "A full grid is accepted when X values are across the first row, Y values are "
                "down the first column, and the top-left cell is blank or a label. A two-row "
                "axis/value TSV is recognized as a 2D curve."
            ),
            PageBreak(),
        ]
    )

    # 5 - target and methods
    story.extend(
        [
            h1("4. Choose the target grid and method"),
            h2("Automatic Range"),
            body(
                "Enter the X column count, Y row count, and minimum/maximum of each axis. Both "
                "endpoints are included, and all intermediate breakpoints use constant spacing."
            ),
            bullet(
                "Increasing cell count inside the original limits is interpolation, not extrapolation."
            ),
            bullet("Extending a minimum or maximum beyond the source creates extrapolated cells."),
            bullet("Reset limits to source map restores the original coordinate range."),
            h2("Custom Axes"),
            body(
                "Enter or paste every target X and Y breakpoint. Use this for intentionally "
                "uneven spacing, OEM-style axes, or exact coordinates selected from logs."
            ),
            h2("Interpolation methods"),
            data_table(
                [
                    ["Method", "Best use", "Main tradeoff"],
                    [
                        "Bilinear",
                        "Default for normal ignition, fuel, boost, and similar continuous maps.",
                        "Local and predictable; no overshoot inside a source cell.",
                    ],
                    [
                        "PCHIP",
                        "A smoother shape-preserving surface when source behavior supports it.",
                        "Can differ from bilinear; always review VS BILINEAR. Requires at least four unique points on each axis.",
                    ],
                    [
                        "Nearest",
                        "Switches, categories, flags, or maps with discrete levels.",
                        "Creates steps and is normally unsuitable for continuous fuel or ignition values.",
                    ],
                ],
                [28 * mm, 77 * mm, 69 * mm],
            ),
            box(
                "<b>Practical default:</b> Start with Bilinear. Choose PCHIP only when its "
                "smoothness is wanted and the comparison view confirms the differences are "
                "reasonable. Choose Nearest only when intermediate values are invalid.",
                "info",
            ),
            PageBreak(),
        ]
    )

    # 6 - extrapolation
    story.extend(
        [
            h1("5. Control extrapolation"),
            body(
                "Interpolation estimates values between known coordinates. Extrapolation "
                "estimates outside the known X or Y range and deserves stricter review."
            ),
            data_table(
                [
                    ["Boundary policy", "Behavior", "Use it when"],
                    [
                        "Hold edge values",
                        "Clamps each outside coordinate to the nearest source boundary.",
                        "You want the conservative default and do not want a continuing edge slope.",
                    ],
                    [
                        "Limited linear",
                        "Continues the nearest edge slope, limited by a chosen number of edge intervals.",
                        "The edge trend is meaningful and a controlled continuation is justified.",
                    ],
                    [
                        "Do not extrapolate",
                        "Rejects any target grid with cells outside the source range.",
                        "You want a hard guardrail against all extrapolation.",
                    ],
                ],
                [35 * mm, 70 * mm, 69 * mm],
            ),
            h2("How to read the display"),
            bullet("Amber cells or points are outside at least one source-axis boundary."),
            bullet("The result header shows the exact number of extrapolated cells."),
            bullet(
                "Slice plots and the 3D surface repeat the amber marking, so extrapolation is not hidden by the color scale."
            ),
            bullet(
                "PCHIP uses its smooth method inside the known domain; Limited linear uses the predictable bilinear edge slope outside."
            ),
            box(
                "Extrapolation is not automatically wrong, and interpolation is not "
                "automatically safe. The important questions are whether the new operating "
                "region is valid, whether the boundary trend is meaningful, and whether the "
                "result is verified with suitable logs and instrumentation.",
                "warning",
            ),
            h2("A conservative expansion sequence"),
            step(
                1,
                "First resize inside the original limits",
                "Confirm the denser map behaves as expected without extrapolation.",
            ),
            step(
                2,
                "Extend one axis deliberately",
                "Keep the extension small and prefer Hold edge values initially.",
            ),
            step(
                3,
                "Inspect every amber region",
                "Use heat maps, slices, 3D view, and the safety report before copying.",
            ),
            step(
                4,
                "Validate on the vehicle",
                "Confirm the newly represented operating area with logs and appropriate safeguards.",
            ),
            PageBreak(),
        ]
    )

    # 7 - results
    story.extend(
        [
            h1("6. Generate, review, and copy"),
            screenshot(
                "02-generated-result.png",
                "A 20 x 16 PCHIP result. Amber edge cells are outside the original source limits.",
                max_height=108 * mm,
            ),
            h2("Review before export"),
            bullet("Confirm the target X and Y headers are the intended values and order."),
            bullet("Scan the full heat map for unexpected plateaus, ridges, spikes, or reversals."),
            bullet(
                "If using PCHIP or Nearest, open VS BILINEAR and inspect the largest differences."
            ),
            bullet(
                "Open Safety report and note changed cells, extrema, RMS difference, extrapolation count, and sharp edges."
            ),
            bullet(
                "Generated result cells are editable. Fine-tuning is tracked by undo/redo and is included in copy, project save, reports, and visualization."
            ),
            h2("Export choices"),
            data_table(
                [
                    ["Action", "Clipboard result"],
                    ["Copy to RR", "A complete [Table3D] result with both axes and all Z cells."],
                    ["Copy TSV", "An Excel-compatible grid with a top-left header cell."],
                    [
                        "Copy source",
                        "The current source map, including padded dimensions and source edits.",
                    ],
                ],
                [38 * mm, 136 * mm],
            ),
            PageBreak(),
        ]
    )

    # 8 - slice
    story.extend(
        [
            h1("7. Inspect live X and Y slices"),
            screenshot(
                "03-slice-plots.png",
                "Two cross-sections through the selected heat-map cell. Amber markers are extrapolated points.",
                max_height=115 * mm,
            ),
            body(
                "Choose <b>Visualize - Live X / Y slice plot</b> from Source, Result, or VS "
                "BILINEAR. Select another heat-map cell while the dialog is open and both "
                "curves update immediately."
            ),
            h2("What slices reveal well"),
            bullet("A spike or dip that occupies only one row or column."),
            bullet("A slope reversal hidden by a broad heat-map color range."),
            bullet("A flat extrapolated edge created by Hold edge values."),
            bullet("A PCHIP transition that differs materially from the bilinear reference."),
            box(
                "The X slice holds the selected Y row constant. The Y slice holds the selected "
                "X column constant. Always inspect both directions; a surface can look smooth "
                "in one direction and irregular in the other.",
                "info",
            ),
            PageBreak(),
        ]
    )

    # 9 - 3d
    story.extend(
        [
            h1("8. Use the interactive 3D surface"),
            screenshot(
                "04-3d-surface.png",
                "Interactive surface view with amber extrapolated cells and the Z-value color scale.",
                max_height=121 * mm,
            ),
            data_table(
                [
                    ["Control", "What it does"],
                    ["Drag", "Rotates the surface."],
                    ["Mouse wheel", "Zooms the camera."],
                    [
                        "Isometric / Top / X side / Y side",
                        "Moves immediately to a repeatable inspection angle.",
                    ],
                    ["Grid lines", "Shows or hides individual surface-cell boundaries."],
                    [
                        "Matplotlib toolbar",
                        "Home, back/forward, pan, zoom, subplot settings, and image save.",
                    ],
                ],
                [52 * mm, 122 * mm],
            ),
            box(
                "The 3D view is a snapshot for smooth rotation. Reopen it after changing or "
                "regenerating the map. Use the heat map and exact values for numerical review; "
                "perspective can make slopes appear larger or smaller than they are.",
                "warning",
            ),
            PageBreak(),
        ]
    )

    # 10 - editing tools
    story.extend(
        [
            h1("9. Edit, compare, and audit changes"),
            h2("Undo and redo"),
            body(
                "Ctrl+Z and Ctrl+Y cover cell edits, selection pastes, axis edits, smoothing, "
                "selection math, and comparison merges. The source and generated result have "
                "separate 100-step histories."
            ),
            h2("Move blocks"),
            bullet("Select a rectangular block and press Ctrl+C."),
            bullet("Select the destination's top-left cell and press Ctrl+V."),
            bullet(
                "Non-contiguous selections preserve holes and leave those destination cells unchanged."
            ),
            h2("Selection math"),
            body(
                "Select source cells or curve points, then choose Selection math. Add, "
                "subtract, multiply, adjust by percent, set a fixed value, or clamp to a "
                "range. One application is one undoable change."
            ),
            h2("Compare clipboard"),
            body(
                "Copy another complete map, then choose Compare clipboard. If its axes differ, "
                "the candidate is aligned to the source with bilinear interpolation and held "
                "edges. Review candidate values, absolute difference, and percentage difference. "
                "Select difference cells to merge only those values into the source."
            ),
            screenshot(
                "06-safety-report.png",
                "The numerical safety report is a review checklist, not an engine-safety determination.",
                max_height=72 * mm,
            ),
            PageBreak(),
        ]
    )

    # 11 - smoothing
    story.extend(
        [
            h1("10. Use smoothing carefully"),
            screenshot(
                "05-smoothing-preview.png",
                "Whole-table smoothing preview: proposed values on the left and exact differences on the right.",
                max_height=105 * mm,
            ),
            data_table(
                [
                    ["Tool", "Behavior"],
                    [
                        "Detect suspicious cells",
                        "Selects strong isolated interior anomalies. It never changes values automatically.",
                    ],
                    [
                        "Repair selected cells",
                        "Reconstructs only selected cells from unchanged surrounding values using an axis-aware harmonic surface.",
                    ],
                    [
                        "Smooth entire table",
                        "Applies one deterministic axis-aware local-plane pass and always shows a before/apply preview.",
                    ],
                    [
                        "Undo last source change",
                        "Returns to the prior source state through the shared undo history.",
                    ],
                ],
                [46 * mm, 128 * mm],
            ),
            box(
                "A smoother-looking map is not automatically safer or better. Smoothing can "
                "flatten intentional calibration features, move thresholds, and alter engine "
                "behavior. Prefer small reviewed selections. Use whole-table smoothing only "
                "when every difference has been evaluated.",
                "danger",
            ),
            PageBreak(),
        ]
    )

    # 12 - curves
    story.extend(
        [
            h1("11. Work with 2D curves"),
            screenshot(
                "07-2d-curve.png",
                "The dedicated 2D Curve Studio with a 20-point PCHIP result and three extrapolated points.",
                max_height=108 * mm,
            ),
            body(
                "A RomRaider [Table2D] contains one X-axis row and one value row. Open the "
                "2D Curve Tool from the main header, or paste a complete [Table2D] into the "
                "main window and it will route automatically."
            ),
            h2("Curve workflow"),
            step(
                1,
                "Paste the complete curve",
                "Use RomRaider Copy Table, not a value-only selection.",
            ),
            step(
                2,
                "Set the target axis",
                "Choose Automatic Range and point count or enter a Custom Axis.",
            ),
            step(
                3,
                "Choose the method",
                "Linear is the predictable default; PCHIP is smoother; Nearest preserves discrete levels.",
            ),
            step(
                4,
                "Review and copy",
                "Inspect the curve, amber extrapolated points, VS LINEAR, then Copy to RR.",
            ),
            body(
                "Curve selection pastes, anomaly detection, selected-point repair, whole-curve "
                "smoothing, selection math, undo/redo, project files, and clean-session reset "
                "are supported in the same style as 3D maps."
            ),
            PageBreak(),
        ]
    )

    # 13 - projects sessions shortcuts
    story.extend(
        [
            h1("12. Save projects and manage sessions"),
            h2("Project files"),
            body(
                "File - Save project stores a versioned .ecumap file containing the source, "
                "current result, extrapolation mask, target axes, method, boundary policy, edge "
                "limit, and display precision. Open project restores the complete working state."
            ),
            bullet("Ctrl+S saves to the current project file."),
            bullet("Ctrl+O opens a map or curve project of the correct type."),
            bullet("Use Save project as when creating a new branch of calibration work."),
            h2("Start clean"),
            body(
                "Clear table / New session removes the source, result, VS BILINEAR map, target "
                "axes, undo histories, and open map visualizers after confirmation. The system "
                "clipboard and RomRaider are not modified. The 2D Curve Tool has the equivalent action."
            ),
            h2("Keyboard shortcuts"),
            data_table(
                [
                    ["Shortcut", "Action"],
                    ["Ctrl+N", "New session / clear current table or curve"],
                    ["Ctrl+O", "Open project"],
                    ["Ctrl+S", "Save project"],
                    ["Ctrl+Z / Ctrl+Y", "Undo / redo in the active Source or Result context"],
                    ["Ctrl+C / Ctrl+V", "Copy or paste the selected cell block"],
                    ["Ctrl+Shift+C", "Copy the current result for RomRaider"],
                    ["Ctrl+- / Ctrl++ / Ctrl+0", "Table zoom out / in / reset"],
                    ["Ctrl + mouse wheel", "Table zoom"],
                ],
                [44 * mm, 130 * mm],
            ),
            box(
                "Project files preserve numerical work; they do not replace normal ROM backups, "
                "change logs, version naming, or recovery copies of the original calibration.",
                "info",
            ),
            PageBreak(),
        ]
    )

    # 14 - troubleshoot and checklist
    story.extend(
        [
            h1("13. Troubleshooting and final checklist"),
            h2("Paste says the format is not recognized"),
            bullet(
                "Use RomRaider Copy Table for a complete [Table3D] or [Table2D], not Ctrl+C on Z cells alone."
            ),
            bullet("For Excel TSV, keep the X header row, Y header column, and every Z cell."),
            bullet("If a selection has no axes, first load its complete source map or curve."),
            h2("A padded table will not calculate"),
            bullet("Repeated coordinates with matching data are handled automatically."),
            bullet(
                "If different Z values share one coordinate, use Edit axes to give the padded bins distinct breakpoints."
            ),
            h2("PCHIP is unavailable"),
            bullet(
                "PCHIP needs at least four unique source coordinates on both map axes, or four source points for a curve."
            ),
            bullet("Use Bilinear/Linear for smaller data sets."),
            h2("The result cannot be copied"),
            bullet("Generate an up-to-date result after every source, axis, or method change."),
            bullet("Resolve invalid or blank cells and review any error shown in the status bar."),
            h2("Pre-export calibration checklist"),
            data_table(
                [
                    ["Check", "Confirm before pasting into RomRaider"],
                    ["Axes", "Correct dimensions, units, order, minimums, maximums, and spacing"],
                    ["Method", "Appropriate interpolation choice and reviewed comparison view"],
                    ["Boundaries", "Every extrapolated region identified and justified"],
                    ["Values", "No unexpected extrema, spikes, dips, plateaus, or sharp edges"],
                    ["History", "Project saved and original ROM/table backup preserved"],
                    [
                        "Vehicle",
                        "Suitable logging, instrumentation, safeguards, and validation plan ready",
                    ],
                ],
                [40 * mm, 134 * mm],
            ),
            Spacer(1, 4 * mm),
            box(
                "<b>Final reminder:</b> ECU Map Studio can show what the numerical operation "
                "did. It cannot know the engine's knock limit, fuel system capacity, thermal "
                "margin, mechanical condition, sensor accuracy, or safe operating envelope.",
                "danger",
            ),
        ]
    )
    return story


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=23 * mm,
        bottomMargin=18 * mm,
        title="ECU Map Studio User Manual",
        author="ECU Map Studio",
        subject="User guide for ECU map and curve interpolation workflows",
    )
    document.build(
        build_story(),
        onFirstPage=cover_page,
        onLaterPages=page_header_footer,
    )
    print(OUTPUT)


if __name__ == "__main__":
    main()
