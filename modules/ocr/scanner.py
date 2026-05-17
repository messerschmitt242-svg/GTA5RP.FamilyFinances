from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    import cv2
    import numpy as np
    import pytesseract
except Exception:  # Railway still starts if OCR deps are missing during local tests.
    cv2 = None
    np = None
    pytesseract = None

from modules.skills.constants import STAT_KEYS


@dataclass(frozen=True)
class IconMatch:
    key: str
    x: int
    y: int
    w: int
    h: int
    score: float


class TemplateOcrScanner:
    """Template matching scanner for GTA5RP contract/personnel icons.

    Templates are loaded recursively from:
        assets/ocr/templates/skills/*.png
        assets/ocr/templates/ranks/*.png
        assets/ocr/templates/clubs/*.png

    Missing templates are skipped. Large/upscaled transparent templates are cropped
    to visible pixels and resized internally, so the files do not need to be the
    exact same resolution as the game screenshot.
    """

    def __init__(self, template_dir: str = "assets/ocr/templates", threshold: float = 0.54):
        self.template_dir = Path(template_dir)
        self.threshold = threshold
        self._templates: dict[str, list] | None = None

    def parse_image(self, path: str) -> dict[str, int]:
        """Parse one contract/profile screenshot into {stat_key: level}.

        If an icon appears several times, the highest detected number is used.
        """
        image = self._read_image(path)
        matches = self.find_icon_matches(image)
        result: dict[str, int] = {}
        for m in matches:
            number = self._read_number_near_icon(image, m)
            if number is None:
                continue
            # On personnel screenshots the same icon can appear in many rows.
            # For fallback/global parse keep the strongest/highest meaningful value.
            result[m.key] = max(result.get(m.key, 0), number)
        return result

    def parse_personnel_table(self, path: str) -> dict[str, dict[str, int]]:
        """Parse a personnel list screenshot into {rp_name: {stat_key: level}}.

        This is best-effort: if names cannot be OCRed reliably the caller can
        still use parse_image() as a fallback.
        """
        image = self._read_image(path)
        h, w = image.shape[:2]
        rows = self._detect_personnel_rows(image)
        if not rows:
            return {}

        output: dict[str, dict[str, int]] = {}
        for y1, y2 in rows:
            row_img = image[y1:y2, :]
            name = self._ocr_name(row_img, w)
            if not name:
                continue
            matches = self.find_icon_matches(row_img, restrict_right=True)
            values: dict[str, int] = {}
            for m in matches:
                number = self._read_number_near_icon(row_img, m)
                if number is not None:
                    values[m.key] = max(values.get(m.key, 0), number)
            if values:
                output[name] = values
        return output

    def template_count(self) -> int:
        return sum(len(v) for v in self._load_templates().values())

    def find_icon_matches(self, image, restrict_right: bool = False) -> list[IconMatch]:
        self._require_deps()
        gray = self._prepare_gray(image)
        h_img, w_img = gray.shape[:2]
        x_min = int(w_img * 0.55) if restrict_right else int(w_img * 0.48)
        search = gray[:, x_min:]

        found: list[IconMatch] = []
        for key, variants in self._load_templates().items():
            best: IconMatch | None = None
            for tmpl, tw, th in variants:
                if tmpl.shape[0] >= search.shape[0] or tmpl.shape[1] >= search.shape[1]:
                    continue
                res = cv2.matchTemplate(search, tmpl, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)
                if max_val < self.threshold:
                    continue
                x, y = max_loc
                candidate = IconMatch(key, int(x + x_min), int(y), int(tw), int(th), float(max_val))
                if best is None or candidate.score > best.score:
                    best = candidate
            if best is not None:
                found.append(best)
        return self._nms(found, distance=10)

    def _read_image(self, path: str):
        self._require_deps()
        image = cv2.imread(path, cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError("Не удалось прочитать изображение")
        return image

    def _require_deps(self) -> None:
        if cv2 is None or pytesseract is None or np is None:
            raise RuntimeError("OCR dependencies are not installed: opencv-python-headless, pytesseract, Pillow, numpy")

    def _load_templates(self) -> dict[str, list]:
        if self._templates is not None:
            return self._templates
        self._require_deps()
        templates: dict[str, list] = {}
        if not self.template_dir.exists():
            self._templates = templates
            return templates

        for path in self.template_dir.rglob("*.png"):
            key = path.stem
            if key not in STAT_KEYS:
                continue
            raw = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
            if raw is None:
                continue
            visible = self._crop_visible_template(raw)
            if visible is None:
                continue
            gray = self._prepare_gray(visible)
            variants = []
            # GTA icons on 1920px screenshots usually render in the 16-32px range.
            for target_h in (16, 20, 24, 28, 32):
                scale = target_h / max(1, gray.shape[0])
                target_w = max(8, int(gray.shape[1] * scale))
                if target_w > 80:
                    continue
                resized = cv2.resize(gray, (target_w, target_h), interpolation=cv2.INTER_AREA)
                variants.append((resized, target_w, target_h))
            templates[key] = variants

        self._templates = templates
        return templates

    def _crop_visible_template(self, raw):
        if raw.ndim == 3 and raw.shape[2] == 4:
            alpha = raw[:, :, 3]
            ys, xs = np.where(alpha > 8)
            if len(xs) == 0 or len(ys) == 0:
                return None
            x1, x2 = max(0, xs.min() - 2), min(raw.shape[1], xs.max() + 3)
            y1, y2 = max(0, ys.min() - 2), min(raw.shape[0], ys.max() + 3)
            bgr = cv2.cvtColor(raw[y1:y2, x1:x2], cv2.COLOR_BGRA2BGR)
            return bgr
        # Fallback: crop non-dark area.
        gray = cv2.cvtColor(raw, cv2.COLOR_BGR2GRAY) if raw.ndim == 3 else raw
        ys, xs = np.where(gray > 35)
        if len(xs) == 0 or len(ys) == 0:
            return None
        x1, x2 = max(0, xs.min() - 2), min(raw.shape[1], xs.max() + 3)
        y1, y2 = max(0, ys.min() - 2), min(raw.shape[0], ys.max() + 3)
        return raw[y1:y2, x1:x2]

    def _prepare_gray(self, img):
        if img.ndim == 3 and img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img.copy()
        # Normalize contrast and keep shapes, not exact color.
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        gray = cv2.equalizeHist(gray)
        return gray

    def _nms(self, matches: Iterable[IconMatch], distance: int = 12) -> list[IconMatch]:
        selected: list[IconMatch] = []
        for m in sorted(matches, key=lambda x: x.score, reverse=True):
            if any(m.key == s.key and abs(m.x - s.x) <= distance and abs(m.y - s.y) <= distance for s in selected):
                continue
            selected.append(m)
        return selected

    def _read_number_near_icon(self, image, match: IconMatch) -> int | None:
        h_img, w_img = image.shape[:2]
        # GTA5RP level number is usually at the lower-left/bottom edge of the icon.
        x1 = max(0, match.x - 12)
        y1 = max(0, match.y + int(match.h * 0.45))
        x2 = min(w_img, match.x + match.w + 24)
        y2 = min(h_img, match.y + match.h + 24)
        if x2 <= x1 or y2 <= y1:
            return None
        number = self._ocr_number(image[y1:y2, x1:x2])
        if number is not None and 0 <= number <= 999:
            return number
        return None

    def _ocr_number(self, crop) -> int | None:
        if crop is None or crop.size == 0:
            return None
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
        gray = cv2.resize(gray, None, fx=5, fy=5, interpolation=cv2.INTER_CUBIC)
        # White digits on dark background.
        _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
        config = "--psm 7 -c tessedit_char_whitelist=0123456789"
        text = pytesseract.image_to_string(binary, config=config)
        digits = "".join(ch for ch in text if ch.isdigit())
        return int(digits) if digits else None

    def _detect_personnel_rows(self, image) -> list[tuple[int, int]]:
        h, w = image.shape[:2]
        # Personnel table rows start below the header. We detect separator lines,
        # then keep rows tall enough for player data.
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        roi = gray[int(h * 0.12): int(h * 0.98), :]
        # Horizontal separators are slightly brighter than row background.
        line_strength = roi.mean(axis=1)
        candidates = []
        for idx, val in enumerate(line_strength):
            if 28 <= val <= 48:
                candidates.append(idx + int(h * 0.12))
        # Merge close candidates.
        merged = []
        for y in candidates:
            if not merged or y - merged[-1] > 12:
                merged.append(y)
        rows = []
        for a, b in zip(merged, merged[1:]):
            if 55 <= b - a <= 130:
                rows.append((a + 2, b - 2))
        # Fallback for the common full-HD personnel screen.
        if len(rows) < 2:
            top = int(h * 0.145)
            row_h = int(h * 0.085)
            rows = [(top + i * row_h, min(h, top + (i + 1) * row_h)) for i in range(10) if top + i * row_h < h]
        return rows

    def _ocr_name(self, row_img, full_width: int) -> str | None:
        # Name column is on the left, after avatar.
        x1 = int(full_width * 0.035)
        x2 = int(full_width * 0.20)
        h = row_img.shape[0]
        crop = row_img[max(0, int(h * 0.15)): min(h, int(h * 0.75)), x1:x2]
        if crop.size == 0:
            return None
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        _, binary = cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY)
        config = "--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_ []-"
        text = pytesseract.image_to_string(binary, config=config).strip()
        text = text.replace(" ", "").replace("[", "").replace("]", "")
        allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_"
        name = "".join(ch for ch in text if ch in allowed)
        return name or None
