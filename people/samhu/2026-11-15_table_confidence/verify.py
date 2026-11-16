"""Audit produced evidence, crop provenance, exports and report image integrity."""
import argparse
import base64
import csv
from html.parser import HTMLParser
import io
from pathlib import Path

from regions import table_summary
from core import digest, read, sha, write


def verify(root):
    from PIL import Image
    bundle = read(root / 'tables.json')
    summary = read(root / 'summary.json')
    assert len(bundle['tables']) == len(summary['tables'])
    expected_settings = digest(bundle['settings'])
    bundle_sha256 = sha(root / 'tables.json')
    engine_settings = {}
    for engine in ('mineru','paddle_vl','glm','monkey'):
        folder = root/'mineru' if engine=='mineru' else root/'extra'/engine
        if (folder/'settings.json').exists():
            settings = read(folder/'settings.json')
            assert settings['source_bundle_sha256'] == bundle_sha256
            engine_settings[engine] = settings
    successful, pending, failed, hooks, truncated = {}, {}, {}, {}, {}
    for table in bundle['tables']:
        assert table['settings_sha256'] == expected_settings
        assert sha(root / table['image']) == table['image_sha256']
        models = {name: result['crop'] for name, result in table['models'].items()}
        mineru = root / 'mineru' / (table['table_id'] + '.json')
        if 'mineru' in engine_settings:
            settings = engine_settings['mineru']
            if mineru.exists():
                result = read(mineru)
                assert result['image_sha256'] == table['image_sha256']
                assert result['source_sha256'] == table['source_sha256']
                assert result['settings_sha256'] == digest(settings)
                models['mineru'] = result
            else:
                models['mineru'] = dict(status='pending')
        for engine in ('paddle_vl', 'glm', 'monkey'):
            folder = root / 'extra' / engine
            if engine not in engine_settings:
                continue
            settings = engine_settings[engine]
            path = folder / (table['table_id'] + '.json')
            if not path.exists():
                models[engine] = dict(status='pending')
                continue
            result = read(path)
            assert result['image_sha256'] == table['image_sha256']
            assert result['source_sha256'] == table['source_sha256']
            assert result['settings_sha256'] == digest(settings)
            if result['status'] == 'success':
                units = result['confidence_units']
                assert [u['token_id'] for u in units] == result['token_ids']
                if result['content_only']['status'] == 'available':
                    assert table_summary([u for u in units if u['content_class'] == 'content']) == result['content_only']['confidence']
            models[engine] = result
        for name, result in models.items():
            if result['status'] == 'success':
                assert table_summary(result['confidence_units']) == result['confidence']
                successful[name] = successful.get(name, 0) + 1
                if result.get('hook_equivalence_passed'):
                    hooks[name] = hooks.get(name, 0) + 1
                if result.get('truncated'):
                    truncated[name] = truncated.get(name, 0) + 1
            elif result['status'] == 'pending':
                pending[name] = pending.get(name, 0) + 1
            else:
                failed[name] = failed.get(name, 0) + 1
    with (root / 'table_scores.csv').open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == sum(len(t['models']) for t in summary['tables'])
    assert len({(r['table_id'], r['engine']) for r in rows}) == len(rows)

    class Check(HTMLParser):
        def __init__(self):
            super().__init__()
            self.images = 0
            self.articles = 0

        def handle_starttag(self, tag, attrs):
            if tag == 'article':
                self.articles += 1
            if tag == 'img':
                url = dict(attrs)['src']
                assert url.startswith('data:image/png;base64,')
                Image.open(io.BytesIO(base64.b64decode(url.split(',', 1)[1]))).verify()
                self.images += 1

    check = Check()
    check.feed((root / 'report.html').read_text())
    assert check.articles == len(bundle['tables'])
    assert check.images == len(bundle['tables']) + sum(p['status'] == 'success' for p in bundle['pages'])
    audit = dict(pages=len(bundle['pages']), table_regions=len(bundle['tables']),
                 successful=successful, pending=pending, failed=failed, token_limit=truncated,
                 hook_equivalence_checks_passed=hooks, valid_embedded_images=check.images,
                 nested_detections_suppressed=sum(len(p.get('suppressed_nested_detections', [])) for p in bundle['pages']),
                 scores_recomputed_from_native_units=True, source_crop_hashes_verified=True,
                 correctness_validated=False,
                 browser_visual_preview='Unavailable: local-file browser preview blocked; source crops visually inspected and HTML/image structure checked')
    write(root / 'audit.json', audit)
    return audit


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('root', type=Path)
    print(verify(cli.parse_args().root))
