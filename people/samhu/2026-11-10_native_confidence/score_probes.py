"""Retain decoder evidence before lossy aggregation/normalization.

Hooks are local to this process; installed packages and model weights are unchanged.
"""
import inspect
import math
from collections import defaultdict, deque
from contextlib import contextmanager

import numpy as np


def stable_logsoftmax(logits, xp):
    """FP32 normalization with log1p so a tiny non-winning mass is not lost at 1.

Promotes the original logits BEFORE subtraction. Does not undo model BF16 rounding.
Only one maximum is removed: tied maxima must remain in the competing mass.
"""
    flat = logits.reshape(-1).astype(xp.float32)
    winner = xp.argmax(flat)
    shifted = flat - flat.max()
    other = xp.where(xp.arange(flat.size) == winner, -float('inf'), shifted)
    log_z = xp.log1p(xp.exp(other).sum())
    return (shifted - log_z).reshape(logits.shape)


@contextmanager
def mineru_probe(module, mx, tokenizer):
    """Replace precisely the installed normalization expression, retaining evidence.

Generation/token selection otherwise uses the original function verbatim. Abort if
the installed source changes instead of silently instrumenting the wrong place.
"""
    original = module.generate_step
    source = inspect.getsource(original)
    needle = 'logprobs = logits - mx.logsumexp(logits)'
    if source.count(needle) != 1:
        raise RuntimeError('Unsupported MLX generate_step source; re-audit normalization')
    records = []

    def capture(logits):
        corrected = stable_logsoftmax(logits, mx)
        # Tiny alternatives remain meaningful in log space; retain selected raw logits.
        flat = logits.reshape(-1).astype(mx.float32)
        ids = mx.argpartition(-flat, 4)[:5].tolist()
        vals = flat[ids].tolist()
        logs = corrected.reshape(-1)[ids].tolist()
        ranked = sorted(zip(ids, vals, logs), key=lambda x: (-x[1], x[0]))
        chosen = int(mx.argmax(flat).item())
        old = logits - mx.logsumexp(logits)
        raw = float(old.reshape(-1)[chosen].item())
        # Reproduce v1's post-hoc FP32 correction on these SAME logits.
        old32 = old.reshape(-1).astype(mx.float32)
        old_max = old32.max()
        v1 = old32[chosen] - (old_max + mx.log(mx.exp(old32-old_max).sum()))
        records.append({
            'token_id': chosen, 'logit_dtype': str(logits.dtype),
            'raw_selected_logit': float(flat[chosen].item()),
            'backend_log_probability': raw,
            'v1_posthoc_probability': math.exp(min(0, float(v1.item()))),
            'top_alternatives': [{'token_id': i, 'text': tokenizer.decode([i]),
                                  'logit': z, 'log_probability': lp,
                                  'probability': math.exp(lp)} for i,z,lp in ranked],
        })
        return corrected

    scope = dict(original.__globals__)
    scope['_capture_native_logits'] = capture
    exec(compile(source.replace(needle, 'logprobs = _capture_native_logits(logits)'),
                 '<audited-mineru-normalization-probe>', 'exec'), scope)
    module.generate_step = scope['generate_step']
    try:
        yield records
    finally:
        module.generate_step = original


def ctc_character_evidence(predictions, characters):
    """Scores on the selected CTC path, not marginal final-character probabilities."""
    rows = []
    for probabilities in np.asarray(predictions):
        if not np.isfinite(probabilities).all() or probabilities.min() < 0 or probabilities.max() > 1:
            raise ValueError('Expected normalized CTC probabilities')
        error = float(np.abs(probabilities.sum(axis=-1)-1).max())
        if error > 1e-3:
            raise ValueError(f'CTC distribution sum range: {probabilities.sum(axis=-1).min()} .. {probabilities.sum(axis=-1).max()}; dtype={probabilities.dtype}')
        ids = probabilities.argmax(axis=-1)
        keep = np.ones(len(ids), dtype=bool)
        keep[1:] = ids[1:] != ids[:-1]
        keep &= ids != 0
        units = []
        for t in np.flatnonzero(keep):
            i = int(ids[t]); p = float(probabilities[t,i])
            top = np.argpartition(-probabilities[t], 2)[:3]
            top = top[np.argsort(-probabilities[t,top])]
            units.append({'text': characters[i], 'token_id': i, 'timestep': int(t),
                          'score': p, 'log_probability': math.log(p) if p else None,
                          'unit_kind': 'character', 'score_kind': 'ctc_selected_path_probability',
                          'top_alternatives': [{'token_id': int(j), 'text': characters[j],
                                                'probability': float(probabilities[t,j])} for j in top]})
        rows.append({'text': ''.join(u['text'] for u in units), 'characters': units,
                     'distribution_sum_max_error': error})
    return rows


@contextmanager
def paddle_probe(decoder_class):
    original = decoder_class.__call__
    captured = defaultdict(deque)

    def call(self, pred, *args, **kwargs):
        result = original(self, pred, *args, **kwargs)
        rows = ctc_character_evidence(pred[0], self.character)
        for row, text, score in zip(rows, result[0], result[1], strict=True):
            if not isinstance(text, str) or row['text'] != text:
                raise ValueError('Unsupported CTC text transformation')
            # Paddle sorts crops for batching then restores page order. Match both
            # text and native line score; identical duplicates have equivalent scores.
            captured[(text, float(score))].append(row)
        return result

    decoder_class.__call__ = call
    try:
        yield captured
    finally:
        decoder_class.__call__ = original


def attach_characters(lines, captured):
    characters = []
    for i, line in enumerate(lines):
        key = (line['text'], line['score'])
        if not captured[key]:
            raise ValueError('Cannot pair Paddle character scores with output line')
        evidence = captured[key].popleft()
        line['characters'] = evidence['characters']
        line['distribution_sum_max_error'] = evidence['distribution_sum_max_error']
        for char in evidence['characters']:
            char['line_index'] = i
            characters.append(char)
    if any(captured.values()):
        raise ValueError('Unpaired Paddle recognition outputs')
    return characters
