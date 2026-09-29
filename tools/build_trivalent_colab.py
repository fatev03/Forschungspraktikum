"""Build the single-file Colab deliverable from the inspectable local modules."""
import base64, hashlib, io, json, textwrap, zipfile
from pathlib import Path
import nbformat as nbf
ROOT=Path(__file__).resolve().parents[1]
files=list((ROOT/'trivalent_pipeline').glob('*.py'))+list((ROOT/'avidity_sim/avidity').glob('*.py'))
files += [p for p in (ROOT/'src/structure_audit').rglob('*') if p.suffix in ('.py','.json') and '__pycache__' not in p.parts]
buf=io.BytesIO()
with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(files):
        info=zipfile.ZipInfo(p.relative_to(ROOT).as_posix(),date_time=(2026,9,29,0,0,0))
        info.compress_type=zipfile.ZIP_DEFLATED
        z.writestr(info,p.read_bytes())
blob=buf.getvalue();sha=hashlib.sha256(blob).hexdigest()
enc='\n'.join(textwrap.wrap(base64.b64encode(blob).decode(),100))
cells=[]
def md(s):cells.append(nbf.v4.new_markdown_cell(textwrap.dedent(s).strip()))
def code(s,cid):
    c=nbf.v4.new_code_cell(textwrap.dedent(s).strip());c['id']=cid;cells.append(c)
md('''
# Üç reseptör · tek zincirde üç binder

**Akış:** üç hedefi tanımla → her hedef için RFdiffusion / ProteinMPNN / AlphaFold adayı üret veya kendi kompleksini yükle → üç binder'ı tek aminoasit dizisinde birleştir → tam kaseti tekrar katla → geometriyi incele → yeterli girdiler varsa termodinamik senaryo hesapla.

Hem **B1–linker–B2–linker–B3** hem **B1–B2–B3** desteklenir. Her hedeften bir bağlanma kolu vardır: toplam valans **3**. Reseptör adları kullanıcı girdisidir; belirli üç reseptöre özel hesap yoktur. Bu sürüm **AA20 protein reseptör konstrüktleri** içindir; çok alt birimli hedefler, modifiye proteinler veya protein dışı hedefler için otomatik tasarım desteği iddia etmez.

1. Colab'de GPU çalışma zamanı seç. **Hedefler ve ayarlar** hücresindeki üç girişin dosyalarını, tam konstrükt dizilerini ve hotspot'larını doldur.
2. Gerçek ikili komplekslerin varsa `mode="import"` kullan; RFdiffusion gerekmez. AF3-ReD, AF3, Boltz ve deneysel PDB/mmCIF çıktıları açık zincir eşlemesiyle alınabilir.
3. Hücreleri sırayla çalıştır. İlk GPU kurulumunda büyük ağırlık dosyaları indirilir. Model tahminleri GPU süresi gerektirir; mevcut örnekleme sayısı bir başarı garantisi değildir.
4. Son ZIP'te FASTA, AlphaFold Server JSON, yerel AF3 JSON, Boltz girdileri, kaynak kompleksler, alınmış tahmin CIF'leri ve PyMOL betiği bulunur.

**Çıktı anlamı:** bunlar hesaplamalı adaylardır. Bağlanma, üçlü eşzamanlı işgal, hücre seçiciliği, agonizm/antagonizm, ekspresyon ve güvenlik deneysel olarak doğrulanmış sayılmaz. Model güven skorları afinite değildir. Eksik sonuçlar demo değerleriyle doldurulmaz.
''')
code('''
#@title CPU bağımlılıkları
import importlib.util, subprocess, sys
packages={"numpy":"numpy", "scipy":"scipy", "pandas":"pandas", "Bio":"biopython", "matplotlib":"matplotlib"}
missing=[pkg for mod,pkg in packages.items() if importlib.util.find_spec(mod) is None]
if missing:
    subprocess.run([sys.executable,"-m","pip","install","-q",*missing],check=True)
print("CPU dependencies ready. GPU tools use separate environments.")
''','cpu-dependencies')
bootstrap='''
#@title Paketli proje kodlarını aç
# Snapshot contains source code and schemas, no protein candidates or synthetic results.
import base64, hashlib, io, os, sys, tempfile, zipfile
from pathlib import Path
BUNDLE_SHA256="__SHA__"
BUNDLE_BASE64="""__ENC__"""
blob=base64.b64decode(BUNDLE_BASE64)
assert hashlib.sha256(blob).hexdigest()==BUNDLE_SHA256, "Notebook payload is corrupt"
base=Path("/content") if Path("/content").is_dir() else Path(tempfile.gettempdir())
PACKAGE_ROOT=(base/("trivalent_code_"+BUNDLE_SHA256[:12])).resolve()
with zipfile.ZipFile(io.BytesIO(blob)) as z:
    for name in z.namelist():
        dest=(PACKAGE_ROOT/name).resolve()
        if not dest.is_relative_to(PACKAGE_ROOT.resolve()): raise ValueError("Unsafe payload path")
        data=z.read(name)
        if dest.exists() and dest.read_bytes()!=data: raise RuntimeError("Existing source differs: "+str(dest))
        dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists(): dest.write_bytes(data)
for p in (PACKAGE_ROOT,PACKAGE_ROOT/"src",PACKAGE_ROOT/"avidity_sim"):
    if str(p) not in sys.path: sys.path.insert(0,str(p))
import trivalent_pipeline
if Path(trivalent_pipeline.__file__).resolve().parent != PACKAGE_ROOT/"trivalent_pipeline":
    raise RuntimeError("Another package version is loaded; restart the runtime.")
from trivalent_pipeline.core import *
from trivalent_pipeline.runtime import validate_target_specs, setup_gpu, obtain_arms, predict_boltz
from trivalent_pipeline.export import export_variant, import_prediction
from trivalent_pipeline.thermo import evaluate_scenario
print("Loaded source snapshot",BUNDLE_SHA256[:12])
'''.replace('__SHA__',sha).replace('__ENC__',enc)
code(bootstrap,'embedded-source');cells[-1]['metadata']['cellView']='form'
md('''
## 1. Hedefler ve ayarlar

`target_sequence`: kullandığın **tam konstrüktün** dizisi; örneğin tam reseptör değil yalnızca ECD kullanıyorsan o ECD dizisi. Yapıda eksik rezidü varsa otomatik birleştirme yapılmaz. `hotspot_positions` bu diziye göre **1 tabanlı** konumlardır; PDB numaralarıyla karıştırma. Yeniden numaralama haritası çıktı olarak saklanır.

`design`: reseptör dosyası ve hotspot'larla yeni binder üretir. `import`: bir hedef–binder kompleksinden, açıkça verdiğin zincir ve dizilerle binder alır. Aynı çalışmada modlar karıştırılabilir. İçe aktarma bir yapının doğru bağlandığını kanıtlamaz; protein kimliği, temas ve kaba çakışmalar kontrol edilir.

**Biyolojik bağlam:** membran/çözelti konumunu, glikan ve kofaktör bilgisini, konstrüktün sınırlarını ve amaçlanan işlevi `biological_context` içinde kaydet. Bilinmeyen, yok anlamına gelmez. Bu bilgiler mevcut geometri modelinde otomatik bir serbest enerji düzeltmesine çevrilmez.
''')
code('''
#@title Üç hedef ve çalışma seçenekleri — BURAYI DOLDUR
TARGETS=[
    {"target_id": f"R{i}", "mode":"design",
     "target_path":f"/content/inputs/receptor{i}.pdb", "target_chain":"A",
     "target_sequence":"", "binder_length":70, "hotspot_positions":[],
     "pair_path":"", "binder_chain":"B", "binder_sequence":"",
     "provider":"external", "model_index":None,
     "biological_context":{"location":"unknown", "construct_scope":"user_supplied",
                            "glycan_status":"unknown", "cofactors":"unknown",
                            "functional_goal":"binding_only", "assay_pH":None, "ionic_strength_M":None}}
    for i in (1,2,3)
]
# Import mode example (replace placeholders with real files/sequences):
# TARGETS[0].update(mode="import", pair_path="/content/pair1.cif",
#                  target_chain="A", binder_chain="B", target_sequence="...",
#                  binder_sequence="...", provider="AF3-ReD")
CONNECTIONS=[
    {"name":"GS20", "linkers":["GGGGS"*4,"GGGGS"*4]},
    {"name":"direct", "linkers":["",""]}
]
ALL_SIX_DOMAIN_ORDERS=False  # True exports 12 variants with the two connection choices.
RUN_GPU_SETUP=True
RUN_BOLTZ=True              # False: export for external AF3/AF3-ReD instead.
FOLD_VARIANT_INDICES=[0,1]   # Indices in the printed variant list, not a biological ranking.
BOLTZ_SAMPLES=1             # Increase for structural sampling; one sample cannot establish robustness.
SETTINGS={"num_designs":2,"num_sequences":8,"diffusion_steps":50,"af_recycles":3,
          "mpnn_temperature":0.1,"exclude_amino_acids":"",
          "screens":{"min_plddt":0.8,"min_iptm":0.6,"max_ipae_A":10.,"max_rmsd_A":2.5}}
# Above thresholds are configurable computational screens, not universal biological cutoffs.
SPACING_GRID_NM=[5.,8.,10.,15.,20.,30.]
WORK_BASE=base/"trivalent_runs"
GPU_TOOLS_ROOT=base/"trivalent_gpu_tools"
AF3RED_OUTPUT_ROOT=""       # Optional existing AF3-ReD output directory for provenance inventory.
EXTERNAL_PREDICTIONS=[]
# After the variant table is available, examples:
# EXTERNAL_PREDICTIONS=[{"variant_index":0,"path":"/content/joint.cif","role":"joint",
#   "chain_map":{"cassette":"D","R1":"A","R2":"B","R3":"C"},
#   "provider":"AF3-ReD","model_index":None,"membrane":None}]
# A membrane declaration is in the SAME coordinate frame as that prediction:
# {"point_A":[0,0,0],"normal":[0,0,1],"source_note":"how the plane was established"}
''','configuration')
code('''
#@title Girdileri kontrol et; yeni çalışma klasörünü oluştur
import json, uuid, datetime
READY=False; RUN_ROOT=None; ARMS=[]; VARIANTS=[]; VARIANT_DIRS=[]; PREDICTION_REPORTS=[]; ENVIRONMENT=None
try:
    validate_target_specs(TARGETS)
except (ValueError,KeyError,TypeError) as exc:
    print("INPUT_REQUIRED:",exc)
    print("Fill the three target records above and rerun from this cell. No demo is substituted.")
else:
    READY=True
    RUN_ROOT=Path(WORK_BASE)/(datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8])
    RUN_ROOT.mkdir(parents=True)
    write_json(RUN_ROOT/"run_config.json",{"targets":TARGETS,"connections":CONNECTIONS,"settings":SETTINGS,
                "all_domain_orders":ALL_SIX_DOMAIN_ORDERS,"source_bundle_sha256":BUNDLE_SHA256,
                "boltz_samples":BOLTZ_SAMPLES,"fold_variant_indices":FOLD_VARIANT_INDICES})
    print("Run directory:",RUN_ROOT)
''','preflight')
md('''
## 2. İsteğe bağlı AF3-ReD dış çıktı kaydı
Mevcut entegrasyon, orijinal dosyaların kaynak kimliğini ve okunabilirliğini kaydeder. `candidate` veya `admitted` durumu biyolojik kabul anlamına gelmez. İkili kompleks için `TARGETS`, birleşik tahmin için `EXTERNAL_PREDICTIONS` içinde dosyayı ve zincirleri açıkça seç.
''')
code('''
#@title AF3-ReD provenance envanteri (isteğe bağlı, çıkarım çalıştırmaz)
AF3RED_INVENTORY=None
if AF3RED_OUTPUT_ROOT:
    from structure_audit.af3_red_adapter import build_red_manifest
    AF3RED_INVENTORY=build_red_manifest(AF3RED_OUTPUT_ROOT,profile="af3_native_v1")
    print("Runs:",len(AF3RED_INVENTORY["runs"]),"artifacts:",len(AF3RED_INVENTORY["artifacts"]))
    print("Diagnostics:",AF3RED_INVENTORY["diagnostics"])
    if RUN_ROOT: write_json(RUN_ROOT/"af3red_inventory.json",AF3RED_INVENTORY)
else:
    print("No external AF3-ReD directory declared; inventory skipped.")
''','af3red-inventory')
code('''
#@title GPU araçlarını kur — ilk çalıştırmada büyük indirmeler
if READY and RUN_GPU_SETUP and (any(t["mode"]=="design" for t in TARGETS) or RUN_BOLTZ):
    ENVIRONMENT=setup_gpu(GPU_TOOLS_ROOT,design=any(t["mode"]=="design" for t in TARGETS),boltz=RUN_BOLTZ)
    write_json(RUN_ROOT/"environment.json",ENVIRONMENT)
elif READY and (any(t["mode"]=="design" for t in TARGETS) or RUN_BOLTZ):
    env_path=Path(GPU_TOOLS_ROOT)/"environment.json"
    if not env_path.is_file(): raise RuntimeError("Enable RUN_GPU_SETUP or supply an existing environment.")
    ENVIRONMENT=json.loads(env_path.read_text())
else:
    print("GPU setup not required for empty inputs / import-only CPU mode.")
if READY and ENVIRONMENT:
    import shutil
    env_report=RUN_ROOT/"environment_details";env_report.mkdir(exist_ok=True)
    write_json(env_report/"runtime.json",{"python":sys.version,"environment":ENVIRONMENT})
    for path in Path(ENVIRONMENT["root"]).glob("*freeze.txt"):
        shutil.copy2(path,env_report/path.name)
''','gpu-setup')
md('''
## 3. Üç ikili adayı üret veya içe aktar
Her hedef bağımsız tasarlanır. ProteinMPNN dizileri AlphaFold ile yeniden tahmin edilir. Eşikler arayüz deneyinin yerine geçmez. Hiçbir aday geçmezse ilgili hedefte işlem durur; düşük güvenli bir “en iyi” aday sessizce kullanılmaz. Ayrı dizilerin iyi görünmesi, füzyonun da iyi katlanacağı anlamına gelmediğinden bir sonraki aşamada tam kaset yeniden modellenir.
''')
code('''
#@title Adayları hazırla ve geometri/kimlik kontrollerini yap
import pandas as pd
if READY:
    ARMS=obtain_arms(TARGETS,ENVIRONMENT,RUN_ROOT,SETTINGS)
    write_json(RUN_ROOT/"arms.json",ARMS)
    display(pd.DataFrame([{k:a[k] for k in ("target_id","candidate_id","screen_state","interface_CA_count","severe_close_atom_pairs")} for a in ARMS]))
    if any(a["screen_state"]!="GEOMETRY_CANDIDATE" for a in ARMS):
        raise RuntimeError("Repair or replace no-interface/clashing complexes before assembly.")
else:
    print("Waiting for complete target inputs.")
''','obtain-arms')
md('''
## 4. Tek zincirde kaset oluştur ve biyokimyasal özellikleri raporla
Linker dizileri gerçekten nihai aminoasit dizisine eklenir; doğrudan füzyonda iki domain arada rezidü olmadan birleşir. Net yük, pI, GRAVY, sisteinler ve N-glikozilasyon motifleri **betimleyici** ölçülerdir. Motif bulunması glikozilasyon oluşacağını, düşük GRAVY çözünürlüğü veya ekspresyonu kanıtlamaz. Birleşme noktalarında yeni oluşan motifler de tam dizi üzerinde görünür.
''')
code('''
#@title Kasetleri ve protein özelliklerini oluştur
if ARMS:
    VARIANTS=build_cassettes(ARMS,CONNECTIONS,ALL_SIX_DOMAIN_ORDERS)
    for variant in VARIANTS:
        VARIANT_DIRS.append(export_variant(variant,RUN_ROOT/"cassettes"))
    display(pd.DataFrame([{"index":i,"id":v["id"],"order":" -> ".join(v["order"]),
                          "connection":v["connection"],"length":len(v["sequence"]),
                          "pI":v["sequence_properties"]["theoretical_pI"],
                          "charge_pH7.4":v["sequence_properties"]["charge_at_pH"],
                          "glycan_sequons":v["sequence_properties"]["N_glycosylation_sequon_positions"]}
                         for i,v in enumerate(VARIANTS)]))
    print("FASTA and 14 folding/control jobs exported for each variant. List order is not ranking.")
else:
    print("No three-arm candidate set available.")
''','assemble-export')
code('''
#@title Reseptör aralığı için kaba uzunluk taraması
if VARIANTS:
    LENGTH_SCREENS=[]
    for v in VARIANTS:
        screen=spacing_screen(v["arms"],v["linkers"],SPACING_GRID_NM)
        LENGTH_SCREENS.append({"variant_id":v["id"],**screen})
    write_json(RUN_ROOT/"length_screens.json",LENGTH_SCREENS)
    display(pd.DataFrame([{**r,"variant_id":s["variant_id"]} for s in LENGTH_SCREENS for r in s["rows"]]))
    print("Length envelopes only. No Ceff, joint-binding verdict or cell-selectivity value is exported from these envelopes.")
''','length-screen')
md('''
## 5. Tam kaseti katla ve üç reseptörlü kompleksi incele
Varsayılan işler: kaset tek başına ve kaset + üç reseptör. **Kaset tek bir zincir olarak verilir**; üç binder ayrı ligand zincirleri olarak sunulmaz. Ek girdilerde her reseptörle tek tek kaset ve her domainin üç hedefe karşı çapraz kontrolleri bulunur. Çapraz kontrol yapıları özgüllük deneyinin yerine geçmez.

Boltz MSA sunucusu seçildiğinde reseptör dizileri dış sunucuya gönderilir. `RUN_BOLTZ=False` yaparak dosyaları dışarıda AF3/AF3-ReD ile çalıştırıp geri alabilirsin. AF3-ReD çıktı olması başlı başına fiziksel doğrulama değildir. Glikan/kofaktör/membran bilgisi olmayan sade protein girdisi bunları otomatik eklemez.
''')
code('''
#@title Boltz ile tam kaset tahminleri (isteğe bağlı GPU aşaması)
AUTO_PREDICTIONS=[]
if VARIANTS and RUN_BOLTZ:
    if len(set(FOLD_VARIANT_INDICES))!=len(FOLD_VARIANT_INDICES): raise ValueError("Duplicate fold indices")
    for index in FOLD_VARIANT_INDICES:
        if type(index)!=int or not 0<=index<len(VARIANTS): raise ValueError("Invalid variant index")
        paths=predict_boltz(ENVIRONMENT,VARIANT_DIRS[index],samples=BOLTZ_SAMPLES)
        for prediction in paths:
            path=prediction["path"];role=prediction["role"]
            chain_map={"cassette":"A"}
            if role=="joint": chain_map.update({target:chr(66+i) for i,target in enumerate(VARIANTS[index]["order"])})
            AUTO_PREDICTIONS.append({"variant_index":index,"path":path,"role":role,
                                     "chain_map":chain_map,"provider":"Boltz","model_index":None,"membrane":None})
else:
    print("Boltz skipped. Prediction inputs are available once variants are assembled.")
''','fold-cassettes')
code('''
#@title Tahmin dosyalarını al; zincir, füzyon ve ortak kompleks geometrisini denetle
PREDICTION_REPORTS=[]
for item in AUTO_PREDICTIONS+EXTERNAL_PREDICTIONS:
    index=item["variant_index"]
    if type(index)!=int or not 0<=index<len(VARIANTS): raise ValueError("Invalid external variant index")
    report=import_prediction(VARIANTS[index],VARIANT_DIRS[index],item["path"],item["chain_map"],
                             item.get("role","joint"),item.get("provider","external"),
                             item.get("model_index"),item.get("membrane"))
    PREDICTION_REPORTS.append({"variant_id":VARIANTS[index]["id"],**report})
if PREDICTION_REPORTS:
    display(pd.DataFrame([{"variant":r["variant_id"],"role":r["role"],"status":r["status"],
                          "findings":", ".join(r["reasons"])} for r in PREDICTION_REPORTS]))
    write_json(RUN_ROOT/"prediction_reports.json",PREDICTION_REPORTS)
else:
    print("No whole-cassette structure supplied. FASTA/AF3 inputs exist; no fused coordinates are invented.")
''','inspect-predictions')
md('''
## 6. Termodinamik: açık girdilerle, sabit reseptör kümesi senaryosu
Model, birer R1/R2/R3 içeren **sabit bir reseptör kümesini** ve serbest ligand rezervuarını ele alır. Boş durum, tek kasetin tekli/ikili/üçlü bağlanması ve farklı kaset moleküllerinin reseptörleri paylaşması dahil **15 düzen** hesaplanır. Böylece ilk Kd de sonucu etkiler; yüksek ligand derişiminde tekli işgalin köprülemeyle rekabeti mümkündür.

Model, füzyon sonrası domainlerin bağlanma yeteneğini koruduğunu ve verilen Kd'lerin bu koşullarda geçerli olduğunu varsayar. Çapraz bağlanma dahil değildir. Gerçek füzyon afiniteyi değiştirebilir; ayrı binder ölçümlerinin kasete taşınması açık bir varsayımdır.

Gerekli girdiler: her kolun Kd'si (M), ligand derişimi (M), aynı sıcaklık/ortam koşulları, J12/J13/J23 (M) ve J123 (M²). J13, arada bağlı olmayan orta domain varken kapanmayı temsil eder. Bunlar tahmin güven skorlarından veya en iyi mesafe sınırından türetilmez. Kd yoksa hesap yapılmaz. ΔG° = RT ln(Kd / 1 M), yalnızca verilen monovalent Kd'nin standart-durum dönüşümüdür.

İsteğe bağlı polimer hesabı **tek bir ortak tahmin koordinat sistemi** kullanır: sonlu kontur kesmesi, WLC momentlerine eşlenen ideal FJC segmentleri, J13 için serbest dönen orta domain çubuğu. J123=J12×J23 yalnızca bu açık ideal bağımsız-linker varsayımında kullanılır. Doğrudan/kısa füzyona bu yaklaşım uygulanmaz. Membran, glikan, bağlanma yönelimi ve dışlanan hacim Ceff integralinde bulunmadığından çıkan değerler biyolojik alt/üst sınır değildir.

Hücre yüzeyi seçiciliği burada hesaplanmaz: reseptörlerin aynı hücrede bulunması, yerel yoğunluk ve hareketlilik verileri olmadan sabit küme sonucu hücre popülasyonuna taşınmaz. Agonizm, antagonizm, internalizasyon, proteoliz ve immünojenisite için sonuç verilmez.
''')
code('''
#@title İsteğe bağlı ortak-yapı polimer senaryosu — varsayılan kapalı
RUN_IDEAL_LINKER_SCENARIO=False
IDEAL_VARIANT_INDEX=0
IDEAL_JOINT_PATH=""
IDEAL_CHAIN_MAP={}  # {"cassette":"A","R1":"B","R2":"C","R3":"D"}
IDEAL_MODEL_INDEX=None
PERSISTENCE_LENGTH_NM=0.5  # Assumed linker property; not calibrated from sequence.
IDEAL_CLOSURE=None
if RUN_IDEAL_LINKER_SCENARIO:
    from trivalent_pipeline.polymer import closure_from_joint
    IDEAL_CLOSURE=closure_from_joint(VARIANTS[IDEAL_VARIANT_INDEX],IDEAL_JOINT_PATH,IDEAL_CHAIN_MAP,
                                  persistence_nm=PERSISTENCE_LENGTH_NM,model_index=IDEAL_MODEL_INDEX)
    print(json.dumps(IDEAL_CLOSURE,indent=2))
    write_json(RUN_ROOT/"ideal_closure_scenario.json",IDEAL_CLOSURE)
''','ideal-closure')
code('''
#@title Kd ve termodinamik senaryo — yalnızca gerçek girdilerinle doldur
THERMODYNAMIC_SCENARIO=None
THERMO_VARIANT_INDEX=0
# Example schema only; do not copy numbers from the independent tests as measurements:
# THERMODYNAMIC_SCENARIO={
#   "variant_id":VARIANTS[0]["id"],"target_order":VARIANTS[0]["order"],
#   "evidence_kind":"model_scenario", "source_note":"Kd sources, construct, pH, salt and model assumptions",
#   "kd_M":[...,...,...],"temperature_K":298.15,"kd_temperature_K":298.15,
#   "closure_factors":{"12":...,"13":...,"23":...,"123":...},
#   "concentrations_M":[...]}
# If using IDEAL_CLOSURE, explicitly copy its closure_factors only after reading its assumptions.
THERMO_RESULT=None
if VARIANTS:
    THERMO_RESULT=evaluate_scenario(VARIANTS[THERMO_VARIANT_INDEX],THERMODYNAMIC_SCENARIO)
    write_json(RUN_ROOT/"thermodynamic_scenario.json",THERMO_RESULT)
    print("Thermodynamics:",THERMO_RESULT["status"])
    if THERMO_RESULT["status"]=="CONDITIONAL_MODEL_RESULT":
        rows=THERMO_RESULT["rows"]
        display(pd.DataFrame([{k:r[k] for k in ("concentration_M","p_any_ligand_bound","p_one_cassette_bridges_all_three","mean_cassettes_bound")} for r in rows]))
        import matplotlib.pyplot as plt
        x=[r["concentration_M"] for r in rows]
        fig,ax=plt.subplots(figsize=(7,4))
        ax.plot(x,[r["p_any_ligand_bound"] for r in rows],label="Any occupancy",color="#2459a6")
        ax.plot(x,[r["p_one_cassette_bridges_all_three"] for r in rows],label="One cassette bridges all 3",color="#b34b1e",linestyle="--")
        if all(v>0 for v in x): ax.set_xscale("log")
        ax.set(xlabel="Free cassette concentration (M)",ylabel="Probability per fixed receptor patch",ylim=(0,1.02),title="Conditional equilibrium scenario")
        ax.legend();fig.tight_layout();fig.savefig(RUN_ROOT/"thermodynamic_scenario.png",dpi=160);plt.show()
else:
    print("Thermodynamics unavailable: no cassette variant.")
''','thermodynamics')
md('''
## 6B. Yeni bilimsel verilerle avidite modelini kalibre et

Bu bölüm, veriler geldikçe **CSV'yi güncelleyip hücreyi tekrar çalıştırarak** seçtiğin parametreleri yeniden uydurur. İnternetten otomatik veri toplamaz. Her çalışmada tüm mevcut veriler yeniden değerlendirilir; önceki fit ayrıca veri/önsel olarak eklenip aynı kanıt iki kez sayılmaz. RFdiffusion'ı tekrar çalıştırmak gerekmez: daha sonra kaydettiğin `variant.json` ve başlangıç senaryosunu yükleyebilirsin.

**Girdiler:** kaynakları ve aynı koşulları belirtilmiş CSV + metadata JSON + teorik/önceki başlangıç senaryosu. CSV şablonu aşağıda üretilir. Kd ve J değerleri **M**, J123 **M²**, derişim **serbest ligand M** birimindedir. Kd ölçümleri, tek hedefli denge bağlanma fraksiyonları veya modelle uyumlu sabit üç-reseptör kümesinin işgal ölçümleri desteklenir. Sıradan hücre bağlanma sinyali, ham SPR/BLI, EC50, görünür Kd ve koff doğrudan bu modele eşitlenmez.

`sd`, sağladığın değerin standart hatasıdır; bir ortalama veriyorsan o ortalamanın standart hatasını kullan. Bağımsız, bilinen Gauss ölçüm hatası varsayılır. Korelasyonlu zaman serileri, aynı deneyden hem eğri hem türetilmiş Kd, sansürlü ölçümler veya belirsiz derişimler için ayrı hata modeli gerekir. Birimler otomatik tahmin edilmez.

`FIT_PARAMETERS` ile güncellenecek parametreleri seç; diğerleri sabit kalır. Veri olmadan bütün yedi parametreyi serbest bırakma. `PARAMETER_BOUNDS` sınırlarını bilimsel gerekçeyle belirle; sabit sıfır kapanma faktörü log uzayında uydurulamaz. Başlangıç senaryosuna, verilerin metadata dosyasındaki koşullarla gerçekten eşleşen `calibration_context` alanını ekle: sıcaklık, pH, iyonik güç, konstrükt açıklaması ve ortak geometri kimliği. Farklı koşullar ayrı kalibrasyon gerektirir.

CSV'deki `split=train` satırları parametreleri belirler. **Farklı deneylerden** `split=validation` satırları yalnız kontrol için kullanılır; bir deney iki grupta bulunamaz. Her kaynağı metadata `sources` alanında belirt. Yeni veri geldiğinde mevcut doğrulama grubunu sonuçlara bakarak yeniden seçme; tekrar tekrar bakılan bir grup nihai bağımsız doğrulama sayılmaz.

Otomatik kullanım ancak yerel parametre belirlenebilirliği, sınır/belirsizlik ve uyum kontrolleri geçerse; yeterli bağımsız doğrulama varsa ve bu grupta başlangıç modelinden kötüleşmiyorsa gerçekleşir. Aksi halde aday fit kaydedilir, aktif senaryo başlangıçta kalır. Aralıklar **yaklaşık yerel %95 Wald aralıklarıdır**; sabit parametrelerin belirsizliğini veya model hatasını kapsamaz, global belirlenebilirliği kanıtlamaz. Fitted J değerleri mevcut modele ait etkin kapanma faktörleridir; tek başına linker'ın fiziksel bir özelliği değildir.
''')
code('''
#@title Veriye göre kalibrasyon — veriler gelince ayarla ve yeniden çalıştır
import json
import pandas as pd
from trivalent_pipeline.calibration import calibrate_files, select_scenario, write_templates
RUN_CALIBRATION=False
AUTO_USE_CALIBRATION=True  # Only eligible fits with independent validation are used.
CALIBRATION_VARIANT_INDEX=0
CALIBRATION_VARIANT_FILE=""  # Later: path to saved cassette variant.json; GPU stages need not run.
CALIBRATION_BASELINE_FILE="" # Later: saved baseline_scenario.json, with calibration_context.
CALIBRATION_CSV="/content/avidity_measurements.csv"
CALIBRATION_METADATA_FILE="/content/avidity_metadata.json"
FIT_PARAMETERS=["J123_M2"]  # Options: kd_1_M, kd_2_M, kd_3_M, J12_M, J13_M, J23_M, J123_M2
PARAMETER_BOUNDS={}         # Fill for every fitted parameter: {parameter: [positive_lower, positive_upper]}.
CALIBRATION_STARTS=5
CALIBRATION_SEED=0
CALIBRATION_RESULT=None; CALIBRATION_DIR=None; CALIBRATED_THERMO_RESULT=None
CALIBRATION_VARIANT=None
_CAL_VARIANTS=globals().get("VARIANTS",[])
_CAL_PIPELINE_ROOT=globals().get("RUN_ROOT")
if CALIBRATION_VARIANT_FILE:
    CALIBRATION_VARIANT=json.loads(Path(CALIBRATION_VARIANT_FILE).read_text())
elif _CAL_VARIANTS:
    if type(CALIBRATION_VARIANT_INDEX)!=int or not 0<=CALIBRATION_VARIANT_INDEX<len(_CAL_VARIANTS):
        raise ValueError("Invalid calibration variant index")
    CALIBRATION_VARIANT=_CAL_VARIANTS[CALIBRATION_VARIANT_INDEX]
CALIBRATION_BASELINE=(json.loads(Path(CALIBRATION_BASELINE_FILE).read_text())
                      if CALIBRATION_BASELINE_FILE else globals().get("THERMODYNAMIC_SCENARIO"))
ACTIVE_THERMODYNAMIC_SCENARIO=CALIBRATION_BASELINE
CALIBRATION_HISTORY=(_CAL_PIPELINE_ROOT/"calibration_history" if _CAL_PIPELINE_ROOT else base/"trivalent_calibration_history")
if CALIBRATION_VARIANT:
    template_dir=(_CAL_PIPELINE_ROOT/"calibration_templates"/CALIBRATION_VARIANT["id"] if _CAL_PIPELINE_ROOT
                  else CALIBRATION_HISTORY/"templates"/CALIBRATION_VARIANT["id"])
    template_paths=write_templates(template_dir,CALIBRATION_VARIANT)
    print("Empty data templates:",*[str(p) for p in template_paths])
if RUN_CALIBRATION:
    if CALIBRATION_VARIANT is None or CALIBRATION_BASELINE is None:
        raise ValueError("Supply the exact variant and a baseline scenario before calibration.")
    CALIBRATION_RESULT,CALIBRATION_DIR=calibrate_files(
        CALIBRATION_VARIANT,CALIBRATION_BASELINE,CALIBRATION_CSV,CALIBRATION_METADATA_FILE,
        FIT_PARAMETERS,PARAMETER_BOUNDS,CALIBRATION_HISTORY,n_starts=CALIBRATION_STARTS,seed=CALIBRATION_SEED)
    ACTIVE_THERMODYNAMIC_SCENARIO=select_scenario(CALIBRATION_BASELINE,CALIBRATION_RESULT,AUTO_USE_CALIBRATION)
    CALIBRATED_THERMO_RESULT=evaluate_scenario(CALIBRATION_VARIANT,ACTIVE_THERMODYNAMIC_SCENARIO)
    write_json(CALIBRATION_DIR/"active_scenario.json",ACTIVE_THERMODYNAMIC_SCENARIO)
    write_json(CALIBRATION_DIR/"active_thermodynamic_result.json",CALIBRATED_THERMO_RESULT)
    print("Calibration:",CALIBRATION_RESULT["status"],"warnings:",CALIBRATION_RESULT["warnings"])
    print("Active model:","calibrated" if ACTIVE_THERMODYNAMIC_SCENARIO.get("calibration_id")==CALIBRATION_RESULT["calibration_id"] else "baseline")
    display(pd.DataFrame([{"parameter":n,"before":CALIBRATION_RESULT["initial_parameters"][n],
        "fitted":CALIBRATION_RESULT["fitted_parameters"][n],
        "local_95_interval":CALIBRATION_RESULT["intervals"].get(n,{}).get("approx_95_interval","unavailable")}
        for n in FIT_PARAMETERS]))
else:
    print("Calibration off: no fitted or experimental result is invented.")
''','adaptive-calibration')
code('''
#@title Kalibrasyon uyumu ve sürüm kaydı
if CALIBRATION_RESULT:
    import matplotlib.pyplot as plt
    from trivalent_pipeline.calibration import predict_observations, PATCH_OBSERVABLES, MONO_OBSERVABLES
    measured=pd.DataFrame(CALIBRATION_RESULT["predictions"])
    synthetic=CALIBRATION_RESULT["metadata"]["evidence_kind"]=="synthetic_test"
    figures=[]
    for observable,group in measured.groupby("observable",sort=False):
        fig,(ax,resax)=plt.subplots(2,1,figsize=(8,6),sharex=True,gridspec_kw={"height_ratios":[3,1]})
        is_curve=observable in PATCH_OBSERVABLES+MONO_OBSERVABLES
        group=group.copy();group["plot_x"]=group["concentration_M"] if is_curve else range(1,len(group)+1)
        for split,marker,color in [("train","o","#2459a6"),("validation","s","#b34b1e")]:
            part=group[group["split"]==split]
            if len(part):
                ax.errorbar(part["plot_x"],part["value"],yerr=part["sd"],fmt=marker,color=color,
                            label=split+" data (±1 SE)",capsize=3,markersize=5)
                resax.scatter(part["plot_x"],part["standardized_residual"],marker=marker,color=color,s=22)
        if is_curve:
            xmin,xmax=float(group["plot_x"].min()),float(group["plot_x"].max())
            grid=np.geomspace(xmin,xmax,160) if xmin>0 and xmax>xmin else np.linspace(xmin,xmax,160)
            grid_rows=[{"observable":observable,"concentration_M":float(c)} for c in grid]
            xlabel="Free cassette concentration (M)" if observable in PATCH_OBSERVABLES else "Free monovalent ligand concentration (M)"
            if xmin>0:ax.set_xscale("log")
        else:
            grid=group["plot_x"].to_numpy();grid_rows=group.to_dict("records");xlabel="Measurement index"
        for params,label,color,style in [(CALIBRATION_RESULT["initial_parameters"],"Baseline","#666666","--"),
                                        (CALIBRATION_RESULT["fitted_parameters"],"Candidate fit","#2459a6","-")]:
            y=predict_observations(params,grid_rows,CALIBRATION_BASELINE["temperature_K"])
            ax.plot(grid,y,label=label,color=color,linestyle=style)
        # Error bars are measurement uncertainty; fitted-parameter intervals are in the table above.
        ax.set_ylabel(observable);ax.legend(fontsize=9)
        ax.set_title(("SYNTHETIC SOFTWARE TEST — " if synthetic else "Conditional calibration — ")+observable,fontsize=11)
        resax.axhline(0,color="#555555",linewidth=.8)
        resax.set(xlabel=xlabel,ylabel="Residual / SE")
        fig.tight_layout();fig.savefig(CALIBRATION_DIR/("fit_"+observable+".png"),dpi=160);plt.show();figures.append(fig)
    print("Parameter intervals are local and conditional; plots do not include predictive uncertainty bands.")
    print("Saved new version:",CALIBRATION_DIR)
    import shutil
    CALIBRATION_ARCHIVE=shutil.make_archive(str(CALIBRATION_DIR),"zip",CALIBRATION_DIR)
    print("Calibration archive:",CALIBRATION_ARCHIVE)
    # Standalone later calibration also has a downloadable result, without rerunning the design pipeline.
    if not _CAL_PIPELINE_ROOT:
        try:
            from google.colab import files
            files.download(CALIBRATION_ARCHIVE)
        except ImportError: pass
''','calibration-results')
md('''
## 7. Sonuçları indir ve PyMOL/AlphaFold'da aç
ZIP'teki her kaset klasöründe `cassette.fasta`, `alphafold_server_jobs.json`, `prediction_inputs/`, `pair_models/` ve `predictions/` bulunur. **AlphaFold Server'a yüklenen dosya tahmin girdisidir.** PyMOL'da ZIP'i açtıktan sonra ilgili klasördeki `view_results.py` betiğini çalıştır veya `predictions/*.cif` dosyasını doğrudan aç. Kaynak ikili kompleksler farklı koordinat çerçevelerindedir; betik bunları ayrı, başlangıçta kapalı nesneler olarak tutar. İncelenmiş tam kaset CIF'lerinde üç binder farklı renktedir.

Varsa glikan/kofaktör atomları inceleme kopyasında korunur, ancak bu işlem kimyasal bağ topolojisini yeniden kurmaz; orijinal `.source.*` dosyaları da saklanır. Eksik glikanlar eklenmiş sayılmaz. Membran kontrolü yalnızca aynı koordinat çerçevesinde açık bir düzlem verdiğinde çalışır.
''')
code('''
#@title Sonuç paketi ve indirme
import shutil, hashlib
if RUN_ROOT and VARIANTS:
    files_before={str(p.relative_to(RUN_ROOT)):digest(p) for p in RUN_ROOT.rglob("*") if p.is_file()}
    write_json(RUN_ROOT/"output_manifest.json",{"files_sha256":files_before,"source_bundle":BUNDLE_SHA256,
              "scope":"candidate designs and explicitly labelled conditional analyses", "biological_validation":"not_established"})
    archive=shutil.make_archive(str(RUN_ROOT),"zip",RUN_ROOT)
    print("Results:",archive)
    try:
        from google.colab import files
        files.download(archive)
    except ImportError:
        print("Local run: open the archive path above.")
else:
    print("No real candidate export yet. Complete target inputs and rerun the pipeline.")
''','download')
md('''
## Yöntem kaynakları ve doğrulama kapsamı
- [RFdiffusion](https://github.com/RosettaCommons/RFdiffusion): hedefe koşullu omurga örnekleme.
- [ColabDesign](https://github.com/sokrypton/ColabDesign): ProteinMPNN ve AlphaFold tasarım incelemesi.
- [Boltz girdileri](https://github.com/jwohlwend/boltz/blob/main/docs/prediction.md).
- [AlphaFold Server JSON](https://github.com/google-deepmind/alphafold/tree/main/server) ve [yerel AF3 JSON](https://github.com/google-deepmind/alphafold3/blob/main/docs/input.md) farklı biçimlerdir; ikisi ayrı dışa aktarılır.
- [Sørensen–Kjaergaard 2019](https://pubmed.ncbi.nlm.nih.gov/31659043/): linker dizisi ve etkin derişim ilişkisi; evrensel bir linker sabiti varsayılmaz.
- [SciPy least_squares](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html) ve [kovaryans sınırları](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.curve_fit.html): sayısal uyum ve yerel belirsizlik yaklaşımı.
- [Raue ve arkadaşları 2009](https://pubmed.ncbi.nlm.nih.gov/19505944/): parametre belirlenebilirliği; buradaki yerel rank kontrolü tam profil-olabilirlik analizinin yerine geçmez.

Bu sürümün CPU kodu sentetik geometriler, bağımsız Langmuir limiti, olasılık normalizasyonu, ilk Kd duyarlılığı, yüksek doz rekabeti ve dosya kimliği kontrolleriyle sınanmıştır. Bu testler biyolojik başarı kanıtı değildir. Gerçek hedef dosyaları ve GPU tahminleri bu dosya hazırlanırken çalıştırılmamıştır; Colab kurulumu ve uçtan uca gerçek tasarım başarısı ayrıca doğrulanmalıdır. PyMOL betiğinin dosya yükleme/renklendirme akışı kontrol edilir; PyMOL uygulamasında görsel inceleme yapılmış sayılmaz.
''')
nb=nbf.v4.new_notebook(cells=cells,metadata={'kernelspec':{'name':'python3','display_name':'Python 3','language':'python'},
       'language_info':{'name':'python'},'accelerator':'GPU','colab':{'name':'diffusion_trivalent_adaptive_colab_2026-09-29.ipynb','provenance':[]}})
nbf.validate(nb)
path=ROOT/'diffusion_trivalent_adaptive_colab_2026-09-29.ipynb';nbf.write(nb,path)
print(path, 'cells',len(cells),'bundled files',len(files),'bytes',path.stat().st_size)
