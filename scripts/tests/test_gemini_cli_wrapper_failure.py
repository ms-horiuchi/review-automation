import sys
import types
import os
import traceback
from pathlib import Path
import pytest

# Ensure a fake google.generativeai exists during import
google = types.ModuleType('google')
google.generativeai = types.ModuleType('google.generativeai')
sys.modules['google'] = google
sys.modules['google.generativeai'] = google.generativeai

import scripts.gemini_cli_wrapper as gcw


def test_batch_review_files_logs_original_cause(monkeypatch, tmp_path, capsys):
    # change cwd
    monkeypatch.chdir(tmp_path)
    # set env api key
    monkeypatch.setenv('GEMINI_API_KEY', 'dummy')

    # create a single file to review
    code_file = tmp_path / 'sample.py'
    code_file.write_text('print("hello")\n', encoding='utf-8')
    file_list = tmp_path / 'files.txt'
    file_list.write_text(str(code_file) + '\n', encoding='utf-8')

    # fake upload/get functions so prompt processing does not fail
    def fake_upload_file(path):
        class U:
            def __init__(self):
                self.name = f"fileid-{os.path.basename(path)}"
                self.file_id = self.name
        return U()

    def fake_get_file(name):
        class F:
            state = types.SimpleNamespace(name='ACTIVE')
            name = name
            file_id = name
            uri = f"file://{name}"
            mime_type = 'text/plain'
        return F()

    google.generativeai.configure = lambda api_key: None
    google.generativeai.upload_file = fake_upload_file
    google.generativeai.get_file = fake_get_file

    # Fake model that raises an exception in generate_content
    class BadModel:
        def __init__(self, name):
            self.name = name

        def generate_content(self, contents):
            raise Exception("model error: simulated failure")

    google.generativeai.GenerativeModel = BadModel

    # Output directory
    outdir = tmp_path / 'out'

    with pytest.raises(SystemExit) as ex:
        gcw.batch_review_files(str(file_list), str(outdir))

    assert ex.value.code == 1

    # The review file should include original cause and traceback
    mdfile = outdir / 'sample.md'
    assert mdfile.exists()
    content = mdfile.read_text(encoding='utf-8')
    assert '自動レビューに失敗しました。担当者に確認してください。' in content
    assert '原始原因' in content
    assert 'model error: simulated failure' in content

    captured = capsys.readouterr()
    # stderr should contain the traceback and original message
    assert 'model error: simulated failure' in captured.err


