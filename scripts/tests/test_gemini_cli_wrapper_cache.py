import os
import json
from pathlib import Path

import pytest
import sys
import types

# Ensure a fake google.generativeai exists during import
google = types.ModuleType('google')
google.generativeai = types.ModuleType('google.generativeai')
sys.modules['google'] = google
sys.modules['google.generativeai'] = google.generativeai

import scripts.gemini_cli_wrapper as gcw


def test_prompt_cache_roundtrip(tmp_path, monkeypatch):
    # set working dir to tmp
    monkeypatch.chdir(tmp_path)
    # ensure no cache file exists
    cache_file = tmp_path / '.prompt_upload_cache.json'
    if cache_file.exists():
        cache_file.unlink()

    called = {'uploads': 0}

    def fake_upload(path):
        called['uploads'] += 1
        return f"fileid-{os.path.basename(path)}"

    # monkeypatch upload_prompt_file to the fake (but keep original cache handling)
    monkeypatch.setattr(gcw, 'upload_prompt_file', fake_upload)

    paths = [str(tmp_path / 'p1.md'), str(tmp_path / 'p2.md')]
    for p in paths:
        Path(p).write_text('# prompt')

    # First call -> should call upload
    uploaded_map = gcw.upload_prompt_files(paths)
    assert called['uploads'] == 2
    assert len(uploaded_map) == 2

    # Save a cache file like the module would have done, to simulate persistence across runs
    cache = {str(Path(p).resolve()): f"fileid-{os.path.basename(p)}" for p in paths}
    cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding='utf-8')

    # Now simulate calling again; cache file exists so our fake upload should not be called
    called['uploads'] = 0
    uploaded_map2 = gcw.upload_prompt_files(paths)
    assert called['uploads'] == 0
    assert 'p1.md' in uploaded_map2[list(uploaded_map2.keys())[0]] or len(uploaded_map2) == 2