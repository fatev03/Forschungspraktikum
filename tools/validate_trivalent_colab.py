"""Execute the delivered notebook in fresh kernels with empty and synthetic inputs.

Synthetic fixtures are stored only under the explicitly labelled validation report.
No fixture or computed synthetic result is written into the deliverable notebook.
"""
import copy, importlib.util, json, os, sys
from pathlib import Path
import nbformat
from nbclient import NotebookClient
from jupyter_client import KernelManager
from jupyter_client.kernelspec import KernelSpecManager

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
REPORT=ROOT/'reports/trivalent-adaptive-validation-20260929'
REPORT.mkdir(parents=True,exist_ok=True)
fixtures=REPORT/'synthetic_fixtures';fixtures.mkdir(exist_ok=True)
spec=importlib.util.spec_from_file_location('synthetic',ROOT/'tests/trivalent/test_pipeline.py')
test=importlib.util.module_from_spec(spec);spec.loader.exec_module(test)
cspec=importlib.util.spec_from_file_location('calibration_fixture',ROOT/'tests/trivalent/test_calibration.py')
ctest=importlib.util.module_from_spec(cspec);cspec.loader.exec_module(ctest)
arms=test.make_arms(fixtures)
variants=test.build_cassettes(arms,[{'name':'GS20','linkers':['GGGGS'*4]*2},{'name':'direct','linkers':['','']}])
cv,cb,cr,cm,_=ctest.fixture()
for data in (cb,cm):data.update(variant_id=variants[0]['id'],target_order=variants[0]['order'])
from trivalent_pipeline.calibration import write_templates, FIELDS
import csv
csvpath,metapath=write_templates(fixtures,variants[0]);metapath.write_text(json.dumps(cm))
baselinepath=fixtures/'baseline.json';baselinepath.write_text(json.dumps(cb))
variantpath=fixtures/'variant.json';variantpath.write_text(json.dumps(variants[0]))
with csvpath.open('w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader();writer.writerows(cr)
inputs=[]
for i,a in enumerate(arms):
    inputs.append({'target_id':a['target_id'],'mode':'import','pair_path':a['source']['path'],
        'target_chain':'A','binder_chain':'B','target_sequence':a['target_sequence'],
        'binder_sequence':a['binder_sequence'],'provider':'SYNTHETIC_SOFTWARE_TEST_ONLY'})
predictions=[]
for index,v in enumerate(variants):
    for role in ('cassette_alone','joint'):
        lines,serial=test.atom_rows(v['sequence'],'A')
        chain_map={'cassette':'A'}
        if role=='joint':
            regions=[r for r in v['regions'] if r['kind']=='binder']
            for j,(arm,region) in enumerate(zip(v['arms'],regions)):
                cid=chr(66+j);chain_map[arm['target_id']]=cid
                rows,serial=test.atom_rows(arm['target_sequence'],cid,-4.5,serial)
                offset=(region['start']-1)*3.8
                lines += [line[:30]+f'{float(line[30:38])+offset:8.3f}'+line[38:] for line in rows]
        p=fixtures/f'variant_{index}_{role}.pdb';p.write_text(''.join(lines)+'END\n')
        predictions.append({'variant_index':index,'path':str(p),'role':role,'chain_map':chain_map,
                            'provider':'SYNTHETIC_SOFTWARE_TEST_ONLY'})

kernelroot=REPORT/'kernels';kernel=(kernelroot/'validation');kernel.mkdir(parents=True,exist_ok=True)
(kernel/'kernel.json').write_text(json.dumps({'argv':[sys.executable,'-m','ipykernel_launcher','-f','{connection_file}'],
    'display_name':'Validation Python','language':'python'}))
base=nbformat.read(ROOT/'diffusion_trivalent_adaptive_colab_2026-09-29.ipynb',as_version=4)
nbformat.validate(base)
for c in base.cells:
    if c.cell_type=='code':compile(c.source,c.id,'exec')
results=[]
for label in ('empty_inputs','synthetic_import','standalone_calibration'):
    nb=copy.deepcopy(base)
    if label=='synthetic_import':
        for c in nb.cells:
            if c.get('id')=='configuration':
                c.source += '\n# VALIDATION OVERRIDES — not included in deliverable\n'
                c.source += f'TARGETS={inputs!r}\nRUN_GPU_SETUP=False\nRUN_BOLTZ=False\n'
                c.source += f'EXTERNAL_PREDICTIONS={predictions!r}\nWORK_BASE=Path({str(REPORT/"synthetic_runs")!r})\n'
                c.source += f'AF3RED_OUTPUT_ROOT={str(fixtures)!r}\n'
            elif c.get('id')=='ideal-closure':
                c.source=c.source.replace('RUN_IDEAL_LINKER_SCENARIO=False','RUN_IDEAL_LINKER_SCENARIO=True')
                joint=next(p for p in predictions if p['variant_index']==0 and p['role']=='joint')
                c.source=c.source.replace('IDEAL_JOINT_PATH=""',f'IDEAL_JOINT_PATH={joint["path"]!r}')
                c.source=c.source.replace('IDEAL_CHAIN_MAP={}',f'IDEAL_CHAIN_MAP={joint["chain_map"]!r}')
            elif c.get('id')=='thermodynamics':
                c.source=c.source.replace('THERMODYNAMIC_SCENARIO=None',
                    'THERMODYNAMIC_SCENARIO={"variant_id":VARIANTS[0]["id"],"target_order":VARIANTS[0]["order"],'
                    '"evidence_kind":"model_scenario","source_note":"SYNTHETIC SOFTWARE TEST; not measurements",'
                    '"kd_M":[1e-6,2e-6,3e-6],"temperature_K":298.15,"kd_temperature_K":298.15,'
                    '"closure_factors":{"12":1e-4,"13":8e-5,"23":2e-4,"123":2e-8},'
                    '"concentrations_M":[1e-12,1e-9,1e-6,1e-3,1.]}')
            elif c.get('id')=='adaptive-calibration':
                c.source=c.source.replace('RUN_CALIBRATION=False','RUN_CALIBRATION=True')
                c.source=c.source.replace('CALIBRATION_BASELINE_FILE=""',f'CALIBRATION_BASELINE_FILE={str(baselinepath)!r}')
                c.source=c.source.replace('CALIBRATION_CSV="/content/avidity_measurements.csv"',f'CALIBRATION_CSV={str(csvpath)!r}')
                c.source=c.source.replace('CALIBRATION_METADATA_FILE="/content/avidity_metadata.json"',f'CALIBRATION_METADATA_FILE={str(metapath)!r}')
                c.source=c.source.replace('PARAMETER_BOUNDS={}','PARAMETER_BOUNDS={"J123_M2":[1e-12,1e-5]}')
        nb.cells.append(nbformat.v4.new_code_cell('''
assert len(VARIANTS)==2 and len(PREDICTION_REPORTS)==4
assert all(r['status']=='NO_LISTED_GEOMETRIC_DEFECT_DETECTED' for r in PREDICTION_REPORTS[:3])
# In the direct-fusion toy model, neighboring receptors meet at peptide-like
# distances despite being separate molecules. This MUST be reported as a clash.
assert PREDICTION_REPORTS[3]['status']=='REVIEW_REQUIRED'
assert 'INTERCHAIN_CLASHES' in PREDICTION_REPORTS[3]['reasons']
assert all(sum(v['valency_by_target'].values())==3 for v in VARIANTS)
assert THERMO_RESULT['status']=='CONDITIONAL_MODEL_RESULT'
assert IDEAL_CLOSURE['status']=='IDEAL_CHAIN_SCENARIO_ONLY'
assert CALIBRATION_RESULT['eligible_for_auto_use'], CALIBRATION_RESULT['warnings']
assert abs(CALIBRATION_RESULT['fitted_parameters']['J123_M2']/2e-8-1)<1e-5
assert ACTIVE_THERMODYNAMIC_SCENARIO['calibration_id']==CALIBRATION_RESULT['calibration_id']
assert CALIBRATED_THERMO_RESULT['status']=='CONDITIONAL_MODEL_RESULT'
assert Path(CALIBRATION_ARCHIVE).is_file()
assert Path(archive).is_file()
print('SYNTHETIC END-TO-END ASSERTIONS PASSED; not biological validation')
'''))
    elif label=='standalone_calibration':
        nb.cells=[c for c in nb.cells if c.get('id') in ('cpu-dependencies','embedded-source','adaptive-calibration','calibration-results')]
        for c in nb.cells:
            if c.get('id')=='adaptive-calibration':
                c.source=c.source.replace('RUN_CALIBRATION=False','RUN_CALIBRATION=True')
                c.source=c.source.replace('CALIBRATION_VARIANT_FILE=""',f'CALIBRATION_VARIANT_FILE={str(variantpath)!r}')
                c.source=c.source.replace('CALIBRATION_BASELINE_FILE=""',f'CALIBRATION_BASELINE_FILE={str(baselinepath)!r}')
                c.source=c.source.replace('CALIBRATION_CSV="/content/avidity_measurements.csv"',f'CALIBRATION_CSV={str(csvpath)!r}')
                c.source=c.source.replace('CALIBRATION_METADATA_FILE="/content/avidity_metadata.json"',f'CALIBRATION_METADATA_FILE={str(metapath)!r}')
                c.source=c.source.replace('PARAMETER_BOUNDS={}','PARAMETER_BOUNDS={"J123_M2":[1e-12,1e-5]}')
                c.source=c.source.replace('if CALIBRATION_VARIANT:',f'CALIBRATION_HISTORY=Path({str(REPORT/"standalone_history")!r})\nif CALIBRATION_VARIANT:')
        nb.cells.append(nbformat.v4.new_code_cell('''
assert CALIBRATION_RESULT['eligible_for_auto_use'],CALIBRATION_RESULT['warnings']
assert abs(CALIBRATION_RESULT['fitted_parameters']['J123_M2']/2e-8-1)<1e-5
assert 'ARMS' not in globals() and 'RUN_ROOT' not in globals()
assert Path(CALIBRATION_ARCHIVE).is_file()
print('STANDALONE CALIBRATION PASSED WITHOUT DESIGN PIPELINE')
'''))
    else:
        nb.cells.append(nbformat.v4.new_code_cell("assert not READY and not VARIANTS and RUN_ROOT is None\nprint('EMPTY INPUT GUARD PASSED')"))
    ksm=KernelSpecManager(kernel_dirs=[str(kernelroot)])
    km=KernelManager(kernel_name='validation',kernel_spec_manager=ksm)
    client=NotebookClient(nb,km=km,timeout=180,resources={'metadata':{'path':str(REPORT)}})
    try:
        client.execute()
    except Exception as exc:
        print(label,type(exc).__name__,str(exc)[-2200:],flush=True)
        raise SystemExit(1) from None
    finally:
        nbformat.write(nb,REPORT/f'{label}.executed.ipynb')
        if km.has_kernel:km.shutdown_kernel(now=True)
    errors=[o for c in nb.cells if c.cell_type=='code' for o in c.outputs if o.output_type=='error']
    assert not errors,errors
    results.append({'case':label,'status':'PASS','executed_code_cells':sum(c.cell_type=='code' for c in nb.cells)})
    print(label,'PASS',flush=True)
(REPORT/'results.json').write_text(json.dumps({'notebook_execution':results,'gpu_inference':'NOT_RUN',
    'real_targets':'NOT_SUPPLIED','biological_validation':'NOT_ESTABLISHED'},indent=2)+'\n')
print(REPORT/'results.json')
