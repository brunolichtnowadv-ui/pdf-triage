# PDF Triage

**A small script that decides, page by page, what an AI assistant can read as text and what it has to look at as an image, so long PDFs cost far fewer tokens without losing signatures, stamps, handwriting or photos.**

[Português](README.pt-BR.md) · Related: [AI Office Guardrails](https://github.com/brunolichtnowadv-ui/ai-office-guardrails) · [No Fake Quotes](https://github.com/brunolichtnowadv-ui/no-fake-quotes) · [Risk-Floor Model Routing](https://github.com/brunolichtnowadv-ui/risk-floor-model-routing) · [No Orphan Tabs](https://github.com/brunolichtnowadv-ui/no-orphan-tabs)

---

## Why

Reading a long PDF only as images is expensive. Reading it only as text is risky: a signature, a stamp, a handwritten date or a photo simply disappears. This script sorts the pages first, so the assistant reads text as text and looks only at what really needs eyes.

Rule it follows: **when in doubt, the image goes to review, and nothing is dropped without a record in the report.**

## Usage

```bash
python3 -I pdf_triage.py "file.pdf" [--out DIR] [--pages 1-40] [--lang eng]
```

It writes, next to the PDF or in `--out`:

- `text.txt`: the text of every page, including OCR text for scanned pages;
- `images/`: crops (or whole pages) that need to be looked at;
- `report.md`: what was decided for each page, plus an estimate of tokens saved.

`--lang` is the Tesseract language code used for scanned pages (`eng` by default; `por`, `spa`, `eng+por`...).

## What it decides

| Page content | Treatment |
|---|---|
| Native text | Read as text |
| Scanned, good OCR | OCR text, plus crops of regions the OCR did not read as words (stamps, signatures, handwriting, photos) |
| Scanned, poor OCR (photo, handwriting) | Whole page as an image |
| Scanned, many non-text regions | Whole page as an image, at lower resolution |
| Embedded image | Cropped at good resolution |
| Vector chart (15 or more curves) | Crop of the chart area |
| Same image on 3 or more pages (logo, seal, QR code) | Ignored, with a count in the report |
| Very small decorative image | Ignored, with a count in the report |

A damaged PDF is rebuilt with `qpdf` and the triage runs on the repaired copy.

## Example

[`examples/make_sample.py`](examples/make_sample.py) builds an invented four-page `sample.pdf` (run `python3 examples/make_sample.py`; it needs `reportlab`): two pages of native text, one with a vector chart, and one scanned page with a stamp and a handwritten scribble. Pages 1 to 3 carry the same logo. The result, from [`examples/report.md`](examples/report.md):

```
Pages: 4 | native text: 3 | scanned: 1 | crops to view: 4 | images ignored: 3 repeated, 0 small | no text: 0
Estimated tokens: text ~1.786 + images ~2.261 = ~4.047 (everything as images: ~9.200)

| Page | What was done | Crops |
| 1 | text | - |
| 2 | text | - |
| 3 | text; view vector chart (24 curves) | page-0003-chart.png |
| 4 | OCR text (confidence 95); view 3 region(s) without text (stamp, signature, handwriting, photo) | page-0004-non-text-1.png, page-0004-non-text-2.png, page-0004-non-text-3.png |
```

The repeated logo was ignored three times, the scanned page was read through OCR, and the stamp and the scribble were cut out for a person (or a model) to look at.

## Using it with Claude

Run it as the first step whenever a long PDF arrives, then read `text.txt` and open only the files in `images/`. A skill can make this a rule: "read text as text, see images as images; when in doubt, look at the image; a literal quotation from a scanned page is used only after checking it against the image". The full rule is in [AI Office Guardrails](https://github.com/brunolichtnowadv-ui/ai-office-guardrails), section 5.

## Requirements

Python 3 with `pdfplumber`, `Pillow`, `numpy` and `scipy`; the command-line tools `pdftoppm` (poppler-utils) and `tesseract` (with the language you need); `qpdf` for damaged files.

## Limitations

- The thresholds at the top of the file (image area, repeated images, OCR confidence, ink outside words, number of curves) are heuristics tuned on real documents of one practice. Adjust them for yours.
- Token figures are estimates (about 3 characters per text token, about 750 pixels per image token, 2,300 tokens for a full page as an image). In the author's tests on real case files (not included, for confidentiality) the reading cost dropped by about half on an 8-page document and by about three quarters on a 93-page one. Your savings depend on how much of your material is native text.
- It does not understand content. A table inside a scanned page is read through OCR only; if the table matters, look at the page.
- OCR quality depends on the scan and on the language you pass in `--lang`.

## License

[MIT](LICENSE)
