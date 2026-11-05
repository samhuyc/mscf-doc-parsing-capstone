"""Final section chunking: lossless source spans, contextual headings and token budgets."""
from collections import Counter, defaultdict
from dataclasses import replace
from functools import lru_cache
import json
import re

import tiktoken

from chunker import (blocks_for_page, digest, make_chunk, plain, slice_spans,
                     title_key, validate_chunks)

VERSION = '2.0.0'
ENCODING = 'cl100k_base'
ENTITY = re.compile(r'^.{2,100}?\b(?:LIMITED|LTD\.?|PLC|INC\.?|CORPORATION)\s*$', re.I)
PERIOD = re.compile(r'\s+(?:FOR THE (?:YEAR|PERIOD) ENDED|AS AT)\s+.*$', re.I)
MAJOR = re.compile(r'^(?:strategic report|directors.? report|company information|'
                   r'(?:condensed )?(?:consolidated )?(?:income statement|balance sheet|cash flow statement)$|'
                   r'(?:condensed )?(?:consolidated )?statement of (?:comprehensive income|financial position|changes in equity)|'
                   r'notes to (?:the )?(?:condensed )?(?:consolidated )?financial statements|'
                   r'independent (?:auditor|review))\b', re.I)


@lru_cache(maxsize=2)
def encoder(name=ENCODING):
    return tiktoken.get_encoding(name)


def count_tokens(text, name=ENCODING):
    return len(encoder(name).encode(text, disallowed_special=()))


def heading_key(text):
    # Numbering can disappear in a continued heading. Only use this relaxed key
    # when the source explicitly says "continued"; ordinary numbered siblings differ.
    return re.sub(r'^\d+(?:\.\d+)*[. )-]*', '', title_key(text))


def promote_structural_titles(blocks):
    """Recover standalone report titles exported as prose, never rewrite source text."""
    known = {title_key(b.title) for b in blocks if b.kind == 'heading'}
    for b in blocks:
        b.original_kind = b.kind
        if b.kind not in ('paragraph', 'list') or len(b.text.strip().splitlines()) != 1:
            continue
        candidate = plain(b.text) if b.kind == 'paragraph' else b.text.strip()
        if len(candidate) > 180:
            continue
        normalized = PERIOD.sub('', candidate).strip()
        normalized = re.sub(r'\s*\(?\bcontinued\b\)?', '', normalized, flags=re.I).strip()
        standalone = MAJOR.fullmatch(normalized)
        repeated_numbered = re.match(r'^\d+[. ]', candidate) and title_key(candidate) in known
        if standalone or repeated_numbered:
            b.kind, b.title, b.level = 'heading', candidate, 2 if standalone else 3


def normalize_headings(blocks):
    promote_structural_titles(blocks)
    entity_pages = defaultdict(set)
    for b in blocks:
        if b.kind == 'heading' and ENTITY.fullmatch(b.title):
            entity_pages[b.title.casefold()].add(b.page)
    entities = sorted((name for name, pages in entity_pages.items() if len(pages) >= 3), key=len, reverse=True)
    decisions, in_notes, note_level = [], False, 3
    for b in blocks:
        if b.kind != 'heading':
            continue
        original = b.title
        title = original
        for entity in entities:
            if title.casefold().startswith(entity):
                title = title[len(entity):].strip(' .:-')
                break
        title = PERIOD.sub('', title).strip()
        title = re.sub(r'\s*\(?\bcontinued\b\)?', '', title, flags=re.I).strip(' .:-')
        letters = ''.join(c for c in title if c.isalpha())
        reason = 'section_candidate'
        if not title and any(original.casefold().startswith(e) for e in entities):
            reason = 'repeated_entity_heading'
        elif not letters or (len(letters) <= 4 and re.search(r'\d', title)) or re.match(r'^(?:at least|up to)\s*[$£€\d]', title, re.I):
            reason = 'numeric_display'
        elif re.match(r'^(?:for the (?:year|period|half.year)|as at|year ended|half.year (?:to|ended))\b', original, re.I):
            reason = 'period_context'
        elif re.match(r'^(?:company registration number|registered (?:number|office))\b', title, re.I):
            reason = 'administrative_context'
        effective = b.level
        if reason == 'section_candidate':
            if re.fullmatch(r'(?:condensed consolidated interim )?financial statements', title, re.I):
                effective = 1
            elif MAJOR.match(title):
                effective = 2
            if MAJOR.match(title) or effective == 1:
                in_notes = bool(re.match(r'^notes to ', title, re.I))
                note_level = 3
            if in_notes and not re.match(r'^notes to ', title, re.I):
                number = re.match(r'^(\d+(?:\.\d+)*)(?:[.,)]\s+|\s+)', title)
                if number:
                    effective = 3 + number[1].count('.')
                    note_level = effective
                else:
                    effective = max(effective, note_level + 1)
        # Source content and original heading text remain unchanged.
        b.reason = reason
        b.section_title, b.effective_level = title, effective
        decisions.append(dict(**b.location(), original_title=original, title=title,
                              original_level=b.level, effective_level=effective, decision=reason,
                              original_kind=b.original_kind,
                              recovered_from_plain_text=b.original_kind != 'heading',
                              normalized=original != title or b.level != effective or b.original_kind != 'heading'))
    return decisions


def decorative(block):
    if block.kind == 'heading':
        return True
    text = plain(block.text)
    return not text or bool(ENTITY.fullmatch(text)) or text.casefold() == 'unaudited' or bool(
        re.fullmatch(r'(?:Page\s+)?-?\d+-?(?:\s+of\s+\d+)?', text, re.I)) or bool(
        re.match(r'^(?:for the (?:year|period|half.year)|as at|at(?= \d)|registered number|company number)\b', text, re.I))


def section_groups(blocks):
    groups, current, stack, pending = [], [], [], []
    path, evidence, last_page = [], [], None

    def flush():
        nonlocal current
        if current:
            groups.append((path.copy(), evidence.copy(), current))
            current = []

    for b in blocks:
        new_page = b.page != last_page
        last_page = b.page
        if new_page and pending:
            current.extend(pending)
            pending = []
        if b.kind == 'heading' and b.reason != 'section_candidate':
            if new_page or pending:
                pending.append(b)
            else:
                current.append(b)
            continue
        if b.kind == 'heading':
            title = b.section_title
            match = next((i for i, h in enumerate(stack) if title_key(h.section_title) == title_key(title)), None)
            if match is None and re.search(r'\bcontinued\b', b.title, re.I):
                match = next((i for i, h in enumerate(stack) if heading_key(h.section_title) == heading_key(title)), None)
            carry = bool(current) and current[-1].page == b.page and all(decorative(x) for x in current)
            if match is not None:
                if current and current[-1].page < b.page:
                    flush()
                elif match < len(stack) - 1 and not carry:
                    flush()
                stack = stack[:match + 1]
            else:
                if not carry:
                    flush()
                while stack and stack[-1].effective_level >= b.effective_level:
                    stack.pop()
                stack.append(b)
            path = [h.section_title for h in stack]
            evidence = [dict(**h.location(), title=h.section_title, original_title=h.title) for h in stack]
        current.extend(pending)
        pending = []
        current.append(b)
    current.extend(pending)
    flush()
    return groups


def split_prose(block, limit, encoding):
    """Split large prose/list blocks at source boundaries; tables and code stay atomic."""
    if block.kind in ('table', 'code', 'heading') or count_tokens(block.text, encoding) <= limit:
        return [block]
    text = block.text
    # Prefer sentence/list-item boundaries. Long sentences fall back to whitespace;
    # no token decoding is used, so Unicode characters and exact offsets survive.
    cuts = {0, len(text)}
    cuts.update(m.end() for m in re.finditer(r'(?<=[.!?])\s+(?=[A-Z])|\n(?=\s*[-*+]\s)', text))
    if len(cuts) == 2 or any(count_tokens(text[a:z], encoding) > limit for a, z in zip(sorted(cuts), sorted(cuts)[1:])):
        cuts.update(m.end() for m in re.finditer(r'\s+', text))
    cuts = sorted(cuts)
    parts, start, end = [], 0, 0
    for cut in cuts[1:]:
        if end > start and count_tokens(text[start:cut], encoding) > limit:
            parts.append(replace(block, start=block.start + start, end=block.start + end, text=text[start:end]))
            start = end
        end = cut
    if end > start:
        parts.append(replace(block, start=block.start + start, end=block.start + end, text=text[start:end]))
    return parts


def header_text(doc, path):
    metadata = {k: v['value'] for k, v in doc.get('document_metadata', {}).items() if v['status'] == 'resolved'}
    return '\n'.join(x for x in [f'Document: {doc["document_id"]}',
                                 'Metadata (extracted): ' + json.dumps(metadata, ensure_ascii=False) if metadata else '',
                                 'Section: ' + ' > '.join(path) if path else ''] if x) + '\n\n'


def finish_chunk(doc, strategy, batch, path, evidence, context, max_tokens, encoding, page=None):
    c = make_chunk(doc, strategy, batch, path, evidence, context, page=page)
    header = header_text(doc, path)
    primary = header + c['content']
    accepted = []
    for s in context:
        candidate = accepted + [s]
        payload = primary + '\n\nAdjacent source context:\n' + slice_spans(doc['pages'], candidate)
        if count_tokens(payload, encoding) <= max_tokens:
            accepted = candidate
    c['context_spans'] = accepted
    c['context_text'] = primary + ('\n\nAdjacent source context:\n' + slice_spans(doc['pages'], accepted) if accepted else '')
    c['retrieval_text'] = header + plain(c['content']) + ('\n' + plain(slice_spans(doc['pages'], accepted)) if accepted else '')
    c['flags'] = [f for f in c['flags'] if f not in ('soft_budget_exceeded', 'oversized_atomic_block')]
    c['chunker_version'], c['tokenizer'], c['max_tokens'] = VERSION, encoding, max_tokens
    c.pop('soft_max_chars', None)
    c['content_tokens'] = count_tokens(c['content'], encoding)
    c['retrieval_tokens'] = count_tokens(c['retrieval_text'], encoding)
    c['context_tokens'] = count_tokens(c['context_text'], encoding)
    c['element_types'] = sorted({b.kind for b in batch})
    visible = plain(c['content'])
    c['indexable'] = bool(len(visible) >= 20 and any(ch.isalpha() for ch in visible))
    if not c['indexable']:
        c['flags'].append('low_information_preserved')
    if c['context_tokens'] > max_tokens:
        c['flags'].append('over_token_budget')
        c['flags'].append('atomic_table_exception' if any(b.kind == 'table' for b in batch) else
                          'page_baseline_exception' if strategy == 'page' else 'atomic_text_exception')
    if all(decorative(b) for b in batch):
        c['flags'].append('scaffolding_only')
    c['chunk_id'] = f'{doc["document_id"]}:{strategy}:{digest([VERSION, doc["pages_sha256"], doc.get("metadata_sha256"), encoding, max_tokens, c["source_spans"], path, accepted])[:20]}'
    return c


def chunk_document(doc, max_tokens=1024, encoding=ENCODING):
    if max_tokens < 256:
        raise ValueError('max_tokens must be at least 256')
    per_page = [blocks_for_page(p['page'], p['markdown']) for p in doc['pages']]
    blocks = [b for items in per_page for b in items]
    decisions = normalize_headings(blocks)
    baseline = [finish_chunk(doc, 'page', items, [], [], [], max_tokens, encoding, page=i + 1)
                for i, items in enumerate(per_page)]
    results = []
    for path, evidence, originals in section_groups(blocks):
        overhead = count_tokens(header_text(doc, path), encoding)
        body_limit = max_tokens - overhead - 32
        if body_limit < 64:
            raise ValueError('Heading/metadata context leaves insufficient room for source content')
        refined = [p for b in originals for p in split_prose(b, body_limit, encoding)]
        batches, batch = [], []
        for b in refined:
            combined = ''.join(x.text for x in batch) + b.text
            scaffold = bool(batch) and all(decorative(x) for x in batch)
            footer = b.kind != 'heading' and decorative(b) and count_tokens(b.text, encoding) <= 16
            if batch and count_tokens(combined, encoding) > body_limit and not scaffold and not footer:
                batches.append(batch)
                batch = []
            batch.append(b)
        if batch:
            batches.append(batch)
        if len(batches) > 1 and len(plain(''.join(b.text for b in batches[-1]))) < 150:
            combined = batches[-2] + batches[-1]
            if count_tokens(header_text(doc, path) + ''.join(b.text for b in combined), encoding) <= max_tokens:
                batches[-2:] = [combined]
        # Map split fragments back to their original global element for context.
        for batch in batches:
            context = []
            if any(b.kind == 'table' for b in batch):
                first = next(i for i, b in enumerate(blocks) if b.page == batch[0].page and b.start <= batch[0].start < b.end)
                last = next(i for i, b in enumerate(blocks) if b.page == batch[-1].page and b.start < batch[-1].end <= b.end)
                for idx in (first - 1, last + 1):
                    if 0 <= idx < len(blocks):
                        b = blocks[idx]
                        if b.page in (batch[0].page, batch[-1].page) and b.kind not in ('table', 'code') and count_tokens(b.text, encoding) <= 200:
                            context.append(b.location())
                after = last + 1
                if after < len(blocks) and blocks[after].kind == 'heading' and re.match(r'^(?:notes?|source|units?|basis)\b', blocks[after].title, re.I):
                    for b in blocks[after + 1:after + 4]:
                        if b.page != batch[-1].page or b.kind in ('table', 'code', 'heading'):
                            break
                        if count_tokens(b.text, encoding) <= 200:
                            context.append(b.location())
            results.append(finish_chunk(doc, 'section', batch, path, evidence, context, max_tokens, encoding))
    validate_chunks(doc, baseline)
    validate_chunks(doc, results)
    return baseline, results, decisions


def token_summary(chunks, limit=1024):
    return dict(indexable=sum(c['indexable'] for c in chunks),
                tiny_under_100_chars=sum(c['char_count'] < 100 for c in chunks),
                scaffolding_only=sum('scaffolding_only' in c['flags'] for c in chunks),
                over_token_budget=sum(c['context_tokens'] > limit for c in chunks),
                max_context_tokens=max((c['context_tokens'] for c in chunks), default=0),
                flags=dict(Counter(f for c in chunks for f in c['flags'])))
