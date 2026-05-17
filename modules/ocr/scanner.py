from __future__ import annotations

from pathlib import Path

try:
    import cv2
    import pytesseract
except Exception:  # Railway still starts if OCR deps are missing during local tests.
    cv2 = None
    pytesseract = None

from modules.skills.constants import STAT_KEYS


class TemplateOcrScanner:
    """Template matching scanner for GTA5RP icons.

    Put icon templates into assets/ocr/templates/<stat_key>.png.
    The scanner finds an icon, crops the number area to its right, and OCRs only digits.
    """

    def __init__(self, template_dir: str = "assets/ocr/templates", threshold: float = 0.82):
        self.template_dir = Path(template_dir)
        self.threshold = threshold

    def parse_image(self, path: str) -> dict[str, int]:
        if cv2 is None or pytesseract is None:
            raise RuntimeError("OCR dependencies are not installed: opencv-python-headless, pytesseract, Pillow")
        image = cv2.imread(path)
        if image is None:
            raise RuntimeError("Не удалось прочитать изображение")
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        result: dict[str, int] = {}
        for key in STAT_KEYS:
            tmpl_path = self.template_dir / f"{key}.png"
            if not tmpl_path.exists():
                continue
            tmpl = cv2.imread(str(tmpl_path), cv2.IMREAD_GRAYSCALE)
            if tmpl is None:
                continue
            matches = cv2.matchTemplate(gray, tmpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(matches)
            if max_val < self.threshold:
                continue
            x, y = max_loc
            h, w = tmpl.shape[:2]
            crop = image[max(0, y - 6): y + h + 8, x + w: x + w + 80]
            number = self._ocr_number(crop)
            if number is not None:
                result[key] = number
        return result

    def _ocr_number(self, crop) -> int | None:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        text = pytesseract.image_to_string(binary, config="--psm 7 -c tessedit_char_whitelist=0123456789")
        digits = "".join(ch for ch in text if ch.isdigit())
        return int(digits) if digits else None
