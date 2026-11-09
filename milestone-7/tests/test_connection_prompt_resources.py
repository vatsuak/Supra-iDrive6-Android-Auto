#!/usr/bin/env python3
"""Validate actual packaged XML/text references, not firmware rendering."""
import pathlib
import xml.etree.ElementTree as ET
import zipfile

root = pathlib.Path(__file__).resolve().parents[1]
apps = ET.parse(root / "rhmiapp/NbtAad.xml").getroot().findall("pluginApp")
app = apps[0]
states = list(app.find("hmiStates"))
assert [s.attrib["id"] for s in states[:5]] == ["10", "12", "13", "11", "14"]
assert states[5].tag == "popupHmiState" and states[5].attrib["id"] == "132"
event = app.find("events/popupEvent")
assert event.attrib == {"id": "131", "target": "132", "priority": "0"}
actions = {a.attrib["id"] for a in app.find("actions")}
models = {m.attrib["id"] for m in app.find("models")}
for state in states:
    assert state.attrib["textModel"] in models
    for component in state.findall("components/*"):
        if "action" in component.attrib:
            assert component.attrib["action"] in actions
        for name in ("model", "imageModel", "textModel"):
            if name in component.attrib:
                assert component.attrib[name] in models
popup_actions = [c.attrib["action"] for c in states[5].findall("components/button")]
assert popup_actions == ["122", "123"]
assert apps[1].find("entryButton/properties/property").attrib["value"] == "02773afe-a0dc-564a-95d8-a4768ea38a65"
texts = {m.attrib["textId"] for m in app.findall("models/textIdModel")}
with zipfile.ZipFile(root / "rhmiapp/NbtAad_ALL_Texts.zip") as z:
    assert len(z.namelist()) == 10
    for name in z.namelist():
        available = {line.partition("=")[0] for line in z.read(name).decode().splitlines() if "=" in line}
        assert texts <= available, (name, texts - available)
print("popup resources, existing state order and favourite UUID: OK (firmware rendering unverified)")
