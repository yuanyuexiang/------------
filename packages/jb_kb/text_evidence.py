"""本地附件文字证据：逐页文本、扫描页 OCR、按内容缓存及明确覆盖范围。"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


def read_evidence(path: str, max_pages: int = 12, ocr_pages: int = 4) -> dict:
    source = Path(path)
    try:
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
    except OSError:
        return {'pages': [], 'notes': ['原件不存在或不可读取']}
    cache = source.parent / '.text-evidence'
    key = f'v1-{digest}-{max_pages}-{ocr_pages}.json'
    try:
        return json.loads((cache / key).read_text())
    except (OSError, ValueError):
        pass
    pages, notes = [], []
    with tempfile.TemporaryDirectory(prefix='jb-evidence-') as folder:
        try:
            suffix = source.suffix.lower()
            if suffix == '.pdf':
                proc = subprocess.run(['pdftotext', '-f', '1', '-l', str(max_pages), '-layout',
                                       str(source), '-'], capture_output=True, text=True, timeout=25)
                if proc.returncode:
                    raise ValueError('PDF文本读取失败')
                texts = proc.stdout.split('\f')
                if texts and not texts[-1].strip():
                    texts.pop()
                notes.append(f'文本覆盖前{max_pages}页；扫描页OCR最多前{ocr_pages}页，后续页未核验')
            elif suffix in ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.webp'):
                texts = ['']
            else:
                return {'pages': [], 'notes': ['此格式尚未自动读取，请查看原件']}
            for number, value in enumerate(texts[:max_pages], 1):
                mode = 'text'
                if len(value.strip()) < 25 and number <= ocr_pages:
                    image = str(source)
                    if suffix == '.pdf':
                        prefix = str(Path(folder) / f'page-{number}')
                        subprocess.run(['pdftoppm', '-f', str(number), '-l', str(number), '-r', '150',
                                        '-singlefile', '-png', str(source), prefix],
                                       capture_output=True, check=True, timeout=30)
                        image = prefix + '.png'
                    proc = subprocess.run(['tesseract', image, 'stdout', '-l', 'chi_sim+eng'],
                                          capture_output=True, text=True, timeout=45)
                    if proc.returncode:
                        notes.append(f'第{number}页OCR失败，需查看原件')
                    else:
                        value, mode = proc.stdout, 'ocr'
                if value.strip():
                    pages.append({'page': number, 'text': value.strip()[:12000], 'method': mode})
                else:
                    notes.append(f'第{number}页未获得可读文字')
        except (OSError, ValueError, subprocess.SubprocessError):
            notes.append('读取或OCR未完成，请查看原件；不据此判定资料缺失')
    result = {'pages': pages, 'notes': notes}
    try:
        cache.mkdir(exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', dir=cache, delete=False) as output:
            json.dump(result, output, ensure_ascii=False)
        os.replace(output.name, cache / key)
    except OSError:
        pass
    return result
