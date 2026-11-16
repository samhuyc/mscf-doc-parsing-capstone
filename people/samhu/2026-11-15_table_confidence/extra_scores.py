"""Passive native-logit capture and conservative HTML token classification."""
import math
import re
from collections import Counter
from regions import table_summary


class LogitObserver:
    def __init__(self, mx, tokenizer):
        self.mx, self.tokenizer, self.records = mx, tokenizer, []

    def __call__(self, tokens, logits):
        from score_probes import stable_logsoftmax
        mx = self.mx
        flat = logits.reshape(-1).astype(mx.float32)
        probabilities = stable_logsoftmax(logits, mx).reshape(-1)
        chosen = int(mx.argmax(flat).item())
        ids = mx.argpartition(-flat, 4)[:5].tolist()
        ranked = sorted(zip(ids, flat[ids].tolist(), probabilities[ids].tolist()), key=lambda v: (-v[1], v[0]))
        lp = float(probabilities[chosen].item())
        self.records.append(dict(token_id=chosen, text=self.tokenizer.decode([chosen]),
            score=math.exp(lp), log_probability=lp, raw_selected_logit=float(flat[chosen].item()),
            logit_dtype=str(logits.dtype), unit_kind='subword_token',
            score_kind='native_conditional_token_probability_fp32_normalization',
            top_alternatives=[dict(token_id=i, text=self.tokenizer.decode([i]), logit=z,
                                   log_probability=p, probability=math.exp(p)) for i,z,p in ranked]))
        return logits  # Identity: reporting never changes generation logits.


def collect(stream, observer=None):
    parts, emitted, final = [], [], None
    for item in stream:
        parts.append(item.text)
        if item.finish_reason is not None:
            final = item
        else:
            emitted.append(int(item.token))
    if final is None:
        raise ValueError('Missing final generation event')
    generated = final.token_ids
    expected = generated[:-1] if final.finish_reason == 'stop' else generated
    if emitted != expected:
        raise ValueError('Stream/final token alignment mismatch')
    units = observer.records[:len(emitted)] if observer else []
    if observer and [u['token_id'] for u in units] != emitted:
        raise ValueError('Observed logits do not align with emitted greedy tokens')
    return dict(text=''.join(parts), token_ids=emitted, generated_token_ids=generated,
                confidence_units=units, stop_reason=final.finish_reason,
                truncated=final.finish_reason != 'stop', prompt_tokens=final.prompt_tokens,
                peak_mlx_gb=final.peak_memory)


def classify_content(units, tokenizer):
    ids = [u['token_id'] for u in units]
    previous, spans = '', []
    for end in range(1, len(ids)+1):
        current = tokenizer.decode(ids[:end], skip_special_tokens=False, clean_up_tokenization_spaces=False)
        if not current.startswith(previous):
            return dict(status='unavailable_nonmonotonic_decode', confidence=table_summary([]))
        spans.append((len(previous), len(current)))
        previous = current
    formatting = set()
    for match in re.finditer(r'<[^>]*>', previous):
        formatting.update(range(match.start(), match.end()))
    for match in re.finditer(r'(?m)^```[^\n]*$', previous):
        formatting.update(range(match.start(), match.end()))
    for unit, (start, end) in zip(units, spans):
        positions = [p for p in range(start, end) if not previous[p].isspace()]
        count = sum(p in formatting for p in positions)
        kind = ('whitespace' if not positions else 'formatting' if count == len(positions)
                else 'mixed' if count else 'content')
        unit.update(content_class=kind, decoded_span=[start,end])
    content = [u for u in units if u['content_class'] == 'content']
    return dict(status='available', method='HTML tags and code fences; mixed tokens excluded',
                token_counts=dict(Counter(u['content_class'] for u in units)),
                confidence=table_summary(content), formatting_confidence=table_summary(
                    [u for u in units if u['content_class'] == 'formatting']))
