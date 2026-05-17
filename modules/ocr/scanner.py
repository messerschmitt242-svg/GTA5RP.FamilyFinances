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


@dataclass(frozen=True)
class DigitGroup:
    x1: int
    y1: int
    x2: int
    y2: int
    value: int


class TemplateOcrScanner:
    """Template matching scanner for GTA5RP contract/personnel icons.

    Important production rule: if the scanner is not confident enough, it skips
    the value instead of writing a guessed/wrong skill into the database.
    """

    def __init__(self, template_dir: str = "assets/ocr/templates", threshold: float = 0.54):
        self.template_dir = Path(template_dir)
        self.threshold = threshold
        self.contract_icon_threshold = 0.74
        self.contract_icon_margin = 0.06
        self._templates: dict[str, list] | None = None

    def parse_image(self, path: str) -> dict[str, int]:
        """Parse one contract screenshot into {stat_key: level}.

        Contract OCR is slot-based: first find the tiny white number groups in
        the contract requirements area, then classify only the icon that belongs
        to that number slot. This prevents binding a skill to a neighbour digit.
        """
        return self.parse_contract_image(path)

    def parse_contract_image(self, path: str) -> dict[str, int]:
        image = self._read_image(path)
        h, w = image.shape[:2]

        # Requirements are in the upper-right block of the GTA5RP contract UI.
        # Keep the crop narrow so we do not accidentally match player-list icons.
        x0 = int(w * 0.60)
        y0 = int(h * 0.10)
        x1 = int(w * 0.985)
        y1 = int(h * 0.285)
        req_area = image[y0:y1, x0:x1]

        digit_groups = self._detect_digit_groups(req_area)
        result: dict[str, int] = {}
        for group in digit_groups:
            classified = self._classify_contract_slot(req_area, group)
            if classified is None:
                continue
            key, score, margin = classified
            if score < self.contract_icon_threshold or margin < self.contract_icon_margin:
                # Not confident enough: leave blank for manual correction.
                continue
            result[key] = max(result.get(key, 0), group.value)
        return result

    def parse_personnel_table(self, path: str) -> dict[str, dict[str, int]]:
        """Parse a personnel list screenshot into {rp_name: {stat_key: level}}."""
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
                if m.score < 0.72:
                    continue
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
            for target_h in (14, 16, 18, 20, 22, 24, 28, 32, 36):
                scale = target_h / max(1, gray.shape[0])
                target_w = max(8, int(gray.shape[1] * scale))
                if target_w > 90:
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

    def _detect_digit_groups(self, image) -> list[DigitGroup]:
        """Find white number groups in contract requirements area."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)

        boxes: list[tuple[int, int, int, int]] = []
        h_img, w_img = gray.shape[:2]
        for i in range(1, count):
            x, y, w, h, area = stats[i]
            # Small bright glyphs below/inside icons. Ignore large white UI text.
            if 2 <= w <= 18 and 6 <= h <= 22 and 8 <= area <= 160 and y > int(h_img * 0.25):
                boxes.append((int(x), int(y), int(w), int(h)))

        boxes.sort(key=lambda b: b[0])
        grouped: list[list[tuple[int, int, int, int]]] = []
        for box in boxes:
            x, y, w, h = box
            if not grouped:
                grouped.append([box])
                continue
            last = grouped[-1][-1]
            last_right = last[0] + last[2]
            same_baseline = abs(y - grouped[-1][0][1]) <= 6
            if same_baseline and x - last_right <= 7:
                grouped[-1].append(box)
            else:
                grouped.append([box])

        result: list[DigitGroup] = []
        for group in grouped:
            x1 = min(b[0] for b in group)
            y1 = min(b[1] for b in group)
            x2 = max(b[0] + b[2] for b in group)
            y2 = max(b[1] + b[3] for b in group)
            value = self._ocr_number(gray[max(0, y1 - 3):min(gray.shape[0], y2 + 4), max(0, x1 - 3):min(gray.shape[1], x2 + 3)])
            if value is not None and 0 < value <= 99:
                result.append(DigitGroup(x1, y1, x2, y2, value))
        return result

    def _classify_contract_slot(self, req_area, group: DigitGroup) -> tuple[str, float, float] | None:
        """Classify icon belonging to a number group. Returns (key, score, margin)."""
        gray_area = self._prepare_gray(req_area)
        cx = int((group.x1 + group.x2) / 2)
        # Icon is above / slightly behind the number. Crop only this slot.
        sx1 = max(0, cx - 46)
        sx2 = min(gray_area.shape[1], cx + 52)
        sy1 = max(0, group.y1 - 54)
        sy2 = min(gray_area.shape[0], group.y2 + 3)
        roi = gray_area[sy1:sy2, sx1:sx2]
        if roi.size == 0:
            return None

        scores: list[tuple[float, str]] = []
        for key, variants in self._load_templates().items():
            best_for_key = -1.0
            for tmpl, tw, th in variants:
                if tmpl.shape[0] >= roi.shape[0] or tmpl.shape[1] >= roi.shape[1]:
                    continue
                res = cv2.matchTemplate(roi, tmpl, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(res)
                best_for_key = max(best_for_key, float(max_val))
            if best_for_key >= 0:
                scores.append((best_for_key, key))

        if not scores:
            return None
        scores.sort(reverse=True)
        best_score, best_key = scores[0]
        second_score = scores[1][0] if len(scores) > 1 else 0.0
        return best_key, best_score, best_score - second_score

    def _read_number_near_icon(self, image, match: IconMatch) -> int | None:
        h_img, w_img = image.shape[:2]
        crop_w = max(34, int(match.w * 1.25))
        crop_h = max(24, int(match.h * 1.0))
        x1 = max(0, match.x - 12)
        y1 = max(0, match.y + int(match.h * 0.28))
        x2 = min(w_img, x1 + crop_w)
        y2 = min(h_img, y1 + crop_h + 10)
        if x2 <= x1 or y2 <= y1:
            return None
        number = self._ocr_number(image[y1:y2, x1:x2])
        if number is not None and 0 <= number <= 99:
            return number
        return None

    def _ocr_number(self, crop) -> int | None:
        if crop is None or crop.size == 0:
            return None
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
        gray = cv2.resize(gray, None, fx=6, fy=6, interpolation=cv2.INTER_CUBIC)
        _, binary = cv2.threshold(gray, 140, 255, cv2.THRESH_BINARY)
        config = "--psm 7 -c tessedit_char_whitelist=0123456789"
        text = pytesseract.image_to_string(binary, config=config)
        digits = "".join(ch for ch in text if ch.isdigit())
        return int(digits) if digits else None

    def _detect_personnel_rows(self, image) -> list[tuple[int, int]]:
        h, w = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        roi = gray[int(h * 0.12): int(h * 0.98), :]
        line_strength = roi.mean(axis=1)
        candidates = []
        for idx, val in enumerate(line_strength):
            if 28 <= val <= 48:
                candidates.append(idx + int(h * 0.12))
        merged = []
        for y in candidates:
            if not merged or y - merged[-1] > 12:
                merged.append(y)
        rows = []
        for a, b in zip(merged, merged[1:]):
            if 55 <= b - a <= 130:
                rows.append((a + 2, b - 2))
        if len(rows) < 2:
            top = int(h * 0.145)
            row_h = int(h * 0.085)
            rows = [(top + i * row_h, min(h, top + (i + 1) * row_h)) for i in range(10) if top + i * row_h < h]
        return rows

    def _ocr_name(self, row_img, full_width: int) -> str | None:
        x1 = int(full_width * 0.050)
        x2 = int(full_width * 0.17)
        h = row_img.shape[0]
        crop = row_img[max(0, int(h * 0.20)): min(h, int(h * 0.72)), x1:x2]
        if crop.size == 0:
            return None
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
        _, binary = cv2.threshold(gray, 130, 255, cv2.THRESH_BINARY)
        config = "--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_"
        text = pytesseract.image_to_string(binary, config=config).strip()
        allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_"
        name = "".join(ch for ch in text if ch in allowed)
        import re
        m = re.search(r"[A-Z][A-Za-z0-9]*_[A-Za-z0-9_]+", name, re.IGNORECASE)
        if m:
            return m.group(0)
        return name or None
