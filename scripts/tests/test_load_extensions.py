import os
from scripts.load_extensions import load_extension_patterns


def test_load_extensions_patterns():
    patterns = load_extension_patterns('docs/target-extensions.csv')
    assert '**/*.java' in patterns
    assert '**/*.py' in patterns
    assert '**/*.ts' in patterns
