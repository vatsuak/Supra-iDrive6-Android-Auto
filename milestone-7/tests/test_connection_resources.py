#!/usr/bin/env python3
"""Connection controls, tile labels and upstream song-title labels stay distinct."""
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

root = Path(__file__).resolve().parents[1] / 'rhmiapp'
apps = ET.parse(root / 'NbtAad.xml').getroot().findall('pluginApp')
assert apps[0].find('entryButton').get('action') == '5'
assert apps[1].find('entryButton').get('action') == '2'
models = {m.get('id'): m for m in apps[0].find('models')}
settings = {
    '24': ('34', '15', 'Connect automatically'),
    '185': ('186', '50', 'Open Android Auto automatically'),
    '181': ('182', '51', 'Show Android Auto tile'),
}
for action, (model, text, label) in settings.items():
    rows = [r for r in apps[0].iter('checkbox') if r.get('action') == action]
    assert len(rows) == 1, action
    assert rows[0].get('model') == model
    assert models[rows[0].get('textModel')].get('textId') == text
assert models['472'].get('textId') == '49'
with zipfile.ZipFile(root / 'NbtAad_ALL_Texts.zip') as archive:
    assert {'pl.txt', 'hu.txt'} <= set(archive.namelist())
    for name in archive.namelist():
        texts = dict(line.split('=', 1) for line in archive.read(name).decode().splitlines())
        for _, text, label in settings.values():
            assert texts[text] == label, (name, text)
        assert texts['49'] != texts['51'], name
        assert texts['10'] == 'Connect Android Auto'
print('test_connection_resources: all passed')
