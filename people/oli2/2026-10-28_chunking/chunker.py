"""Lossless, source-addressed chunking of saved page Markdown; no model calls."""
from collections import defaultdict
from dataclasses import dataclass
import hashlib
from html import escape
from html.parser import HTMLParser
import json
import re

from markdown_it import MarkdownIt

VERSION = '1.0.0'
MD = MarkdownIt('commonmark', {'html': True}).enable('table')


def digest(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf8')
    return hashlib.sha256(value).hexdigest()


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        if not self.hidden and tag in ('p', 'br', 'tr', 'td', 'th', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self.parts.append(' ')

    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.hidden:
            self.hidden -= 1
        if not self.hidden:
            self.parts.append(' ')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain(text):
    parser = VisibleText()
    parser.feed(MD.render(text))
    return re.sub(r'\s+', ' ', ''.join(parser.parts)).strip()


def title_key(text):
    return re.sub(r'\s+', ' ', re.sub(r'\(?\bcontinued\b\)?', '', text, flags=re.I)).strip(' .:-').casefold()


def span(page, start, end):
    return dict(page=page, start=start, end=end, json_pointer=f'/pages/{page - 1}/markdown')


@dataclass
class Block:
    page: int
    start: int
    end: int
    text: str
    kind: str
    level: int = 0
    title: str = ''
    reason: str = ''

    def location(self):
        return span(self.page, self.start, self.end)


class TableRanges(HTMLParser):
    """Find complete outer tables even when Markdown splits HTML at blank lines."""
    def __init__(self, text, excluded):
        super().__init__(convert_charrefs=False)
        self.lines = [0]
        for match in re.finditer('\n', text):
            self.lines.append(match.end())
        self.excluded, self.depth, self.start, self.ranges = excluded, 0, 0, []

    def position_index(self):
        line, col = self.getpos()
        return self.lines[line - 1] + col

    def ignored(self, pos):
        return any(a <= pos < b for a, b in self.excluded)

    def handle_starttag(self, tag, attrs):
        pos = self.position_index()
        if tag == 'table' and not self.ignored(pos):
            if self.depth == 0:
                self.start = pos
            self.depth += 1

    def handle_endtag(self, tag):
        pos = self.position_index()
        if tag == 'table' and not self.ignored(pos):
            if not self.depth:
                raise ValueError('Unmatched closing table tag')
            self.depth -= 1
            if not self.depth:
                self.ranges.append((self.start, pos + len('</table>')))


def blocks_for_page(page, text):
    if not text:
        return []
    offsets = [0]
    for line in text.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    tokens = [t for t in MD.parse(text) if t.level == 0 and t.map]
    excluded = [(offsets[t.map[0]], offsets[t.map[1]]) for t in tokens if t.type in ('fence', 'code_block')]
    tables = TableRanges(text, excluded)
    tables.feed(text)
    tables.close()
    if tables.depth:
        raise ValueError(f'Unclosed HTML table on physical page {page}; repair upstream, not in chunking')
    cuts = {0, len(text)} | {offsets[t.map[0]] for t in tokens}
    # Only split at full Markdown block boundaries, never within an HTML table.
    cuts = sorted(c for c in cuts if not any(a < c < b for a, b in tables.ranges))
    starts = {offsets[t.map[0]]: t for t in tokens}
    blocks = []
    for a, b in zip(cuts, cuts[1:]):
        token = starts.get(a)
        kind = 'paragraph'
        if any(a <= x < b for x, _ in tables.ranges) or token and token.type == 'table_open':
            kind = 'table'
        elif token and token.type == 'heading_open':
            kind = 'heading'
        elif token and token.type in ('fence', 'code_block'):
            kind = 'code'
        elif token and token.type in ('bullet_list_open', 'ordered_list_open'):
            kind = 'list'
        block = Block(page, a, b, text[a:b], kind)
        if kind == 'heading':
            block.level, block.title = int(token.tag[1:]), plain(block.text)
        blocks.append(block)
    return blocks


def heading_decisions(blocks):
    occurrences = defaultdict(set)
    for b in blocks:
        if b.kind == 'heading':
            occurrences[title_key(b.title)].add(b.page)
    for b in blocks:
        if b.kind != 'heading':
            continue
        title = b.title
        letters = ''.join(c for c in title if c.isalpha())
        if not letters or len(letters) <= 4 and re.search(r'\d', title):
            b.reason = 'numeric_display'
        elif re.match(r'^(?:for the (?:year|period|half.year)|as at|at(?= \d)|year ended|half.year (?:to|ended))\b', title, re.I):
            b.reason = 'period_context'
        elif len(occurrences[title_key(title)]) >= 3 and re.search(r'\b(?:limited|ltd|plc|inc|corporation)\b', title, re.I):
            b.reason = 'repeated_entity_heading'
        else:
            b.reason = 'section_candidate'


def sections(blocks):
    """Return conservative candidate sections. Heading levels remain heuristic."""
    groups, current, stack, pending = [], [], [], []
    current_path, current_evidence = [], []
    last_page = None

    def flush():
        nonlocal current
        if current:
            groups.append((current_path.copy(), current_evidence.copy(), current))
            current = []

    for block in blocks:
        new_page = block.page != last_page
        last_page = block.page
        if new_page and pending:
            current.extend(pending)
            pending = []
        if block.kind == 'heading' and block.reason != 'section_candidate':
            # Leading company/date lines travel with the following heading, not the preceding page.
            if new_page or pending:
                pending.append(block)
            else:
                current.append(block)
            continue
        if block.kind == 'heading':
            key = title_key(block.title)
            matching = next((i for i, h in enumerate(stack) if title_key(h.title) == key), None)
            if matching is not None:
                # Repeated / continued title returns to that section, without creating another child.
                changed = matching < len(stack) - 1
                if changed:
                    flush()
                stack = stack[:matching + 1]
            else:
                flush()
                while stack and stack[-1].level >= block.level:
                    stack.pop()
                stack.append(block)
            current_path = [h.title for h in stack]
            current_evidence = [dict(**h.location(), title=h.title) for h in stack]
        current.extend(pending)
        pending = []
        current.append(block)
    current.extend(pending)
    flush()
    return groups


def slice_spans(pages, locations):
    return ''.join(pages[s['page'] - 1]['markdown'][s['start']:s['end']] for s in locations)


def pack_spans(blocks):
    result = []
    for b in blocks:
        if result and result[-1]['page'] == b.page and result[-1]['end'] == b.start:
            result[-1]['end'] = b.end
        else:
            result.append(b.location())
    return result


def make_chunk(doc, strategy, blocks, path, evidence, context=None, max_chars=4000, page=None):
    locations = pack_spans(blocks)
    if not locations and page is not None:
        locations = [span(page, 0, 0)]
    content = slice_spans(doc['pages'], locations)
    context = context or []
    flags = []
    if len(content) > max_chars:
        flags.append('soft_budget_exceeded')
    if any(len(b.text) > max_chars for b in blocks):
        flags.append('oversized_atomic_block')
    if any(b.kind == 'table' for b in blocks):
        flags.append('table_preserved_as_exported')
    if not plain(content):
        flags.append('no_visible_text')
    metadata = doc.get('document_metadata', {})
    metadata_text = ' '.join(f'{k}: {json.dumps(v["value"], ensure_ascii=False)}' for k, v in metadata.items()
                             if v['status'] == 'resolved')
    retrieval = '\n'.join(x for x in [metadata_text, ' > '.join(path), plain(content),
                                      plain(slice_spans(doc['pages'], context))] if x)
    identity = [VERSION, doc['source_sha256'], doc['pages_sha256'], doc['parser'], strategy, max_chars,
                locations, path, context, doc.get('metadata_sha256')]
    return dict(schema_version=1, chunker_version=VERSION, soft_max_chars=max_chars,
                chunk_id=f'{doc["document_id"]}:{strategy}:{digest(identity)[:20]}',
                strategy=strategy, document_id=doc['document_id'], parser=doc['parser'],
                source_sha256=doc['source_sha256'], pages_sha256=doc['pages_sha256'],
                source_artifact=doc.get('source_artifact'), metadata_sha256=doc.get('metadata_sha256'),
                content=content, source_spans=locations, section_path=path, heading_evidence=evidence,
                context_spans=context, document_metadata=metadata, retrieval_text=retrieval,
                char_count=len(content), flags=flags)


def chunk_document(doc, max_chars=4000):
    if max_chars < 100:
        raise ValueError('max_chars must be at least 100; this is a soft raw-Markdown character budget')
    per_page = [blocks_for_page(p['page'], p['markdown']) for p in doc['pages']]
    blocks = [b for page in per_page for b in page]
    heading_decisions(blocks)
    baseline = [make_chunk(doc, 'page', items, [], [], max_chars=max_chars, page=i + 1)
                for i, items in enumerate(per_page)]
    structured = []
    global_indexes = {id(b): i for i, b in enumerate(blocks)}
    for path, evidence, items in sections(blocks):
        batches, batch, size = [], [], 0
        for block in items:
            # Never strand a run of headings merely to meet the soft size budget.
            headings_only = batch and all(b.kind == 'heading' for b in batch)
            if batch and size + len(block.text) > max_chars and not headings_only:
                batches.append(batch)
                batch, size = [], 0
            batch.append(block)
            size += len(block.text)
        if batch:
            batches.append(batch)
        indexes = {id(b): i for i, b in enumerate(items)}
        for batch in batches:
            context = []
            if any(b.kind == 'table' for b in batch):
                first, last = indexes[id(batch[0])], indexes[id(batch[-1])]
                # Adjacent text is explicitly additional context, not duplicate primary content.
                for index in (first - 1, last + 1):
                    if 0 <= index < len(items):
                        b = items[index]
                        if b.kind not in ('table', 'code') and len(b.text) <= 1200:
                            context.append(b.location())
                # A following notes heading can form its own section. Keep a bounded,
                # explicitly heuristic link to it rather than losing the table's nearby notes.
                after = global_indexes[id(batch[-1])] + 1
                if after < len(blocks):
                    candidate = blocks[after]
                    if candidate.kind == 'heading' and re.match(r'^(?:notes?|source|units?|basis)\b', candidate.title, re.I):
                        budget = 2000
                        for neighbor in blocks[after:after + 4]:
                            if neighbor.page != batch[-1].page or neighbor.kind == 'table':
                                break
                            if neighbor is not candidate and neighbor.kind == 'heading':
                                break
                            if len(neighbor.text) > budget:
                                break
                            context.append(neighbor.location())
                            budget -= len(neighbor.text)
            structured.append(make_chunk(doc, 'section', batch, path, evidence, context, max_chars))
    decisions = [dict(**b.location(), title=b.title, level=b.level, decision=b.reason)
                 for b in blocks if b.kind == 'heading']
    return baseline, structured, decisions


def validate_chunks(doc, chunks):
    """Check exact character coverage, ordering, source slices and complete exported tables."""
    pages = doc['pages']
    intervals = defaultdict(list)
    ids = set()
    last = (0, 0)
    for c in chunks:
        if any(c[key] != doc[key] for key in ('document_id', 'parser', 'source_sha256', 'pages_sha256')):
            raise ValueError('Chunk source identity mismatch')
        if c['chunk_id'] in ids:
            raise ValueError('Duplicate chunk ID')
        ids.add(c['chunk_id'])
        for s in c['source_spans'] + c['context_spans'] + c['heading_evidence']:
            if not 1 <= s['page'] <= len(pages) or not 0 <= s['start'] <= s['end'] <= len(pages[s['page'] - 1]['markdown']):
                raise ValueError('Invalid source location')
            if s['json_pointer'] != f'/pages/{s["page"] - 1}/markdown':
                raise ValueError('Source pointer/page mismatch')
        if c['content'] != slice_spans(pages, c['source_spans']):
            raise ValueError('Content differs from source slices')
        for s in c['source_spans']:
            if (s['page'], s['start']) < last:
                raise ValueError('Chunks are out of source order')
            last = (s['page'], s['end'])
            intervals[s['page']].append((s['start'], s['end'], c['chunk_id']))
    tables = 0
    for p in pages:
        cursor = 0
        for start, end, _ in intervals[p['page']]:
            if start != cursor:
                raise ValueError('Lost or duplicated primary source characters')
            cursor = end
        if cursor != len(p['markdown']):
            raise ValueError('Missing source characters')
        for b in blocks_for_page(p['page'], p['markdown']):
            if b.kind == 'table':
                tables += 1
                if not any(a <= b.start and z >= b.end for a, z, _ in intervals[p['page']]):
                    raise ValueError('An exported table block was split')
    return dict(exact_character_coverage=True, ordered=True, source_characters=sum(len(p['markdown']) for p in pages),
                table_blocks_preserved=tables, chunk_count=len(chunks))


class SafeHTML(HTMLParser):
    ALLOWED = {'p', 'br', 'strong', 'em', 'ul', 'ol', 'li', 'blockquote', 'pre', 'code',
               'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'sup', 'sub', 'hr',
               'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}

    def __init__(self):
        super().__init__()
        self.output, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        if self.hidden:
            return
        if tag in self.ALLOWED:
            keep = ''.join(f' {k}="{v}"' for k, v in attrs if tag in ('td', 'th') and
                           k in ('rowspan', 'colspan') and v and v.isdigit() and 0 < int(v) <= 1000)
            self.output.append(f'<{tag}{keep}>')
        elif tag == 'img':
            self.output.append('<span>[Image reference; see the path in the original Markdown]</span>')

    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.hidden:
            self.hidden -= 1
        elif not self.hidden and tag in self.ALLOWED:
            self.output.append(f'</{tag}>')

    def handle_data(self, data):
        if not self.hidden:
            self.output.append(escape(data))


def safe_render(text):
    parser = SafeHTML()
    parser.feed(MD.render(text))
    return ''.join(parser.output)
