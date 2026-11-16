import io, json, numpy as np, pandas as pd
from PIL import Image
import plotly.graph_objects as go, plotly.io as pio
from simple_steps_core.output import _data_version

print("== numpy .npy, allow_pickle=False")
arrs = {
 "uint8 image HxWx3": np.random.default_rng(0).integers(0, 255, (4, 5, 3), dtype=np.uint8),
 "float32 + nan": np.array([1.5, np.nan], dtype=np.float32),
 "float16": np.array([0.1], dtype=np.float16), "bool": np.array([True, False]),
 "complex128": np.array([1+2j]), "datetime64": np.array(["2026-01-01"], dtype="datetime64[D]"),
 "structured": np.array([(1, 2.0)], dtype=[("a", "i4"), ("b", "f8")]),
 "fortran order": np.asfortranarray(np.arange(6).reshape(2, 3)), "0-d": np.array(5),
 "big-endian": np.array([1, 2], dtype=">i4"), "object dtype": np.array([{"a": 1}], dtype=object),
}
for n, a in arrs.items():
    b = io.BytesIO()
    try:
        np.save(b, a, allow_pickle=False); r = np.load(io.BytesIO(b.getvalue()), allow_pickle=False)
        same = r.dtype == a.dtype and r.shape == a.shape and np.array_equal(r, a, equal_nan=a.dtype.kind in "fc")
        print(f"  {n}: exact={same} order_kept={r.flags.f_contiguous == a.flags.f_contiguous}")
    except Exception as e: print(f"  {n}: FAILS {type(e).__name__}: {str(e)[:60]}")

print("== PIL image as PNG")
base = Image.fromarray(arrs["uint8 image HxWx3"])
for mode in ["1", "L", "P", "RGB", "RGBA", "I;16", "I", "F", "CMYK", "LA"]:
    try:
        im = base.convert(mode) if mode not in ("I;16",) else Image.fromarray(np.arange(20, dtype=np.uint16).reshape(4, 5))
        b = io.BytesIO(); im.save(b, format="PNG"); r = Image.open(io.BytesIO(b.getvalue())); r.load()
        print(f"  {mode}: exact={r.mode == im.mode and r.size == im.size and r.tobytes() == im.tobytes()} mode {im.mode}->{r.mode}")
    except Exception as e: print(f"  {mode}: FAILS {type(e).__name__}: {str(e)[:50]}")
jb = io.BytesIO(); base.save(jb, format="JPEG", quality=80); j = Image.open(io.BytesIO(jb.getvalue())); j.load()
b = io.BytesIO(); j.save(b, format="PNG"); r = Image.open(io.BytesIO(b.getvalue())); r.load()
print(f"  opened JPEG -> PNG: pixels exact={r.tobytes() == j.tobytes()} format {j.format}->{r.format} info {sorted(j.info)}->{sorted(r.info)}")
for mode in ["F", "CMYK"]:
    im = base.convert(mode); b = io.BytesIO(); im.save(b, format="TIFF"); r = Image.open(io.BytesIO(b.getvalue())); r.load()
    print(f"  {mode} as TIFF: exact={r.mode == im.mode and r.tobytes() == im.tobytes()}")

print("== plotly JSON")
x = np.array([1.5, 2.5], dtype=np.float32)
figs = {"bar, lists": go.Figure(go.Bar(x=["a", "b"], y=[1, 2]), layout=dict(title="t")),
        "scatter, float32 array": go.Figure(go.Scatter(x=x, y=x * 2)),
        "with template": go.Figure(go.Bar(y=[1]), layout=dict(template="plotly_dark")),
        "FigureWidget-like class": go.Figure(go.Heatmap(z=np.eye(3)))}
for n, f in figs.items():
    r = pio.from_json(pio.to_json(f))
    same = pio.to_json(r) == pio.to_json(f)
    print(f"  {n}: json-equal={same} type {type(f).__name__}->{type(r).__name__} x-type {type(f.data[0].x).__name__ if f.data[0].x is not None else '-'}->{type(r.data[0].x).__name__ if r.data[0].x is not None else '-'}")

print("== data versions: equal content, equal version?")
for n, (a, b) in {"ndarray": (np.arange(4), np.arange(4)), "PIL": (base, base.copy()),
                  "plotly": (go.Figure(go.Bar(y=[1])), go.Figure(go.Bar(y=[1])))}.items():
    va = _data_version(pd.DataFrame({"c": [a]})); vb = _data_version(pd.DataFrame({"c": [b]}))
    print(f"  {n}: equal={va == vb}")
