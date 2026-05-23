import json, subprocess
from pathlib import Path

PADS = """*PART*
COMP U1 value=MCU footprint=QFN48
COMP R1 value=10k footprint=0402
*NET*
NET GND
U1.1
R1.1
NET SIG
U1.2
R1.2
"""
BOM = "Designator,Value,MPN,Manufacturer,Description,Footprint\nU1,MCU,STM32,ST,Controller,QFN48\nR1,10k,RC0402,Yageo,Resistor,0402\nC9,100n,CC0402,Murata,Cap,0402\n"
XML = """<IPC2581><Layer name='L1' type='signal'/><Layer name='L2' type='signal'/><Component refdes='U1' x='1' y='2'/><Component refdes='R1' x='3' y='4'/><Net name='GND'><Pin refdes='U1' pin='1'/><Pin refdes='R1' pin='1'/></Net><Net name='SIG'><Pin refdes='U1' pin='2'/><Pin refdes='R1' pin='2'/></Net><Via x='5' y='6' drill='0.2'/><Segment x1='1' y1='1' x2='2' y2='2' net='SIG'/></IPC2581>"""
XML_NS = """<ns:IPC2581 xmlns:ns='urn:test'><ns:Layer name='L1'/><ns:Layer name='L2'/><ns:Component refdes='U1'/><ns:Component refdes='R1'/><ns:Net name='GND'><ns:Pin refdes='U1' pin='1'/><ns:Pin refdes='R1' pin='1'/></ns:Net></ns:IPC2581>"""

def run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)

def test_all(tmp_path):
    root = Path(__file__).resolve().parents[1]
    net = tmp_path/"pads.asc"; net.write_text(PADS)
    bom = tmp_path/"bom.csv"; bom.write_text(BOM)
    xml = tmp_path/"ipc.xml"; xml.write_text(XML)
    xmlns = tmp_path/"ipcns.xml"; xmlns.write_text(XML_NS)
    out = tmp_path/"out"

    r = run(["python3","pads_ascii_to_thomson_sch.py","--netlist",str(net),"--bom",str(bom),"--project","t1","--output",str(out),"--pretty"], root)
    assert r.returncode == 0
    sch = json.loads((out/"t1-thomson-export-sch.json").read_text())
    assert len(sch["components"]) >= 2 and len(sch["nets"]) >= 2

    (tmp_path/"empty.asc").write_text("")
    r = run(["python3","pads_ascii_to_thomson_sch.py","--netlist",str(tmp_path/"empty.asc"),"--project","e","--output",str(out)], root)
    assert r.returncode != 0

    r = run(["python3","ipc2581_to_thomson.py",str(xml),"--project","b1","--output",str(out),"--pretty"], root)
    assert r.returncode == 0
    brd = json.loads((out/"b1-thomson-export-brd.json").read_text())
    assert len(brd["components"]) == 2

    r = run(["python3","ipc2581_to_thomson.py",str(xmlns),"--project","b2","--output",str(out)], root)
    assert r.returncode == 0

    bad = tmp_path/"bad.xml"; bad.write_text("<x>")
    r = run(["python3","ipc2581_to_thomson.py",str(bad),"--project","bad","--output",str(out)], root)
    assert r.returncode != 0

    dry = tmp_path/"dry"; dry.mkdir()
    r = run(["python3","ipc2581_to_thomson.py",str(xml),"--project","dry","--output",str(dry),"--dry-run"], root)
    assert r.returncode == 0 and not (dry/"dry-thomson-export-brd.json").exists()
    r = run(["python3","altium_orcad_to_thomson_bundle.py","--bundle",str(tmp_path/"bundle_missing"),"--project","bdry","--output",str(tmp_path/"dry2"),"--dry-run"], root)
    assert r.returncode == 0 and not (tmp_path/"dry2").exists()

    bundle = tmp_path/"bundle"; (bundle/"schematic").mkdir(parents=True); (bundle/"layout").mkdir(parents=True)
    (bundle/"schematic/pads_netlist.asc").write_text(PADS)
    (bundle/"schematic/bom.csv").write_text(BOM)
    (bundle/"layout/ipc2581.xml").write_text(XML)
    r = run(["python3","altium_orcad_to_thomson_bundle.py","--bundle",str(bundle),"--project","bun","--output",str(out),"--pretty"], root)
    assert r.returncode == 0
    assert (out/"bun-thomson-export-sch.json").exists()
    assert (out/"bun-thomson-export-brd.json").exists()
    assert (out/"bun-thomson-export-stack.json").exists()
    assert (out/"bun-bundle-conversion-report.json").exists()


def test_phase1_bundle_converter_discovery_and_dryrun(tmp_path):
    root = Path(__file__).resolve().parents[1]
    proj = tmp_path/"proj"
    (proj/"pre_conversion"/"schematic").mkdir(parents=True)
    (proj/"pre_conversion"/"layout").mkdir(parents=True)
    (proj/"pre_conversion"/"schematic"/"n.asc").write_text("*PADS-PCB*\n")
    (proj/"pre_conversion"/"schematic"/"bom.csv").write_text("A,B\n1,2\n")
    (proj/"pre_conversion"/"schematic"/"sch.pdf").write_text("pdf")
    (proj/"pre_conversion"/"layout"/"board.xml").write_text("<IPC-2581/>")
    (proj/"pre_conversion"/"layout"/"fab.pdf").write_text("pdf")

    out = tmp_path/"out"
    r = run(["python3","thomson_bundle_converter.py",str(proj),"--output-root",str(out),"--dry-run","--report-only"], root)
    assert r.returncode == 0
    assert not out.exists()

    r2 = run(["python3","thomson_bundle_converter.py",str(proj),"--output-root",str(out),"--pretty"], root)
    assert r2.returncode == 0
    report = json.loads((out/"proj-conversion-report.json").read_text())
    cats = report["discovery"]["counts_by_category"]
    assert cats["pads_ascii_candidate"] == 1
    assert cats["bom_csv_candidate"] == 1
    assert cats["schematic_pdf_candidate"] == 1
    assert cats["ipc2581_candidate"] == 1
    assert cats["layout_pdf_candidate"] == 1


def test_phase1_examples_compat_mode(tmp_path):
    root = Path(__file__).resolve().parents[1]
    proj = tmp_path/"examples"
    proj.mkdir()
    (proj/"example_pads.asc").write_text("*PADS-PCB*\n")
    (proj/"example_bom.csv").write_text("A,B\n1,2\n")
    (proj/"example_ipc.xml").write_text("<IPC-2581/>")
    (proj/"example_schematic.pdf").write_text("pdf")
    (proj/"example_gerbers.pdf").write_text("pdf")

    out = tmp_path/"o2"
    r = run(["python3","thomson_bundle_converter.py",str(proj),"--output-root",str(out),"--pretty"], root)
    assert r.returncode == 0
    report = json.loads((out/"examples-conversion-report.json").read_text())
    warn_codes = {w["code"] for w in report["warnings"]}
    assert "WARN_EXAMPLES_FLAT_LAYOUT" in warn_codes
    cats = report["discovery"]["counts_by_category"]
    assert cats["pads_ascii_candidate"] == 1
    assert cats["bom_csv_candidate"] == 1
    assert cats["ipc2581_candidate"] == 1
    assert cats.get("schematic_pdf_candidate", 0) + cats.get("layout_pdf_candidate", 0) == 2
    files = report["discovery"]["files"]
    gerber = [f for f in files if f["relative_path"] == "example_gerbers.pdf"][0]
    assert gerber["category"] == "layout_pdf_candidate"

def test_phase2_bom_simple_and_multi_refdes(tmp_path):
    root = Path(__file__).resolve().parents[1]
    proj = tmp_path / "proj"
    (proj / "pre_conversion" / "schematic").mkdir(parents=True)
    (proj / "pre_conversion" / "layout").mkdir(parents=True)
    (proj / "pre_conversion" / "schematic" / "bom.csv").write_text(
        "Designator,Value,Qty,DNP\nR1 R2,10k,2,No\nC1-C3,100n,3,Yes\n"
    )
    out = tmp_path / "out"
    r = run(["python3", "thomson_bundle_converter.py", str(proj), "--output-root", str(out), "--pretty"], root)
    assert r.returncode == 0
    bom = json.loads((out / "proj-bom.json").read_text())
    assert bom["row_count"] == 2
    assert bom["expanded_refdes_count"] == 5
    assert bom["items"][0]["fields"]["dnp"] is False
    assert bom["items"][1]["fields"]["dnp"] is True


def test_phase2_bom_duplicate_refdes(tmp_path):
    root = Path(__file__).resolve().parents[1]
    proj = tmp_path / "proj"
    (proj / "pre_conversion" / "schematic").mkdir(parents=True)
    (proj / "pre_conversion" / "layout").mkdir(parents=True)
    (proj / "pre_conversion" / "schematic" / "bom.csv").write_text(
        "RefDes,Description\nU1,MCU\nU1,MCU2\n"
    )
    out = tmp_path / "out"
    r = run(["python3", "thomson_bundle_converter.py", str(proj), "--output-root", str(out)], root)
    assert r.returncode == 0
    bom = json.loads((out / "proj-bom.json").read_text())
    assert "U1" in bom["duplicate_refdes"]


def test_phase2_bom_real_examples_smoke_if_present(tmp_path):
    root = Path(__file__).resolve().parents[1]
    examples = root / "examples"
    if not examples.exists():
        return
    out = tmp_path / "out"
    r = run(["python3", "thomson_bundle_converter.py", str(examples), "--project-name", "example", "--output-root", str(out), "--pretty"], root)
    assert r.returncode == 0
    assert (out / "example-bom.json").exists()
    report = json.loads((out / "example-conversion-report.json").read_text())
    assert "bom" in report

def test_phase3_pads_parse_and_bom_merge(tmp_path):
    root = Path(__file__).resolve().parents[1]
    proj = tmp_path / "proj"
    (proj / "pre_conversion" / "schematic").mkdir(parents=True)
    (proj / "pre_conversion" / "layout").mkdir(parents=True)
    (proj / "pre_conversion" / "schematic" / "net.asc").write_text(
        "*PADS-PCB*\n*PART*\nCOMP U1 value=MCU footprint=QFN48\nCOMP R1 value=10k footprint=0402\n*NET*\nNET GND\nU1.1\nR1.1\nNET SIG\nU1.2\nR1.2\n"
    )
    (proj / "pre_conversion" / "schematic" / "bom.csv").write_text(
        "RefDes,Value,Footprint,Description\nU1,MCU,QFN48,Controller\nR1,10k,0402,Resistor\n"
    )
    out = tmp_path / "out"
    r = run(["python3", "thomson_bundle_converter.py", str(proj), "--output-root", str(out), "--pretty"], root)
    assert r.returncode == 0
    sch = json.loads((out / "proj-thomson-export-sch.json").read_text())
    assert len(sch["components"]) == 2
    assert len(sch["nets"]) == 2
    assert sch["bom_merge"]["components_with_bom_metadata"] == 2
    sig = {n["name"]: n for n in sch["nets"]}["SIG"]
    assert sig["node_count"] == 2


def test_phase3_pads_value_mismatch_warning(tmp_path):
    root = Path(__file__).resolve().parents[1]
    proj = tmp_path / "proj"
    (proj / "pre_conversion" / "schematic").mkdir(parents=True)
    (proj / "pre_conversion" / "layout").mkdir(parents=True)
    (proj / "pre_conversion" / "schematic" / "net.asc").write_text(
        "*PADS-PCB*\n*PART*\nCOMP U1 value=A footprint=QFN48\n*NET*\nNET G\nU1.1\n"
    )
    (proj / "pre_conversion" / "schematic" / "bom.csv").write_text("RefDes,Value\nU1,B\n")
    out = tmp_path / "out"
    r = run(["python3", "thomson_bundle_converter.py", str(proj), "--output-root", str(out)], root)
    assert r.returncode == 0
    report = json.loads((out / "proj-conversion-report.json").read_text())
    codes = {w["code"] for w in report["warnings"]}
    assert "WARN_COMPONENT_VALUE_MISMATCH" in codes


def test_phase3_real_examples_smoke_if_present(tmp_path):
    root = Path(__file__).resolve().parents[1]
    examples = root / "examples"
    if not examples.exists():
        return
    out = tmp_path / "out"
    r = run(["python3", "thomson_bundle_converter.py", str(examples), "--project-name", "example", "--output-root", str(out), "--pretty"], root)
    assert r.returncode == 0
    assert (out / "example-thomson-export-sch.json").exists()
    sch = json.loads((out / "example-thomson-export-sch.json").read_text())
    assert "components" in sch and "nets" in sch

def test_phase4_ipc_minimal_and_namespace(tmp_path):
    root = Path(__file__).resolve().parents[1]
    proj = tmp_path / "proj"
    (proj / "pre_conversion" / "schematic").mkdir(parents=True)
    (proj / "pre_conversion" / "layout").mkdir(parents=True)
    (proj / "pre_conversion" / "schematic" / "bom.csv").write_text("RefDes,Value\nU1,MCU\n")
    (proj / "pre_conversion" / "schematic" / "net.asc").write_text("*PADS-PCB*\n*PART*\nCOMP U1 value=MCU footprint=QFN\n*NET*\nNET GND\nU1.1\n")
    (proj / "pre_conversion" / "layout" / "board.xml").write_text("""<ns:IPC-2581 xmlns:ns='urn:test' revision='B'><ns:Layer name='L1' layerFunction='signal'/><ns:Component refDes='U1' x='1' y='2' layerRef='L1'/><ns:Net name='GND'><ns:PinRef componentRef='U1' pin='1'/></ns:Net><ns:Via x='1' y='1' drill='0.2'/><ns:Segment x1='0' y1='0' x2='1' y2='1' net='GND'/></ns:IPC-2581>""")
    out = tmp_path / "out"
    r = run(["python3", "thomson_bundle_converter.py", str(proj), "--output-root", str(out)], root)
    assert r.returncode == 0
    brd = json.loads((out / "proj-thomson-export-brd.json").read_text())
    stk = json.loads((out / "proj-thomson-export-stack.json").read_text())
    assert brd["source"]["ipc_root"] == "IPC-2581"
    assert len(brd["components"]) == 1
    assert len(brd["layers"]) >= 1
    assert "layer_stack" in stk


def test_phase4_real_examples_ipc_smoke_if_present(tmp_path):
    root = Path(__file__).resolve().parents[1]
    examples = root / "examples"
    if not examples.exists():
        return
    out = tmp_path / "out"
    r = run(["python3", "thomson_bundle_converter.py", str(examples), "--project-name", "example", "--output-root", str(out), "--pretty"], root)
    assert r.returncode == 0
    assert (out / "example-thomson-export-brd.json").exists()
    assert (out / "example-thomson-export-stack.json").exists()

def test_phase5_pdf_report_section_and_dryrun(tmp_path):
    root = Path(__file__).resolve().parents[1]
    proj = tmp_path / "proj"
    (proj / "pre_conversion" / "schematic").mkdir(parents=True)
    (proj / "pre_conversion" / "layout").mkdir(parents=True)
    (proj / "pre_conversion" / "schematic" / "n.asc").write_text("*PADS-PCB*\n*PART*\nCOMP U1\n*NET*\nNET G\nU1.1\n")
    (proj / "pre_conversion" / "schematic" / "b.csv").write_text("RefDes\nU1\n")
    (proj / "pre_conversion" / "layout" / "i.xml").write_text("<IPC-2581/>")
    (proj / "pre_conversion" / "schematic" / "s.pdf").write_bytes(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    out = tmp_path / "out"
    r = run(["python3", "thomson_bundle_converter.py", str(proj), "--output-root", str(out), "--dry-run", "--report-only"], root)
    assert r.returncode == 0
    assert not list(out.glob("*.png"))


def test_phase5_real_examples_png_smoke_if_poppler(tmp_path):
    import shutil
    if not shutil.which("pdftoppm"):
        return
    root = Path(__file__).resolve().parents[1]
    examples = root / "examples"
    if not examples.exists():
        return
    out = tmp_path / "out"
    r = run(["python3", "thomson_bundle_converter.py", str(examples), "--project-name", "example", "--output-root", str(out)], root)
    assert r.returncode == 0
    report = json.loads((out / "example-conversion-report.json").read_text())
    assert "images" in report

def test_phase6_validation_summary_present(tmp_path):
    root = Path(__file__).resolve().parents[1]
    proj = tmp_path / "proj"
    (proj / "pre_conversion" / "schematic").mkdir(parents=True)
    (proj / "pre_conversion" / "layout").mkdir(parents=True)
    (proj / "pre_conversion" / "schematic" / "n.asc").write_text("*PADS-PCB*\n*PART*\nCOMP U1\n*NET*\nNET G\nU1.1\n")
    (proj / "pre_conversion" / "schematic" / "bom.csv").write_text("RefDes\nU1\n")
    (proj / "pre_conversion" / "layout" / "i.xml").write_text("<IPC-2581/>")
    out = tmp_path / "out"
    r = run(["python3", "thomson_bundle_converter.py", str(proj), "--output-root", str(out), "--pretty"], root)
    assert r.returncode == 0
    report = json.loads((out / "proj-conversion-report.json").read_text())
    assert "validation" in report
    assert "ok" in report["validation"]


def test_phase6_missing_optional_pdf_non_strict_ok(tmp_path):
    root = Path(__file__).resolve().parents[1]
    proj = tmp_path / "proj"
    (proj / "pre_conversion" / "schematic").mkdir(parents=True)
    (proj / "pre_conversion" / "layout").mkdir(parents=True)
    (proj / "pre_conversion" / "schematic" / "n.asc").write_text("*PADS-PCB*\n*PART*\nCOMP U1\n*NET*\nNET G\nU1.1\n")
    (proj / "pre_conversion" / "schematic" / "bom.csv").write_text("RefDes\nU1\n")
    (proj / "pre_conversion" / "layout" / "i.xml").write_text("<IPC-2581/>")
    out = tmp_path / "out"
    r = run(["python3", "thomson_bundle_converter.py", str(proj), "--output-root", str(out)], root)
    assert r.returncode == 0
    report = json.loads((out / "proj-conversion-report.json").read_text())
    assert report["validation"]["required_outputs_ok"] is True


def test_phase6_examples_smoke_validation_if_present(tmp_path):
    root = Path(__file__).resolve().parents[1]
    examples = root / "examples"
    if not examples.exists():
        return
    out = tmp_path / "out"
    r = run(["python3", "thomson_bundle_converter.py", str(examples), "--project-name", "example", "--output-root", str(out)], root)
    assert r.returncode == 0
    report = json.loads((out / "example-conversion-report.json").read_text())
    assert "validation" in report


def test_phase610_review_geometry_summary(tmp_path):
    root = Path(__file__).resolve().parents[1]
    proj = tmp_path / "proj"
    (proj / "pre_conversion" / "schematic").mkdir(parents=True)
    (proj / "pre_conversion" / "layout").mkdir(parents=True)
    (proj / "pre_conversion" / "schematic" / "net.asc").write_text(
        "*PADS-PCB*\n*PART*\nCOMP U1\nCOMP J1\n*NET*\n"
        "NET CAN_RX\nU1.1 J1.1\n"
        "NET GND\nU1.2 J1.2\n"
        "NET XY2_CLK_POS\nU1.3 J1.3\n"
        "NET XY2_CLK_NEG\nU1.4 J1.4\n"
        "NET CAN_HI\nU1.5 J1.5\n"
        "NET CAN_LO\nU1.6 J1.6\n"
    )
    (proj / "pre_conversion" / "schematic" / "bom.csv").write_text("RefDes\nU1\nJ1\n")
    (proj / "pre_conversion" / "layout" / "board.xml").write_text(
        """<IPC-2581>
          <DictionaryLineDesc units="INCH">
            <EntryLineDesc id="ROUND_500"><LineDesc lineEnd="ROUND" lineWidth="0.00500"/></EntryLineDesc>
            <EntryLineDesc id="ROUND_400"><LineDesc lineEnd="ROUND" lineWidth="0.00400"/></EntryLineDesc>
          </DictionaryLineDesc>
          <DictionaryFillDesc units="INCH">
            <EntryFillDesc id="SOLID_FILL"><FillDesc fillProperty="FILL"/></EntryFillDesc>
          </DictionaryFillDesc>
          <Layer name="TOP" layerFunction="CONDUCTOR" side="TOP"/>
          <Layer name="LAYER2" layerFunction="PLANE" side="INTERNAL"/>
          <Layer name="BOTTOM" layerFunction="CONDUCTOR" side="BOTTOM"/>
          <Net name="CAN_RX"><PinRef componentRef="U1" pin="1"/></Net>
          <Net name="GND"><PinRef componentRef="U1" pin="2"/></Net>
          <Net name="XY2_CLK_POS"><PinRef componentRef="U1" pin="3"/></Net>
          <Net name="XY2_CLK_NEG"><PinRef componentRef="U1" pin="4"/></Net>
          <Net name="CAN_HI"><PinRef componentRef="U1" pin="5"/></Net>
          <Net name="CAN_LO"><PinRef componentRef="U1" pin="6"/></Net>
          <LayerFeature layerRef="TOP">
            <Set net="CAN_RX"><Features><Polyline><PolyBegin x="0" y="0"/><PolyStepSegment x="1" y="0"/><LineDescRef id="ROUND_500"/></Polyline><Pad/></Features></Set>
            <Set net="XY2_CLK_POS"><Features><Polyline><PolyBegin x="0" y="1"/><PolyStepSegment x="1" y="1"/><LineDescRef id="ROUND_400"/></Polyline></Features></Set>
            <Set net="XY2_CLK_NEG"><Features><Polyline><PolyBegin x="0" y="2"/><PolyStepSegment x="1" y="2"/><LineDescRef id="ROUND_400"/></Polyline></Features></Set>
            <Set net="CAN_HI"><Features><Polyline><PolyBegin x="0" y="3"/><PolyStepSegment x="1" y="3"/><LineDescRef id="ROUND_500"/></Polyline></Features></Set>
            <Set net="CAN_LO"><Features><Polyline><PolyBegin x="0" y="4"/><PolyStepSegment x="1" y="4"/><LineDescRef id="ROUND_500"/></Polyline></Features></Set>
          </LayerFeature>
          <LayerFeature layerRef="LAYER2">
            <Set net="GND"><Features><Contour><Polygon><PolyBegin x="0" y="0"/><PolyStepSegment x="5" y="0"/><FillDescRef id="SOLID_FILL"/></Polygon><Cutout><PolyBegin x="1" y="1"/><PolyStepSegment x="2" y="1"/></Cutout></Contour></Features></Set>
            <Set net="GND"><Features><Contour><Polygon><PolyBegin x="0" y="2"/><PolyStepSegment x="5" y="2"/><FillDescRef id="SOLID_FILL"/></Polygon><Cutout><PolyBegin x="1" y="2"/><PolyStepSegment x="2" y="2"/></Cutout></Contour></Features></Set>
            <Set net="GND"><Features><Contour><Polygon><PolyBegin x="0" y="3"/><PolyStepSegment x="5" y="3"/><FillDescRef id="SOLID_FILL"/></Polygon><Cutout><PolyBegin x="1" y="3"/><PolyStepSegment x="2" y="3"/></Cutout></Contour></Features></Set>
          </LayerFeature>
        </IPC-2581>"""
    )
    out = tmp_path / "out"
    r = run(["python3", "thomson_bundle_converter.py", str(proj), "--output-root", str(out), "--pretty"], root)
    assert r.returncode == 0
    brd = json.loads((out / "proj-thomson-export-brd.json").read_text())
    review = brd["review_geometry_summary"]
    assert review["geometry_review_limitations"]
    assert any(n["net"] == "CAN_RX" and "TOP" in n["layers"] for n in review["net_layer_presence"])
    assert any(p["net"] == "GND" for p in review["plane_candidates"])
    assert any({"XY2_CLK_POS", "XY2_CLK_NEG"} == set(p["pair"]) or {"CAN_HI", "CAN_LO"} == set(p["pair"]) for p in review["candidate_differential_or_paired_nets"])
    assert "copper_feature_summary_rows" in brd
    assert "board_feature_summary_rows" in brd
    assert brd["routing_geometry"]["routes"]
    assert brd["routing_geometry"]["polygons"]
    assert brd["routing_geometry"]["pads"]
    assert brd["routing_geometry"]["cutouts"]
    can_rx_route = next(r for r in brd["routing_geometry"]["routes"] if r["net"] == "CAN_RX")
    assert can_rx_route["length"] > 0
    assert can_rx_route["length_units"] == "INCH"
    assert can_rx_route["length_is_estimated"] is False
    assert can_rx_route["segment_count"] == 1
    assert can_rx_route["curve_count"] == 0
    assert brd["routing_geometry_extraction"]["normalized_route_count"] == 5
    assert brd["routing_geometry_extraction"]["dropped_or_unparsed_feature_count"] == 0
    assert any(d["id"] == "ROUND_500" and d["width"] == 0.005 for d in brd["line_descriptors"])
    assert any(d["id"] == "SOLID_FILL" and d["fill_type"] == "solid" for d in brd["fill_descriptors"])
    can_rx = next(n for n in review["net_routing_summary"] if n["net"] == "CAN_RX")
    assert can_rx["route_count"] > 0
    assert "ROUND_500" in can_rx["line_desc_refs"]
    topology = brd["routing_topology_summary"]
    assert topology["nets"]
    assert topology["trace_width_by_net"]
    assert topology["trace_width_usage_by_layer"]
    assert topology["route_length_by_net"]
    assert topology["route_length_by_layer"]
    topo_can_rx = next(n for n in topology["nets"] if n["net"] == "CAN_RX")
    assert topo_can_rx["route_count"] > 0
    assert topo_can_rx["min_trace_width"] == 0.005
    assert topo_can_rx["max_trace_width"] == 0.005
    assert topo_can_rx["is_routing_candidate"] is True
    assert any("route/polyline on TOP" in e for e in topo_can_rx["geometry_evidence"])
    can_rx_trace = next(t for t in topology["trace_width_by_net"] if t["net"] == "CAN_RX")
    assert "ROUND_500" in can_rx_trace["line_desc_refs"]
    assert can_rx_trace["min_trace_width"] == 0.005
    assert can_rx_trace["max_trace_width"] == 0.005
    assert can_rx_trace["route_count"] > 0
    assert "TOP" in can_rx_trace["layers"]
    can_rx_length = next(t for t in topology["route_length_by_net"] if t["net"] == "CAN_RX")
    assert can_rx_length["total_route_length"] > 0
    assert can_rx_length["length_units"] == "INCH"
    assert can_rx_length["route_count"] == 1
    assert can_rx_length["length_is_estimated"] is False
    assert any(t["layer"] == "TOP" and t["total_route_length"] > 0 for t in topology["route_length_by_layer"])
    can_pair = next(p for p in topology["paired_net_geometry_comparison"] if set(p["pair"]) == {"CAN_HI", "CAN_LO"})
    assert "route_length_delta" in can_pair["comparison"]
    assert can_pair["comparison"]["route_length_delta_units"] == "INCH"
    assert any(c["net"] == "GND" for c in topology["layer_transition_candidates"]) is False
    assert any(t["net"] == "CAN_RX" and t["route_count"] > 0 for t in brd["trace_width_by_net"])
    assert any(t["layer"] == "TOP" and t["line_desc_ref"] == "ROUND_500" for t in brd["trace_width_usage_by_layer"])
    assert any(t["net"] == "CAN_RX" and t["total_route_length"] > 0 for t in brd["route_length_by_net"])
    assert any(t["layer"] == "TOP" and t["total_route_length"] > 0 for t in brd["route_length_by_layer"])
    assert any("No true DRC" in w for w in topology["routing_evidence_warnings"])
    assert brd["extraction_counts"]["route_segment_count"] == 0
    assert len(brd["routing_geometry"]["routes"]) > 0
    plane_nets = {p["net"] for p in review["plane_candidates"]}
    assert "CAN_HI" not in plane_nets
    assert "CAN_LO" not in plane_nets
    pair_sets = [set(p["pair"]) for p in review["candidate_differential_or_paired_nets"]]
    assert {"CAN_HI", "CAN_LO"} in pair_sets

    report = json.loads((out / "proj-conversion-report.json").read_text())
    ipc_report = report["ipc2581"]
    assert ipc_report["copper_feature_extraction_enabled"] is True
    assert ipc_report["layerfeature_count"] == 2
    assert ipc_report["set_count"] == 8
    assert ipc_report["polyline_object_count"] == 5
    assert ipc_report["polygon_object_count"] == 3
    assert ipc_report["pad_object_count"] == 1
    assert ipc_report["cutout_object_count"] == 3
    assert ipc_report["detailed_geometry_truncated"] is False
    assert ipc_report["routing_topology_summary_enabled"] is True
    assert ipc_report["routed_net_count"] >= 1
    assert ipc_report["paired_net_geometry_comparison_count"] >= 1
    assert ipc_report["trace_width_by_net_count"] == len(topology["trace_width_by_net"])
    assert ipc_report["trace_width_usage_by_layer_count"] == len(topology["trace_width_usage_by_layer"])
    assert ipc_report["route_length_summary_enabled"] is True
    assert ipc_report["route_length_by_net_count"] == len(topology["route_length_by_net"])
    assert ipc_report["route_length_by_layer_count"] == len(topology["route_length_by_layer"])
    assert ipc_report["routes_with_length_count"] == len(brd["routing_geometry"]["routes"])
    assert ipc_report["paired_net_length_comparison_count"] == len([p for p in topology["paired_net_geometry_comparison"] if p["comparison"].get("route_length_delta") is not None])
    assert ipc_report["routing_evidence_warning_count"] >= 1


def test_phase611_real_examples_routing_geometry_if_present(tmp_path):
    root = Path(__file__).resolve().parents[1]
    examples = root / "examples"
    if not examples.exists():
        return
    out = tmp_path / "out"
    r = run(["python3", "thomson_bundle_converter.py", str(examples), "--project-name", "example", "--output-root", str(out), "--pretty"], root)
    assert r.returncode == 0
    brd = json.loads((out / "example-thomson-export-brd.json").read_text())
    routing = brd["routing_geometry"]
    review = brd["review_geometry_summary"]
    assert routing["routes"]
    assert routing["copper_routes"]
    assert routing["non_copper_polylines"]
    assert len(routing["copper_routes"]) + len(routing["non_copper_polylines"]) == len(routing["routes"])
    assert routing["copper_polygons"]
    assert routing["non_copper_polygons"]
    assert routing["copper_pads"]
    assert routing["non_copper_pads"]
    assert routing["route_counts_by_domain"]
    assert routing["route_counts_by_layer_function"]
    assert any(r.get("length", 0) > 0 for r in routing["routes"])
    assert routing["polygons"]
    assert routing["pads"]
    assert brd["drill_hole_summary"]
    assert brd["holes"]
    assert brd["via_holes"]
    assert len(brd["holes"]) == brd["drill_hole_summary"]["total_holes"]
    assert len(brd["via_holes"]) == brd["drill_hole_summary"]["via_holes"]
    assert brd["pad_primitives"]
    assert any(p["shape"] == "circle" for p in brd["pad_primitives"])
    assert any(p["shape"] == "rect_center" for p in brd["pad_primitives"])
    assert any(p.get("primitive_resolution_status") == "resolved" for p in routing["pads"])
    assert brd["package_geometry_summary"]["package_count"] > 0
    assert brd["package_geometry_summary"]["landpattern_pad_count"] > 0
    assert brd["package_land_patterns"]
    assert brd["stackup_data_quality"]["material_thickness_available"] is False
    assert brd["stackup_data_quality"]["impedance_rules_available"] is False
    assert brd["routing_geometry_extraction"]["dropped_or_unparsed_feature_count"] == 0
    assert brd["line_descriptors"]
    assert any(d["id"] == "ROUND_500" for d in brd["line_descriptors"])
    can_rx = next(n for n in review["net_routing_summary"] if n["net"] == "CAN_RX")
    assert can_rx["route_count"] > 0
    assert "ROUND_500" in can_rx["line_desc_refs"]
    topology = brd["routing_topology_summary"]
    assert topology["trace_width_by_net"]
    assert topology["trace_width_usage_by_layer"]
    assert topology["route_length_by_net"]
    assert topology["route_length_by_layer"]
    assert topology["via_hole_by_net"]
    topo_can_rx = next(n for n in topology["nets"] if n["net"] == "CAN_RX")
    assert topo_can_rx["route_count"] > 0
    assert topo_can_rx["min_trace_width"] is not None
    assert topo_can_rx["max_trace_width"] is not None
    can_rx_trace = next(t for t in topology["trace_width_by_net"] if t["net"] == "CAN_RX")
    assert "ROUND_500" in can_rx_trace["line_desc_refs"]
    assert can_rx_trace["min_trace_width"] == 0.005
    assert can_rx_trace["max_trace_width"] == 0.005
    can_rx_route = next(r for r in routing["routes"] if r["net"] == "CAN_RX")
    assert can_rx_route["length"] > 0
    can_rx_length = next(t for t in topology["route_length_by_net"] if t["net"] == "CAN_RX")
    assert can_rx_length["total_route_length"] > 0
    assert can_rx_length["length_units"] == "INCH"
    assert any(t["total_route_length"] > 0 for t in topology["route_length_by_layer"])
    can_pair = next(p for p in topology["paired_net_geometry_comparison"] if set(p["pair"]) == {"CAN_HI", "CAN_LO"})
    assert "route_length_delta" in can_pair["comparison"]
    assert any(c["net"] == "GND" for c in topology["layer_transition_candidates"])
    assert any(c["net"] == "GND" and c["via_hole_count"] > 0 for c in topology["via_hole_by_net"])
    assert any(t["net"] == "CAN_RX" for t in brd["trace_width_by_net"])
    assert any("Geometry comes from IPC-2581" in w for w in topology["routing_evidence_warnings"])
    assert any("Non-copper drawing geometry is separated" in w for w in topology["routing_evidence_warnings"])
    assert any("Hole/via evidence is normalized" in w for w in topology["routing_evidence_warnings"])
    assert any("Pad primitive dimensions are parsed" in w for w in topology["routing_evidence_warnings"])
    assert any("Package/library geometry is summarized" in w for w in topology["routing_evidence_warnings"])
    assert brd["extraction_counts"]["route_segment_count"] == 0
    assert len(routing["routes"]) > 0
    plane_nets = {p["net"] for p in review["plane_candidates"]}
    assert "GND" in plane_nets
    assert ("V3P3" in plane_nets) or ("V5P0" in plane_nets)
    assert "CAN_HI" not in plane_nets
    assert "CAN_LO" not in plane_nets
    assert "AUXSPI_CLK" not in plane_nets
    pair_sets = [set(p["pair"]) for p in review["candidate_differential_or_paired_nets"]]
    assert {"CAN_HI", "CAN_LO"} in pair_sets
    assert brd["geometry_review_limitations"]

    report = json.loads((out / "example-conversion-report.json").read_text())
    ipc_report = report["ipc2581"]
    assert ipc_report["copper_route_count"] == len(routing["copper_routes"])
    assert ipc_report["non_copper_polyline_count"] == len(routing["non_copper_polylines"])
    assert ipc_report["copper_polygon_count"] == len(routing["copper_polygons"])
    assert ipc_report["non_copper_polygon_count"] == len(routing["non_copper_polygons"])
    assert ipc_report["copper_pad_count"] == len(routing["copper_pads"])
    assert ipc_report["non_copper_pad_count"] == len(routing["non_copper_pads"])
    assert ipc_report["hole_count"] == len(brd["holes"])
    assert ipc_report["via_hole_count"] == len(brd["via_holes"])
    assert ipc_report["plated_hole_count"] == len(brd["plated_holes"])
    assert ipc_report["nonplated_hole_count"] == len(brd["nonplated_holes"])
    assert ipc_report["pad_primitive_count"] == len(brd["pad_primitives"])
    assert ipc_report["resolved_pad_primitive_count"] == len([p for p in routing["pads"] if p.get("primitive_resolution_status") == "resolved"])
    assert ipc_report["unresolved_pad_primitive_count"] == len([p for p in routing["pads"] if p.get("primitive_resolution_status") == "unresolved"])
    assert ipc_report["package_geometry_summary_enabled"] is True
    assert ipc_report["package_count"] == brd["package_geometry_summary"]["package_count"]
    assert ipc_report["package_landpattern_pad_count"] == brd["package_geometry_summary"]["landpattern_pad_count"]
    assert ipc_report["stackup_data_quality_available"] is True
    assert ipc_report["trace_width_by_net_count"] == len(topology["trace_width_by_net"])
    assert ipc_report["trace_width_usage_by_layer_count"] == len(topology["trace_width_usage_by_layer"])
    assert ipc_report["route_length_summary_enabled"] is True
    assert ipc_report["route_length_by_net_count"] == len(topology["route_length_by_net"])
    assert ipc_report["route_length_by_layer_count"] == len(topology["route_length_by_layer"])
    assert ipc_report["routes_with_length_count"] == len(routing["routes"])
    assert ipc_report["paired_net_length_comparison_count"] == len([p for p in topology["paired_net_geometry_comparison"] if p["comparison"].get("route_length_delta") is not None])


def test_phase66_pads_multinode_line_and_numbered_mfg_headers(tmp_path):
    root = Path(__file__).resolve().parents[1]
    proj = tmp_path / "proj"
    (proj / "pre_conversion" / "schematic").mkdir(parents=True)
    (proj / "pre_conversion" / "layout").mkdir(parents=True)
    (proj / "pre_conversion" / "schematic" / "net.asc").write_text(
        "*PADS-PCB*\n*PART*\nJ3 footprint\nJ27 footprint\n*NET*\n*SIGNAL* ABORT_NEG\nJ3.41 J27.30\n"
    )
    (proj / "pre_conversion" / "schematic" / "bom.csv").write_text(
        "RefDes,MFG_1,MFG P/N_1\nJ3,Murata,ABC123\nJ27,AVX,XYZ999\n"
    )
    (proj / "pre_conversion" / "layout" / "i.xml").write_text("<IPC-2581/>")
    out = tmp_path / "out"
    r = run(["python3", "thomson_bundle_converter.py", str(proj), "--output-root", str(out)], root)
    assert r.returncode == 0
    sch = json.loads((out / "proj-thomson-export-sch.json").read_text())
    net = {n["name"]: n for n in sch["nets"]}["ABORT_NEG"]
    assert net["node_count"] == 2
    refs = {n["refdes"] for n in net["nodes"]}
    assert {"J3", "J27"} <= refs
    bom = json.loads((out / "proj-bom.json").read_text())
    first = bom["items"][0]
    assert first["fields"]["manufacturer"] is not None
    assert first["fields"]["mpn"] is not None
