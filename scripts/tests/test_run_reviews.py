import os
import subprocess
from pathlib import Path
import pytest

import scripts.run_reviews as run_reviews


def write_file(path: Path, content: str = "dummy\n"):
    path.write_text(content, encoding='utf-8')


def test_no_files_no_api_key_skips_review(monkeypatch, tmp_path, capsys):
    # Ensure GK not set and no file lists
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    # run in temporary dir so files don't exist
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as ex:
        run_reviews.main()

    assert ex.value.code == 0
    captured = capsys.readouterr()
    assert "No files to review: skip Gemini API calls" in captured.err
    assert "files_to_commit=" in captured.out


def test_files_present_without_api_key_fails(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    # Put a decoded_files.txt with a path inside
    decoded = tmp_path / 'decoded_files.txt'
    write_file(decoded, "some/code/file.py\n")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as ex:
        run_reviews.main()

    assert ex.value.code == 1
    captured = capsys.readouterr()
    assert "Error: GEMINI_API_KEY is not set" in captured.err


class DummyResult:
    def __init__(self):
        self.returncode = 0
        self.stdout = "OK"
        self.stderr = ""


def test_files_present_with_api_key_runs(monkeypatch, tmp_path, capsys):
    # set API key
    monkeypatch.setenv('GEMINI_API_KEY', 'dummy')

    # create decoded file list
    decoded = tmp_path / 'decoded_files.txt'
    write_file(decoded, "some/code/file.py\n")

    # patch run_batch_review to avoid network calls and to create a dummy review file
    def fake_run_batch_review(file_list, output_dir, use_prompt_map=False):
        # create output dir and a dummy md file
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        (output / 'dummy.md').write_text('# dummy review', encoding='utf-8')
        return True

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('REVIEW_BASE_DIR', str(tmp_path))
    monkeypatch.setattr(run_reviews, 'run_batch_review', fake_run_batch_review)

    # Run - should not raise
    run_reviews.main()
    captured = capsys.readouterr()
    assert '生成されたレビューファイル数' in captured.err


def test_batch_review_failure_causes_exit(monkeypatch, tmp_path, capsys):
    # set API key
    monkeypatch.setenv('GEMINI_API_KEY', 'dummy')

    # create decoded file list
    decoded = tmp_path / 'decoded_files.txt'
    decoded.write_text("some/code/file.py\n", encoding='utf-8')
    monkeypatch.chdir(tmp_path)

    # Simulate a failing batch review via return False
    monkeypatch.setenv('REVIEW_BASE_DIR', str(tmp_path))
    monkeypatch.setattr(run_reviews, 'run_batch_review', lambda file_list, output_dir, use_prompt_map=False: False)

    with pytest.raises(SystemExit) as ex:
        run_reviews.main()

    assert ex.value.code == 1
    captured = capsys.readouterr()
    assert 'Error: Batch review for code files failed.' in captured.err


def test_resolve_model_name_ignores_empty_env(monkeypatch):
    # No GEMINI_MODEL set
    monkeypatch.delenv('GEMINI_MODEL', raising=False)
    import scripts.gemini_cli_wrapper as gcw
    # explicit None should return default
    assert gcw._resolve_model_name(None) == 'gemini-2.5-flash'
    # empty env should be ignored
    monkeypatch.setenv('GEMINI_MODEL', '')
    assert gcw._resolve_model_name(None) == 'gemini-2.5-flash'
    # explicit arg should override
    assert gcw._resolve_model_name('gemini-2.5-flash') == 'gemini-2.5-flash'

 