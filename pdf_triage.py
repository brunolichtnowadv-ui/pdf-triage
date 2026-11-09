#!/usr/bin/env python3
"""PDF triage: separates what can simply be read as text from what has to be seen as an image.

Usage: python3 -I pdf_triage.py "file.pdf" [--out DIR] [--pages 1-40] [--lang eng]
Writes to DIR: text.txt (text per page, including OCR), images/ (crops to look at) and report.md.
Safety rule: when in doubt, the image goes to review; nothing is dropped without a record in the report.
"""
import argparse, collections, hashlib, os, subprocess, sys, tempfile
import numpy as np
import pdfplumber
from PIL import Image

MAX_SIDE = 1568          # longest useful side for visual reading
MIN_IMG_AREA = 0.03      # embedded image under 3% of the page = decorative element
MIN_SIDE_PX = 80         # and under 80 px on the short side
REPEATED_MIN = 3         # same image on 3+ pages = logo, seal, letterhead
SCAN_COVERAGE = 0.6  # image covering 60%+ of the page = scanned page
TEXT_OVER_IMG = 400    # under 400 characters over the image = no text layer
CHART_CURVES = 15      # 15+ vector curves = chart drawn inside the PDF
OCR_CONF_MIN = 75        # minimum average OCR confidence
OCR_PALAVRAS_MIN = 25    # fewer words than this on a scanned page = photo, handwriting or similar
RESIDUAL_INK = 0.0002  # fraction of the page with ink outside the words = stamp, signature, handwriting, photo


def thousands(n):
    return f'{n:,}'.replace(',', '.')


def page_range(s, n):
    if not s:
        return list(range(1, n + 1))
    out = []
    for parte in s.split(','):
        a, _, b = parte.partition('-')
        out += list(range(int(a), int(b or a) + 1))
    return [p for p in out if 1 <= p <= n]


def signature(img):
    try:
        raw = img['stream'].get_rawdata()[:4096]
    except Exception:
        raw = b''
    return hashlib.md5(repr(img.get('srcsize')).encode() + raw).hexdigest()


def render_page(pdf, pag, dpi, folder):
    base = os.path.join(folder, f'r{pag}_{dpi}')
    subprocess.run(['pdftoppm', '-r', str(dpi), '-f', str(pag), '-l', str(pag), '-png', '-singlefile', pdf, base],
                   check=True, capture_output=True)
    return Image.open(base + '.png')


def trim(im, threshold=235, margin=12):
    """Trims the white margins so the image is larger and more legible for fewer tokens."""
    g = np.asarray(im.convert('L'))
    ys, xs = np.where(g < threshold)
    if len(xs) == 0:
        return im
    return im.crop((max(0, xs.min() - margin), max(0, ys.min() - margin),
                    min(im.width, xs.max() + margin), min(im.height, ys.max() + margin)))


def crop_region(im_pag, bbox, width, height, dest_path, margin=6):
    sx, sy = im_pag.width / width, im_pag.height / height
    x0, y0, x1, y1 = bbox
    box = (max(0, int(x0 * sx) - margin), max(0, int(y0 * sy) - margin),
             min(im_pag.width, int(x1 * sx) + margin), min(im_pag.height, int(y1 * sy) + margin))
    crop = trim(im_pag.crop(box))
    crop.thumbnail((MAX_SIDE, MAX_SIDE))
    crop.save(dest_path)
    return crop.width * crop.height // 750  # estimated image tokens


def ocr(im, folder, pag, lang):
    base = os.path.join(folder, f'ocr{pag}')
    im.convert('L').save(base + '.png')
    r = subprocess.run(['tesseract', base + '.png', 'stdout', '-l', lang, '--psm', '3', 'tsv'],
                       capture_output=True, text=True)
    words, confs, boxes, rows = [], [], [], collections.OrderedDict()
    for ln in r.stdout.splitlines()[1:]:
        c = ln.split('\t')
        if len(c) < 12 or not c[11].strip():
            continue
        conf = float(c[10])
        if conf < 0:
            continue
        words.append(c[11]); confs.append(conf)
        if conf >= 60:  # only well-recognised words leave the visual review; a scribble read as a "word" stays
            x, y, w, h = map(int, c[6:10]); boxes.append((x, y, x + w, y + h))
        rows.setdefault((c[2], c[3], c[4]), []).append(c[11])
    text = '\n'.join(' '.join(v) for v in rows.values())
    return text, len(words), (sum(confs) / len(confs) if confs else 0), boxes


def ink_outside_words(im, boxes):
    """Regions with ink that OCR did not recognise as words (stamp, signature, handwriting, photo)."""
    from scipy import ndimage
    rgb = np.asarray(im.convert('RGB')).astype(np.int16)
    g = np.asarray(im.convert('L'))
    h, w = g.shape
    hw = h * w
    # dark ink (black pen, strong pencil, photo) and coloured ink (blue pen, stamp, tick)
    ink = g < 170
    mx, mn = rgb.max(2), rgb.min(2)
    colour = ((mx - mn) > 0.25 * np.maximum(mx, 1)) & (mx < 235)
    colour = ndimage.binary_opening(colour, structure=np.ones((3, 3)))  # compression noise
    for m in (ink, colour):
        m[:int(h * .02)] = m[-int(h * .02):] = False  # scanner borders
        m[:, :int(w * .02)] = m[:, -int(w * .02):] = False
    for x0, y0, x1, y1 in boxes:
        ink[max(0, y0 - 4):y1 + 4, max(0, x0 - 4):x1 + 4] = False
    # straight lines of tables and forms do not count as visual content
    rows = (ndimage.binary_opening(ink, structure=np.ones((1, max(25, w // 25)))) |
              ndimage.binary_opening(ink, structure=np.ones((max(25, h // 25), 1))))
    ink &= ~ndimage.binary_dilation(rows, iterations=2)
    ink = ndimage.binary_opening(ink, structure=np.ones((2, 2)))  # scanner dust
    ink |= colour
    fraction = ink.mean()
    if fraction < RESIDUAL_INK:
        return fraction, []
    labelled, n = ndimage.label(ndimage.binary_dilation(ink, iterations=max(3, w // 60)))
    regions = []
    for sl in ndimage.find_objects(labelled):
        ys, xs = sl
        area = (ys.stop - ys.start) * (xs.stop - xs.start)
        if area >= 0.001 * hw and ink[sl].sum() >= 0.0001 * hw:
            regions.append((xs.start, ys.start, xs.stop, ys.stop))
    union = sum((x1 - x0) * (y1 - y0) for x0, y0, x1, y1 in regions)
    if len(regions) > 4 or union > 0.4 * hw:  # many areas: better to see the whole page at lower resolution
        return fraction, [None]
    return fraction, regions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pdf'); ap.add_argument('--out'); ap.add_argument('--pages')
    ap.add_argument('--lang', default='eng', help='Tesseract language code(s), e.g. eng, por, eng+por')
    a = ap.parse_args()
    outdir = a.out or os.path.splitext(a.pdf)[0] + ' - triage'
    os.makedirs(os.path.join(outdir, 'images'), exist_ok=True)
    tmp = tempfile.mkdtemp()
    try:
        pdfplumber.open(a.pdf).close()
    except Exception:  # damaged PDF: rebuild with qpdf and carry on with the repaired copy
        reparado = os.path.join(tmp, 'reparado.pdf')
        subprocess.run(['qpdf', a.pdf, reparado], capture_output=True)
        print('Warning: damaged PDF; triage done on a copy repaired by qpdf.')
        a.pdf = reparado
    report_rows, texts, total_img_tokens, total_text = [], [], 0, 0
    cont = collections.Counter()
    with pdfplumber.open(a.pdf) as doc:
        page_list = page_range(a.pages, len(doc.pages))
        seen = collections.Counter()
        for p in page_list:  # first pass: images that repeat
            for img in doc.pages[p - 1].images:
                seen[signature(img)] += 1
        for p in page_list:
            pg = doc.pages[p - 1]
            width, height = float(pg.width), float(pg.height)
            text = (pg.extract_text() or '').strip()
            actions, files_out = [], []
            imgs = []
            for img in pg.images:
                x0, y0, x1, y1 = max(0, img['x0']), max(0, img['top']), min(width, img['x1']), min(height, img['bottom'])
                if x1 <= x0 or y1 <= y0:
                    continue
                area = (x1 - x0) * (y1 - y0) / (width * height)
                sw, sh = img.get('srcsize') or (0, 0)
                imgs.append(dict(bbox=(x0, y0, x1, y1), area=area, short_side=min(sw, sh), sig=signature(img)))
            largest = max(imgs, key=lambda i: i['area'], default=None)
            scanned_page = False
            if largest and largest['area'] >= SCAN_COVERAGE:
                over_img = (pg.crop(largest['bbox']).extract_text() or '').strip()
                scanned_page = len(over_img) < TEXT_OVER_IMG
            im_pag = None
            if scanned_page:
                cont['scanned'] += 1
                im_pag = render_page(a.pdf, p, 300, tmp)
                t_ocr, n_pal, conf, boxes = ocr(im_pag, tmp, p, a.lang)
                texts.append(f'=== page {p} (scanned; OCR {n_pal} words, confidence {conf:.0f}) ===\n{t_ocr}\n{text}')
                total_text += len(t_ocr) + len(text)
                if n_pal < OCR_PALAVRAS_MIN or conf < OCR_CONF_MIN:
                    dest = os.path.join(outdir, 'images', f'page-{p:04d}-full-page.png')
                    total_img_tokens += crop_region(im_pag, (0, 0, width, height), width, height, dest, 0)
                    actions.append(f'view the whole page (weak OCR: {n_pal} words, confidence {conf:.0f})')
                    files_out.append(os.path.basename(dest)); cont['view'] += 1
                else:
                    actions.append(f'OCR text (confidence {conf:.0f})')
                    fraction, regions = ink_outside_words(im_pag, boxes)
                    if regions == [None]:
                        dest = os.path.join(outdir, 'images', f'page-{p:04d}-reduced-page.png')
                        red = trim(im_pag); red.thumbnail((1200, 1200)); red.save(dest)
                        total_img_tokens += red.width * red.height // 750
                        actions.append('view the whole page at lower resolution (several non-text elements)')
                        files_out.append(os.path.basename(dest)); cont['view'] += 1
                        regions = []
                    for k, (x0, y0, x1, y1) in enumerate(regions, 1):
                        bb = (x0 * width / im_pag.width, y0 * height / im_pag.height, x1 * width / im_pag.width, y1 * height / im_pag.height)
                        dest = os.path.join(outdir, 'images', f'page-{p:04d}-non-text-{k}.png')
                        total_img_tokens += crop_region(im_pag, bb, width, height, dest)
                        files_out.append(os.path.basename(dest)); cont['view'] += 1
                    if regions:
                        actions.append(f'view {len(regions)} region(s) without text (stamp, signature, handwriting, photo)')
            else:
                texts.append(f'=== page {p} ===\n{text}')
                total_text += len(text)
                actions.append('text' if text else 'no text')
                cont['text' if text else 'no text'] += 1
                for k, i in enumerate(imgs, 1):
                    if seen[i['sig']] >= REPEATED_MIN:
                        cont['repeated'] += 1; continue
                    if i['area'] < MIN_IMG_AREA or (i['short_side'] and i['short_side'] < MIN_SIDE_PX):
                        cont['small'] += 1; continue
                    im_pag = im_pag or render_page(a.pdf, p, 200, tmp)
                    dest = os.path.join(outdir, 'images', f'page-{p:04d}-image-{k}.png')
                    total_img_tokens += crop_region(im_pag, i['bbox'], width, height, dest)
                    actions.append(f'view image {k} ({i["area"]:.0%} of the page)')
                    files_out.append(os.path.basename(dest)); cont['view'] += 1
                curves = pg.curves
                if len(curves) >= CHART_CURVES:
                    bb = (min(c['x0'] for c in curves), min(c['top'] for c in curves),
                          max(c['x1'] for c in curves), max(c['bottom'] for c in curves))
                    im_pag = im_pag or render_page(a.pdf, p, 200, tmp)
                    dest = os.path.join(outdir, 'images', f'page-{p:04d}-chart.png')
                    total_img_tokens += crop_region(im_pag, bb, width, height, dest)
                    actions.append(f'view vector chart ({len(curves)} curves)')
                    files_out.append(os.path.basename(dest)); cont['view'] += 1
            report_rows.append(f'| {p} | {"; ".join(actions)} | {", ".join(files_out) or "-"} |')
    with open(os.path.join(outdir, 'text.txt'), 'w', encoding='utf-8') as f:
        f.write('\n\n'.join(texts))
    tok_text = total_text // 3
    tok_all_img = len(page_list) * 2300
    summary = (f'Pages: {len(page_list)} | native text: {cont["text"]} | scanned: {cont["scanned"]} | '
              f'crops to view: {cont["view"]} | images ignored: {cont["repeated"]} repeated, {cont["small"]} small | '
              f'no text: {cont["no text"]}\n'
              f'Estimated tokens: text ~{thousands(tok_text)} + images ~{thousands(total_img_tokens)} = ~{thousands(tok_text + total_img_tokens)} '
              f'(everything as images: ~{thousands(tok_all_img)})')
    with open(os.path.join(outdir, 'report.md'), 'w', encoding='utf-8') as f:
        f.write(f'# Triage - {os.path.basename(a.pdf)}\n\n{summary}\n\n'
                '| Page | What was done | Crops |\n|---|---|---|\n' + '\n'.join(report_rows) + '\n')
    print(summary)
    print('Output:', outdir)


if __name__ == '__main__':
    main()
