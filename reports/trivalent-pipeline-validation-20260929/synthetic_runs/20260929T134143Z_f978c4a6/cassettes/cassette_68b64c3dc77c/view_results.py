from pathlib import Path
from pymol import cmd
import json
root=Path(__file__).resolve().parent
for i,p in enumerate(sorted((root/"pair_models").glob("*")),1):
    cmd.load(str(p), f"pair_{i}")
    cmd.disable(f"pair_{i}")
for p in sorted((root/"predictions").glob("*.cif")):
    if p.name.endswith(".source.cif"): continue
    cmd.load(str(p),p.stem)
    cmd.disable(p.stem)
cmd.hide("everything","all")
cmd.show("cartoon","all")
cmd.color("gray70","all")
for meta in sorted((root/"predictions").glob("*.mapping.json")):
    m=json.loads(meta.read_text()); obj=m["object"]
    for region in m["binder_regions"]:
        cmd.color(region["color"],"{} and chain A and resi {}-{}".format(obj,region["start"],region["end"]))
if cmd.get_names("objects"):
    cmd.enable(cmd.get_names("objects")[-1]);cmd.zoom(cmd.get_names("objects")[-1])
