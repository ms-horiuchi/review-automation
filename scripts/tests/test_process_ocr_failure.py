import sys
from pathlib import Path
import types
import pytest

import importlib

# Provide fake PIL before importing process_ocr
class FakeImage:
    def __init__(self, path=None):
        self._path = path
    def convert(self, mode):
        return self
    def filter(self, *_args, **_kwargs):
        return self
    def point(self, func):
        return self

class FakeImageModule:
    @staticmethod
    def open(path):
        return FakeImage(path)

class FakeEnhance:
    class Contrast:
        def __init__(self, image):
            pass
        def enhance(self, factor):
            return FakeImage()

class FakeFilter:
    SHARPEN = object()

import sys
sys.modules['PIL'] = importlib.util.module_from_spec(importlib.machinery.ModuleSpec('PIL', None))
sys.modules['PIL.Image'] = FakeImageModule()
sys.modules['PIL.ImageEnhance'] = FakeEnhance()
sys.modules['PIL.ImageFilter'] = FakeFilter()

import types

# Fake pyocr
class FakeTool:
    def get_name(self):
        return 'fake'
    def get_available_languages(self):
        return ['eng', 'jpn']
    def image_to_string(self, image, lang, builder):
        return ''

class FakePyOCR:
    def __init__(self):
        self.builders = types.SimpleNamespace(TextBuilder=lambda: object())
    def get_available_tools(self):
        return [FakeTool()]

sys.modules['pyocr'] = FakePyOCR()
sys.modules['pyocr.builders'] = sys.modules['pyocr'].builders

import scripts.process_ocr as pocr

class DummyTool:
    def get_name(self):
        return "fake"
    def get_available_languages(self):
        return ['eng', 'jpn']
    def image_to_string(self, image, lang, builder):
        return ""

class DummyOCR:
    def __init__(self):
        self.builders = types.SimpleNamespace(TextBuilder=lambda: object())
    def get_available_tools(self):
        return [DummyTool()]


def test_ocr_fails_with_no_outputs(monkeypatch, tmp_path):
    # monkeypatch a fake pyocr module
    fake_pyocr = DummyOCR()
    sys.modules['pyocr'] = fake_pyocr
    sys.modules['pyocr.builders'] = fake_pyocr.builders

    # create a 'nonexistent' image path
    image = tmp_path / 'missing.png'
    # call main with the non-existent path
    with pytest.raises(SystemExit) as ex:
        monkeypatch.setenv('PYTEST_RUNNING', '1')
        # args emulate command line
        monkeypatch.setattr(sys, 'argv', ['process_ocr.py', str(image)])
        pocr.main()
    # expect error code non-zero
    assert ex.value.code == 1