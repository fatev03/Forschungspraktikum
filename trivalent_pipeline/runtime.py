"""Colab GPU orchestration. Called explicitly; import never installs or downloads."""
from __future__ import annotations
import csv, json, os, re, subprocess, sys, tarfile, time, urllib.request, zipfile
from pathlib import Path
from .core import analyse_pair, finite, prepare_target, safe_id, sequence, write_json, digest, load_structure, chain_data

REFS={'rfdiffusion':'597d37f2a686e23941440fddf6daa4cb778e7bc7',
      'colabdesign':'e31a56fe1d9b4de25c8697f3a28b75892941cc72',
      'boltz':'b1ebfc46ecf57f5414e0d1a6f9027bbb122c53bc'}
URLS={'rfdiffusion':'https://github.com/sokrypton/RFdiffusion.git',
      'colabdesign':'https://github.com/sokrypton/ColabDesign.git',
      'boltz':'https://github.com/jwohlwend/boltz.git'}

def checked(cmd,cwd=None,log=None,env=None):
    print('Running:', ' '.join(map(str,cmd)))
    if log:
        with open(log,'w') as out:
            p=subprocess.run(list(map(str,cmd)),cwd=cwd,env=env,stdout=out,stderr=subprocess.STDOUT)
        if p.returncode:
            tail=Path(log).read_text(errors='replace')[-6000:]
            raise RuntimeError(f'Command failed ({p.returncode}); log: {log}\n{tail}')
    else:subprocess.run(list(map(str,cmd)),cwd=cwd,env=env,check=True)


def download(url,path):
    path=Path(path)
    if path.is_file() and path.stat().st_size>0:return
    tmp=path.with_suffix(path.suffix+'.partial');path.parent.mkdir(parents=True,exist_ok=True)
    print('Downloading:',url)
    with urllib.request.urlopen(url,timeout=180) as src,open(tmp,'wb') as dst:
        while True:
            block=src.read(4*1024*1024)
            if not block:break
            dst.write(block)
    if tmp.stat().st_size==0:raise RuntimeError('Empty download')
    tmp.replace(path)


def checkout(name,root):
    dest=Path(root)/name
    if not dest.exists():checked(['git','clone',URLS[name],str(dest)])
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=dest,text=True).strip()
    if head!=REFS[name]:
        dirty=subprocess.check_output(['git','status','--porcelain'],cwd=dest,text=True).strip()
        if dirty:raise RuntimeError(f'Preserve edits in {dest}; expected pinned revision')
        checked(['git','checkout',REFS[name]],cwd=dest)
    return dest


def setup_gpu(root,design=True,boltz=True):
    """Separate Python 3.11 environments; no changes to Colab's torch/JAX."""
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    checked(['nvidia-smi'])
    checked([sys.executable,'-m','pip','install','uv'])
    uv=[sys.executable,'-m','uv'];checked(uv+['python','install','3.11'])
    config={'root':str(root),'refs':REFS}
    def venv(name,requirements):
        env=root/name;py=env/'bin/python'
        if not py.exists():checked(uv+['venv','--python','3.11',str(env)])
        stamp=env/'pipeline_setup.json'
        signature={'requirements':requirements,'refs':REFS}
        if not stamp.exists() or json.loads(stamp.read_text())!=signature:
            checked(uv+['pip','install','--python',str(py)]+requirements)
            write_json(stamp,signature)
        return py
    if design:
        rf=checkout('rfdiffusion',root);cd=checkout('colabdesign',root)
        rfpy=venv('rf_env',['numpy==1.26.4','scipy==1.13.1','torch==2.4.1','torchdata==0.8.0',
                           'pandas','hydra-core','omegaconf','icecream','pyrsistent','pynvml','decorator',
                           'e3nn==0.5.5','opt_einsum','opt_einsum_fx','requests','tqdm','psutil'])
        marker=rfpy.parent.parent/'se3_ready'
        if not marker.exists():
            checked(uv+['pip','install','--python',str(rfpy),'torch==2.4.1+cu124',
                        '--index-url','https://download.pytorch.org/whl/cu124'])
            checked(uv+['pip','install','--python',str(rfpy),'--no-deps','dgl==2.4.0',
                        '-f','https://data.dgl.ai/wheels/torch-2.4/cu124/repo.html'])
            checked(uv+['pip','install','--python',str(rfpy),'git+https://github.com/NVIDIA/dllogger'])
            checked(uv+['pip','install','--python',str(rfpy),'--no-deps',str(rf/'env/SE3Transformer')])
            checked([rfpy,'-c','import torch,dgl,se3_transformer; assert torch.cuda.is_available(); print(torch.__version__,dgl.__version__)'])
            marker.touch()
        # JAX 0.4 retains the clip keyword API expected by this ColabDesign revision.
        cdpy=venv('design_env',['numpy==1.26.4','scipy==1.13.1','jax[cuda12]==0.4.35',
                    'chex==0.1.87','optax==0.2.4','dm-haiku==0.0.13',str(cd)])
        checked([cdpy,'-c','import jax; assert any(d.platform=="gpu" for d in jax.devices()); import colabdesign; print(jax.devices())'])
        for name,token in [('Base_ckpt.pt','6f5902ac237024bdd0c176cb93063dc4'),('Complex_base_ckpt.pt','e29311f6f1bf1af907f9ef9f44b8328b')]:
            download(f'https://files.ipd.uw.edu/pub/RFdiffusion/{token}/{name}',rf/'models'/name)
        params=root/'params';params.mkdir(exist_ok=True)
        if not (params/'params_model_1_ptm.npz').exists():
            archive=root/'alphafold_params_2022-12-06.tar'
            download('https://storage.googleapis.com/alphafold/alphafold_params_2022-12-06.tar',archive)
            with tarfile.open(archive) as tf:
                members=tf.getmembers()
                for m in members:
                    if not (m.isfile() or m.isdir()) or not (params/m.name).resolve().is_relative_to(params.resolve()):
                        raise ValueError('Unsafe/non-file member in weights archive')
                tf.extractall(params,members=members)
            if not (params/'params_model_1_ptm.npz').exists():raise RuntimeError('AlphaFold weights incomplete')
        config.update(rf_repo=str(rf),cd_repo=str(cd),rf_python=str(rfpy),design_python=str(cdpy),
                      weight_sha256={str(p.relative_to(root)):digest(p) for p in
                        [rf/'models/Base_ckpt.pt',rf/'models/Complex_base_ckpt.pt',params/'params_model_1_ptm.npz']})
    if boltz:
        br=checkout('boltz',root)
        bp=venv('boltz_env',[str(br)])
        config.update(boltz_bin=str(bp.parent/'boltz'))
    write_json(root/'environment.json',config)
    for key in ('rf_python','design_python'):
        if key in config:
            freeze=subprocess.check_output(uv+['pip','freeze','--python',config[key]],text=True)
            (root/(key+'_freeze.txt')).write_text(freeze)
    if boltz:(root/'boltz_freeze.txt').write_text(subprocess.check_output(uv+['pip','freeze','--python',str(bp)],text=True))
    return config


def validate_target_specs(targets):
    if len(targets)!=3 or len({t['target_id'] for t in targets})!=3:raise ValueError('Declare exactly three distinct receptor target IDs')
    for t in targets:
        safe_id(t['target_id']);sequence(t['target_sequence'])
        if t['mode'] not in ('design','import'):raise ValueError('Target mode must be design or import')
        if t['mode']=='design':
            if not Path(t['target_path']).is_file():raise ValueError(f"Missing receptor file: {t['target_path']}")
            if type(t['binder_length'])!=int or t['binder_length']<10:raise ValueError('binder_length must be an integer >=10')
            if not t['hotspot_positions']:raise ValueError('Supply hotspot positions in the declared construct sequence (1-based)')
            if any(type(i)!=int or not 1<=i<=len(t['target_sequence']) for i in t['hotspot_positions']):raise ValueError('Hotspot position out of sequence bounds')
        else:
            sequence(t['binder_sequence'])
            if not Path(t['pair_path']).is_file():raise ValueError(f"Missing pair structure: {t['pair_path']}")
    if len({t['target_sequence'] for t in targets})!=3:raise ValueError('Three different receptor constructs required')


def normalize_rf_backbone(path,target_sequence,binder_length):
    """RF outputs binder A then receptor B; publish target A then binder B for AF2.

    The RF contig must be `N-N A1-L/0`. Coordinate order is never relabelled
    by length alone: target identity and both chain lengths are checked first.
    """
    import copy
    from Bio.PDB import PDBIO
    from Bio.PDB.Structure import Structure
    from Bio.PDB.Model import Model
    from Bio.PDB.Chain import Chain
    path=Path(path);model=load_structure(path)
    if {c.id for c in model} != {'A','B'}:raise ValueError('Unexpected RF chain mapping')
    b=chain_data(model,'A');t=chain_data(model,'B',target_sequence)
    if len(b['sequence'])!=binder_length:raise ValueError('RF binder length changed')
    out=Structure('normalized');m=Model(0);out.add(m)
    for cid,data in [('A',t),('B',b)]:
        c=Chain(cid);m.add(c)
        for i,r in enumerate(data['residues'],1):
            rr=copy.deepcopy(r);rr.detach_parent();rr.id=(' ',i,' ');c.add(rr)
    raw=path.with_suffix('.raw.pdb')
    if raw.exists():raise ValueError('Raw RF backbone already retained')
    raw.write_bytes(path.read_bytes())
    io=PDBIO();io.set_structure(out);io.save(str(path))


def generate_target(t,environment,out,settings):
    """Run one target; keep all rows and fail closed if none pass heuristic screens."""
    safe_id(t['target_id']);out=Path(out);out.mkdir(parents=True,exist_ok=False)
    prepared=prepare_target(t['target_path'],t['target_chain'],t['target_sequence'],out/'target.pdb',t.get('model_index'))
    write_json(out/'target_mapping.json',prepared)
    n=t['binder_length'];length=len(t['target_sequence']);prefix=out/'backbone'
    num=settings['num_designs'];seqs=settings['num_sequences']
    if type(num)!=int or num<1 or type(seqs)!=int or seqs not in (1,2,4,8,16,32,64):raise ValueError('Invalid design/sequence count')
    steps=settings['diffusion_steps']
    if type(steps)!=int or not 1<=steps<=200:raise ValueError('diffusion_steps must be 1..200')
    contigs=[f'A1-{length}',f'{n}-{n}']
    cmd=[environment['rf_python'],str(Path(environment['rf_repo'])/'run_inference.py'),
         'inference.input_pdb='+str(out/'target.pdb'),'inference.output_prefix='+str(prefix),
         f'inference.num_designs={num}','inference.design_startnum=0','inference.deterministic=True',
         f'diffuser.T={steps}',f'contigmap.contigs=[{n}-{n} A1-{length}/0]',
         'ppi.hotspot_res=['+','.join('A'+str(i) for i in t['hotspot_positions'])+']']
    checked(cmd,cwd=environment['rf_repo'],log=out/'rfdiffusion.log')
    for i in range(num):normalize_rf_backbone(str(prefix)+f'_{i}.pdb',t['target_sequence'],n)
    childenv=os.environ.copy();childenv['XLA_PYTHON_CLIENT_PREALLOCATE']='false'
    pred=out/'mpnn_af';script=Path(environment['cd_repo'])/'colabdesign/rf/designability_test.py'
    runner=out/'design_runner.py'
    runner.write_text('import sys,runpy,random,numpy as np\nrandom.seed(0);np.random.seed(0)\n'
                      +'script=sys.argv[1];sys.argv=sys.argv[1:];runpy.run_path(script,run_name="__main__")\n')
    args=[environment['design_python'],str(runner),str(script),'--pdb='+str(prefix)+'_0.pdb',
          '--loc='+str(pred),'--contigs='+':'.join(contigs),f'--num_designs={num}',f'--num_seqs={seqs}',
          '--num_recycles='+str(settings['af_recycles']),'--mpnn_sampling_temp='+str(settings['mpnn_temperature']),
          '--rm_aa='+settings.get('exclude_amino_acids',''),'--initial_guess']
    checked(args,cwd=environment['root'],log=out/'mpnn_af.log',env=childenv)
    selected=None;allrows=[];gates=settings['screens']
    with open(pred/'mpnn_results.csv') as f:
        for row in csv.DictReader(f):
            metrics={k:float(row[k]) for k in ('plddt','i_ptm','i_pae','rmsd')}
            if not all(math_isfinite(v) for v in metrics.values()):continue
            if not 0<=metrics['plddt']<=1 or not 0<=metrics['i_ptm']<=1:raise ValueError('Unexpected confidence scale')
            eligible=metrics['plddt']>=gates['min_plddt'] and metrics['i_ptm']>=gates['min_iptm'] and metrics['i_pae']<=gates['max_ipae_A'] and metrics['rmsd']<=gates['max_rmsd_A']
            row['passes_declared_heuristics']=eligible;allrows.append(row)
    write_json(out/'candidate_rows.json',allrows)
    # Screen structure for every confidence-eligible candidate; lowest RMSD among retained.
    for row in sorted((r for r in allrows if r['passes_declared_heuristics']),key=lambda r:float(r['rmsd'])):
        seqparts=row['seq'].split('/')
        if len(seqparts)!=2 or seqparts[0]!=t['target_sequence']:raise ValueError('Generated target/binder sequence mapping changed')
        a,b=int(row['design']),int(row['n'])
        spec={'target_id':t['target_id'],'candidate_id':f"{t['target_id']}_d{a}_s{b}",
              'path':str(pred/'all_pdb'/f'design{a}_n{b}.pdb'),'target_chain':'A','binder_chain':'B',
              'target_sequence':seqparts[0],'binder_sequence':seqparts[1],'provider':'RFdiffusion_ProteinMPNN_AF2',
              'confidence':{k:float(row[k]) for k in ('plddt','i_ptm','i_pae','rmsd')},
              'biological_context':t.get('biological_context',{})}
        arm=analyse_pair(spec)
        if arm['screen_state']=='GEOMETRY_CANDIDATE':selected=arm;break
    if selected is None:raise RuntimeError(f"No candidate passed the declared heuristic and geometry screens for {t['target_id']}. See {out/'candidate_rows.json'}. Increase sampling or revise target/hotspots; no fallback candidate is substituted.")
    write_json(out/'selected_candidate.json',selected)
    return selected


def math_isfinite(x):
    import math
    return math.isfinite(x)


def obtain_arms(targets,environment,run_root,settings):
    validate_target_specs(targets);arms=[]
    for t in targets:
        if t['mode']=='design':
            if environment is None:raise ValueError('GPU setup is required for design mode')
            arm=generate_target(t,environment,Path(run_root)/'designs'/t['target_id'],settings)
        else:
            arm=analyse_pair({'target_id':t['target_id'],'candidate_id':t['target_id']+'_external',
                'path':t['pair_path'],'target_chain':t['target_chain'],'binder_chain':t['binder_chain'],
                'target_sequence':t['target_sequence'],'binder_sequence':t['binder_sequence'],
                'model_index':t.get('model_index'),'provider':t.get('provider','external'),
                'confidence':t.get('confidence'),'biological_context':t.get('biological_context',{})})
        arms.append(arm)
    return arms


def predict_boltz(environment,variant_dir,roles=('cassette_alone','joint'),samples=3,recycles=3):
    """Keep all samples and raw confidence. No automatic confidence-to-affinity conversion."""
    if type(samples)!=int or not 1<=samples<=20:raise ValueError('samples must be an integer 1..20')
    variant_dir=Path(variant_dir);predictions=[]
    for role in roles:
        safe_id(role)
        inp=variant_dir/'prediction_inputs'/f'{role}.boltz.yaml'
        out=variant_dir/'boltz_runs'/role
        if out.exists():raise ValueError(f'{out} already exists; retain provenance and choose a fresh run')
        out.mkdir(parents=True)
        checked([environment['boltz_bin'],'predict',str(inp),'--out_dir',str(out),'--use_msa_server',
                 '--output_format','mmcif','--diffusion_samples',str(samples),'--recycling_steps',str(recycles),
                 '--no_kernels','--num_workers','2'],log=out/'prediction.log')
        paths=sorted(out.rglob('*_model_*.cif'))
        if len(paths)!=samples:raise RuntimeError(f'Expected {samples} Boltz samples for {role}, found {len(paths)}; inspect {out}')
        predictions.extend({'path':str(p),'role':role} for p in paths)
    return predictions
