"""Geometry and score pooling. No learned quality model or score calibration."""
import math
from pathlib import Path
import sys

NATIVE = Path(__file__).resolve().parent.parent / '2026-11-10_native_confidence'
sys.path.insert(0, str(NATIVE))
from core import summarize


def box_of(unit):
    if 'bbox' in unit:
        return list(unit['bbox'])
    points = unit['polygon']
    return [min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points), max(p[1] for p in points)]


def intersection_fraction(box, region):
    x0, y0, x1, y1 = box
    area = max(0, x1 - x0) * max(0, y1 - y0)
    if not area:
        return 0.0
    return (max(0, min(x1, region[2]) - max(x0, region[0])) *
            max(0, min(y1, region[3]) - max(y0, region[1]))) / area


def padded_box(box, width, height, padding=0.02):
    if len(box) != 4 or not all(math.isfinite(v) for v in box):
        raise ValueError('Invalid region box')
    if box[2] <= box[0] or box[3] <= box[1] or padding < 0:
        raise ValueError('Empty region or negative padding')
    dx, dy = (box[2] - box[0]) * padding, (box[3] - box[1]) * padding
    result = [max(0, math.floor(box[0] - dx)), max(0, math.floor(box[1] - dy)),
              min(width, math.ceil(box[2] + dx)), min(height, math.ceil(box[3] + dy))]
    if result[2] <= result[0] or result[3] <= result[1]:
        raise ValueError('Region outside page')
    return result


def table_summary(units):
    result = summarize(units)
    result.pop('probability_document_correct')
    result['probability_table_correct'] = None
    return result


def deduplicate_tables(boxes, containment=0.95):
    """Keep the larger context when table detections are almost fully nested.

    This removes duplicate numeric-only sub-boxes, not adjacent tables. Preserve
    discarded detections for audit; a retained box may still contain subtables.
    """
    area = lambda b: (b['coordinate'][2]-b['coordinate'][0]) * (b['coordinate'][3]-b['coordinate'][1])
    kept, removed = [], []
    for original_index, box in sorted(enumerate(boxes), key=lambda item: (-area(item[1]), -item[1]['score'], item[0])):
        parent = next((i for i, other in kept if intersection_fraction(box['coordinate'], other['coordinate']) >= containment), None)
        if parent is None:
            kept.append((original_index, box))
        else:
            removed.append(dict(original_index=original_index, contained_in_index=parent, detection=box))
    return sorted([b for _, b in kept], key=lambda b: (b['coordinate'][1], b['coordinate'][0])), removed


def assign_units(page, regions, target_size):
    """Assign each full-page line/word once by maximum overlap, requiring >=50%.

    Paddle characters inherit their detected line's box. These are not exact
    character coordinates. Ambiguous overlaps and boundary cuts remain visible.
    """
    result = [{'units': [], 'source_unit_indices': [], 'boundary_units': [],
               'ambiguous_units': []} for _ in regions]
    if page.get('status') != 'success':
        return result
    sx, sy = target_size[0] / page['width'], target_size[1] / page['height']
    for index, unit in enumerate(page['units']):
        b = box_of(unit)
        b = [b[0]*sx, b[1]*sy, b[2]*sx, b[3]*sy]
        overlaps = [intersection_fraction(b, region['bbox_px']) for region in regions]
        if not overlaps or max(overlaps) < 0.5:
            continue
        chosen = max(range(len(overlaps)), key=overlaps.__getitem__)
        result[chosen]['units'].append(unit)
        result[chosen]['source_unit_indices'].append(index)
        if overlaps[chosen] < 0.98:
            result[chosen]['boundary_units'].append(index)
        if sum(v >= 0.5 for v in overlaps) > 1:
            result[chosen]['ambiguous_units'].append(index)
    return result


def pool_assignment(assignment, engine):
    lines = assignment['units']
    if engine == 'paddle':
        if any('characters' not in line for line in lines):
            raise ValueError('Paddle v2 character evidence required; v1 scores cannot substitute')
        units = [u for line in lines for u in line['characters']]
    else:
        units = lines
    return dict(text='\n'.join(line['text'] for line in lines),
                confidence=table_summary(units), confidence_units=units)
