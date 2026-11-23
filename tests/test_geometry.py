"""Run: .venv/Scripts/python tests/test_geometry.py   (no PDFs needed)"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
import geometry as g


def mm(s):
    return [v for v, _, _ in g.lengths_mm(s)]


for s, want in {
    "70 mils in diameter on 100-mil centers": [1.778, 2.54], "1/16-in-spaced 0.3-mm-diameter": [1.5875, 0.3],
    "1/16 inch spacing": [1.5875], "0.5 inch pads": [12.7], "2.5 x 1.25 mm": [2.5, 1.25], "0.25-3.0 mm": [0.25, 3.0],
    "2.5mm to 1.25mm": [2.5, 1.25], "10 mmol/L NaCl": [], "120 mmHg": [], "a 0.5 mm 2 area": [], "3.125 mm2": [],
    "3.1 mm²": [], "5 mm 24 electrodes": [5.0], "300 µm thick, 4.1 cm": [0.3, 41.0], "2 mm and 2 mm": [2.0, 2.0],
    "10 mm in diameter": [10.0], "25 cm2": [], "8 mm, 3 of": [8.0], "3 cm/s": [],
}.items():
    assert mm(s) == want, (s, mm(s), want)
assert g.clean("elec￾\r\ntrode") == "electrode"
assert g.clean("100￾\nmil") == "100-mil"
assert g.contact_area("disc", 5) == 19.635 and g.contact_area("square", 2) == 4
assert g.contact_area("ring", 10, 5) == 58.9049
assert g.contact_area("ring", 10) is None and g.contact_area("rectangle", 2) is None
assert mm(g.clean("0.3-mm"+chr(0xfffe)+"diameter")) == [0.3]
d = g.derive({"gap_mm": 0.25, "contact_dim_mm": 2.5, "contact_dim2_mm": 1.25, "contact_shape": "rectangle"})
assert d["gap_used_mm"] == 0.25 and d["pitch_used_mm"] is None and d["at_or_below_pitch_floor"] is None
assert d["area_mm2"] == 3.125
d = g.derive({"gap_mm": 1, "contact_dim_mm": 1, "contact_shape": "disc"})
assert d["pitch_used_mm"] == 2 and d["pitch_source"] == "gap_plus_contact" and d["pitch_to_contact_ratio"] == 2
assert g.derive({"spacing_mm": 2, "contact_dim_mm": 1})["pitch_used_mm"] is None
assert next(c for c in g.completeness([{"pitch_mm": -1}, {"pitch_mm": 2}]) if c["field"] == "pitch_mm")["n"] == 1
t = "Each electrode has a radius of 1 mm and the center-to-center dis￾\r\ntance is 4 mm."
q = ["radius of 1 mm and the center-to-center distance is 4 mm"]
assert g.audit({"electrodes": [{"contact_dim_mm": 2, "pitch_mm": 4, "quotes": q}]}, t) == []
assert len(g.audit({"electrodes": [{"pitch_mm": 3, "quotes": ["the pitch is 4 mm"]}]}, t)) == 2
assert g.audit({"impedances": [{"Z_ohm_min": 5000, "Z_source": "guess", "quotes": q}]}, t)
assert g.derive({"contact_shape": "line", "contact_dim_mm": 20, "pitch_mm": 1})["pitch_to_contact_ratio"] is None
assert g._states(185960, "Rp (K\u03a9) 8.33 185.96 0.12") and g._states(10000, "5000-10 000 ohms")
assert g._states(2e6, "of 2 X 106 ohms") and not g._states(33185.96, "8.33 185.96")
print("ok")
