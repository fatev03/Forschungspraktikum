"""Sequence-first folding exports and inspection of explicitly supplied predictions."""
import itertools, json, math, shutil
from pathlib import Path
import numpy as np
from Bio.PDB import MMCIFIO
from .core import chain_data, contacts, digest, distances, finite, load_structure, write_json, missing_heavy_atoms


def folding_jobs(variant):
    arms=variant['arms'];seq=variant['sequence']
    targets=[(a['target_id'],a['target_sequence']) for a in arms]
    jobs=[('cassette_alone',[('A',seq,True)]),
          ('joint',[('A',seq,True)]+[(chr(66+i),s,False) for i,(_,s) in enumerate(targets)])]
    for i,(name,s) in enumerate(targets):
        jobs.append((f'cassette_target_{i+1}',[('A',seq,True),('B',s,False)]))
    # Three on-target and six cross-target predictions: off-target evaluation remains separate.
    for i,a in enumerate(arms):
        for j,(_,s) in enumerate(targets):
            jobs.append((f'domain_{i+1}_target_{j+1}',[('A',a['binder_sequence'],True),('B',s,False)]))
    return jobs


def export_variant(variant,out_root,seeds=(1,2,3)):
    out=Path(out_root)/variant['id'];out.mkdir(parents=True,exist_ok=False)
    (out/'prediction_inputs').mkdir();(out/'pair_models').mkdir();(out/'predictions').mkdir()
    (out/'cassette.fasta').write_text(f">{variant['id']} | one chain | valency 1,1,1\n{variant['sequence']}\n")
    write_json(out/'variant.json',variant)
    # Source complexes remain separate files/objects; never place pairwise coordinates in one frame.
    for i,a in enumerate(variant['arms'],1):
        src=Path(a['source']['path'])
        if digest(src)!=a['source']['sha256']:raise ValueError('Pair source changed since inspection')
        shutil.copy2(src,out/'pair_models'/f'pair_{i}{src.suffix.lower()}')
    server=[];job_index=[]
    for role,chains in folding_jobs(variant):
        name=variant['id']+'_'+role
        af=[];boltz=[];srv=[]
        for cid,s,denovo in chains:
            p={'id':cid,'sequence':s}
            if denovo:p.update(unpairedMsa='',pairedMsa='',templates=[])
            af.append({'protein':p})
            b={'id':cid,'sequence':s}
            if denovo:b['msa']='empty'
            boltz.append({'protein':b})
            srv.append({'proteinChain':{'sequence':s,'count':1,'useStructureTemplate':False if denovo else True}})
        write_json(out/'prediction_inputs'/f'{role}.af3.json',{'name':name,'modelSeeds':list(seeds),'sequences':af,'dialect':'alphafold3','version':1})
        # JSON is valid YAML 1.2 and avoids another serialization dependency.
        write_json(out/'prediction_inputs'/f'{role}.boltz.yaml',{'version':1,'sequences':boltz})
        server.append({'name':name,'modelSeeds':[str(x) for x in seeds],'sequences':srv,'dialect':'alphafoldserver','version':1})
        job_index.append({'role':role,'chains':{cid:s for cid,s,_ in chains},'status':'INPUT_ONLY_NOT_PREDICTED'})
    write_json(out/'alphafold_server_jobs.json',server)
    write_json(out/'prediction_jobs.json',job_index)
    (out/'README.txt').write_text('One cassette molecule has one binder per target.\n'
        'cassette.fasta is one covalently continuous sequence. Empty linkers mean direct peptide fusion.\n'
        'AlphaFold Server: upload alphafold_server_jobs.json (jobs may exceed server limits; select individual jobs).\n'
        'Local AF3/AF3-ReD: prediction_inputs/*.af3.json; receptor MSAs need the AF3 data pipeline.\n'
        'Boltz: prediction_inputs/*.boltz.yaml. MSA server sends receptor sequences to the service.\n'
        'Run cassette_alone AND joint for each retained variant; test single-target and cross-target jobs separately.\n'
        'Plain sequence inputs omit unknown glycans, cofactors and membranes; edit model inputs with known chemistry.\n'
        'Prediction files must be imported and sequence checked before they appear in PyMOL.\n'
        'PyMOL: run view_results.py from this folder. Each pair is a separate object; enable one at a time.\n'
        'No assembled coordinate model is fabricated from the separate pairwise structures.\n')
    # Python script uses its own file location, so relocating the ZIP is safe.
    (out/'view_results.py').write_text('from pathlib import Path\nfrom pymol import cmd\nimport json\n'
        'root=Path(__file__).resolve().parent\n'
        'for i,p in enumerate(sorted((root/"pair_models").glob("*")),1):\n'
        '    cmd.load(str(p), f"pair_{i}")\n'
        '    cmd.disable(f"pair_{i}")\n'
        'for p in sorted((root/"predictions").glob("*.cif")):\n'
        '    if p.name.endswith(".source.cif"): continue\n'
        '    cmd.load(str(p),p.stem)\n'
        '    cmd.disable(p.stem)\n'
        'cmd.hide("everything","all")\ncmd.show("cartoon","all")\n'
        'cmd.color("gray70","all")\n'
        'for meta in sorted((root/"predictions").glob("*.mapping.json")):\n'
        '    m=json.loads(meta.read_text()); obj=m["object"]\n'
        '    for region in m["binder_regions"]:\n'
        '        cmd.color(region["color"],"{} and chain A and resi {}-{}".format(obj,region["start"],region["end"]))\n'
        'if cmd.get_names("objects"):\n'
        '    cmd.enable(cmd.get_names("objects")[-1]);cmd.zoom(cmd.get_names("objects")[-1])\n')
    return out


def _aligned_rmsd(x,y):
    x=x-x.mean(0);y=y-y.mean(0)
    u,_,vt=np.linalg.svd(x.T@y);rot=u@vt
    if np.linalg.det(rot)<0:u[:,-1]*=-1;rot=u@vt
    return float(np.sqrt(np.mean(np.sum((x@rot-y)**2,axis=1))))


def inspect_prediction(variant,path,chain_map,role='joint',model_index=None,membrane=None,
                       contact_cutoff_A=5.,clash_cutoff_A=2.,domain_rmsd_review_A=3.):
    """chain_map names cassette and, for joint, each exact target ID. No guessed mapping."""
    if role not in ('joint','cassette_alone'):raise ValueError('Only full-cassette models accepted here')
    keys={'cassette'}|(set(variant['order']) if role=='joint' else set())
    if set(chain_map)!=keys or len(set(chain_map.values()))!=len(keys):raise ValueError('Explicit unique chain mapping required')
    model=load_structure(path,model_index)
    protein_chains={c.id for c in model if any(r.id[0]==' ' for r in c)}
    if protein_chains!=set(chain_map.values()):raise ValueError('Unmapped protein chains; role/complex identity must match the full model')
    d=chain_data(model,chain_map['cassette'],variant['sequence'])
    missing=[];breaks=[]
    for i,(left,right) in enumerate(zip(d['residues'],d['residues'][1:]),1):
        if 'C' not in left or 'N' not in right:missing.append(i);continue
        length=float(np.linalg.norm(left['C'].coord-right['N'].coord))
        if not 1.1<=length<=1.6:breaks.append({'after_position':i,'C_N_distance_A':length})
    domain_rows=[];cross=[]
    targets={a['target_id']:chain_data(model,chain_map[a['target_id']],a['target_sequence']) for a in variant['arms']} if role=='joint' else {}
    whole_cassette_clashes=[{'receptor_id':tid,'severe_close_atom_pairs':contacts(d['heavy'],t['heavy'],clash_cutoff_A)}
                            for tid,t in targets.items()]
    binder_regions=[r for r in variant['regions'] if r['kind']=='binder']
    for region,arm in zip(binder_regions,variant['arms']):
        lo,hi=region['start']-1,region['end'];res=d['residues'][lo:hi]
        xyz=np.array([atom.coord for rr in res for atom in rr if atom.element not in ('H','D')])
        source=load_structure(arm['source']['path'],arm['source'].get('model_index'))
        if digest(arm['source']['path'])!=arm['source']['sha256']:raise ValueError('Pair reference changed')
        ref=chain_data(source,arm['source']['binder_chain'],arm['binder_sequence'])
        domain_rows.append({'target_id':arm['target_id'],'binder_CA_RMSD_to_pair_A':_aligned_rmsd(d['ca'][lo:hi],ref['ca'])})
        for tid,t in targets.items():
            cross.append({'binder_target_id':arm['target_id'],'receptor_id':tid,'intended':tid==arm['target_id'],
                          'contact_atom_pairs':contacts(xyz,t['heavy'],contact_cutoff_A),
                          'severe_close_atom_pairs':contacts(xyz,t['heavy'],clash_cutoff_A)})
    # Nonlocal intrachain clashes (neighbor residues excluded; this is not a force field).
    coords=[];indices=[]
    for i,res in enumerate(d['residues']):
        for atom in res:
            if atom.element not in ('H','D'):coords.append(atom.coord);indices.append(i)
    from scipy.spatial import cKDTree
    clashes=sum(abs(indices[i]-indices[j])>2 for i,j in cKDTree(coords).query_pairs(clash_cutoff_A))
    receptor_clashes=[]
    for (a,x),(b,y) in itertools.combinations(targets.items(),2):
        receptor_clashes.append({'receptors':[a,b],'severe_close_atom_pairs':contacts(x['heavy'],y['heavy'],clash_cutoff_A)})
    membrane_result={'status':'NOT_ASSESSED'}
    if membrane is not None:
        normal=np.asarray(membrane['normal'],dtype=float);point=np.asarray(membrane['point_A'],dtype=float)
        if normal.shape!=(3,) or point.shape!=(3,) or not np.isfinite(normal).all() or not np.isfinite(point).all() or np.linalg.norm(normal)==0:
            raise ValueError('Finite membrane point and nonzero normal required')
        if not membrane.get('source_note'):raise ValueError('Membrane plane must have a source in this exact coordinate frame')
        normal/=np.linalg.norm(normal)
        signed=(d['heavy']-point)@normal
        membrane_result={'status':'SUPPLIED_HALF_SPACE_ONLY','binder_atoms_below_plane':int((signed<0).sum()),'declaration':membrane}
    hetero=[a.coord for c in model for r in c if r.id[0] not in (' ','W') for a in r if a.element not in ('H','D')]
    hetero_clash=contacts(d['heavy'],np.asarray(hetero),clash_cutoff_A) if hetero else None
    incomplete={'cassette':missing_heavy_atoms(d),**{tid:missing_heavy_atoms(t) for tid,t in targets.items()}}
    reasons=[]
    if any(incomplete.values()):reasons.append('INCOMPLETE_HEAVY_ATOMS')
    if missing:reasons.append('MISSING_JUNCTION_ATOMS')
    if breaks:reasons.append('PEPTIDE_BOND_GEOMETRY_REVIEW')
    if clashes:reasons.append('NONLOCAL_INTRACHAIN_CLASHES')
    if any(x['severe_close_atom_pairs'] for x in whole_cassette_clashes+receptor_clashes):reasons.append('INTERCHAIN_CLASHES')
    if any(x['binder_CA_RMSD_to_pair_A']>finite(domain_rmsd_review_A,'domain RMSD review threshold',strict=True) for x in domain_rows):
        reasons.append('DOMAIN_FOLD_CHANGE_REVIEW')
    if role=='joint' and any(x['intended'] and x['contact_atom_pairs']==0 for x in cross):reasons.append('INTENDED_INTERFACE_ABSENT')
    if membrane_result.get('binder_atoms_below_plane',0):reasons.append('MEMBRANE_HALF_SPACE_VIOLATION')
    if hetero_clash:reasons.append('HETEROATOM_CLASH_REVIEW')
    return {'status':'REVIEW_REQUIRED' if reasons else 'NO_LISTED_GEOMETRIC_DEFECT_DETECTED',
            'reasons':reasons,'role':role,'source_path':str(Path(path).resolve()),'sha256':digest(path),
            'chain_map':chain_map,'missing_junction_positions':missing,'peptide_bond_outliers':breaks,
            'missing_heavy_atoms':incomplete,
            'domain_comparison':domain_rows,'interface_contact_matrix':cross,'nonlocal_intrachain_close_pairs':clashes,
            'whole_cassette_receptor_close_pairs':whole_cassette_clashes,'domain_rmsd_review_threshold_A':domain_rmsd_review_A,
            'receptor_close_pairs':receptor_clashes,'membrane':membrane_result,'heteroatom_close_pairs':hetero_clash,
            'scope':'structure plausibility only; does not establish simultaneous biological binding, selectivity or activation'}


def import_prediction(variant,out_dir,path,chain_map,role='joint',provider='external',model_index=None,membrane=None):
    report=inspect_prediction(variant,path,chain_map,role,model_index,membrane)
    model=load_structure(path,model_index)
    # Canonical visualization copy with sequence-position numbering; raw bytes are retained too.
    from Bio.PDB.Structure import Structure
    from Bio.PDB.Model import Model
    from Bio.PDB.Chain import Chain
    import copy
    s=Structure('prediction');m=Model(0);s.add(m)
    order=['cassette']+[t for t in variant['order'] if t in chain_map]
    mapping=[]
    for i,label in enumerate(order):
        cid=chr(65+i);c=Chain(cid);m.add(c)
        residues=[r for r in model[chain_map[label]] if r.id[0]==' ']
        for pos,r in enumerate(residues,1):
            rr=copy.deepcopy(r);rr.detach_parent();rr.id=(' ',pos,' ');c.add(rr)
            mapping.append({'input_chain':chain_map[label],'input_residue':list(r.id),'output_chain':cid,'output_position':pos})
    # Preserve non-water hetero residues as independent inspection chains, without claiming chemical bonds.
    for j,old in enumerate(model):
        het=[r for r in old if r.id[0] not in (' ','W')]
        if het:
            c=Chain(f'H{j+1}');m.add(c)
            for r in het:
                rr=copy.deepcopy(r);rr.detach_parent();c.add(rr)
    dest=Path(out_dir)/'predictions';dest.mkdir(exist_ok=True)
    tag=role+'_'+report['sha256'][:12]
    if (dest/(tag+'.report.json')).exists():raise ValueError('Prediction already imported; use its existing report')
    raw=Path(path);shutil.copy2(raw,dest/(tag+'.source'+raw.suffix.lower()))
    writer=MMCIFIO();writer.set_structure(s);writer.save(str(dest/(tag+'.cif')))
    report['provider_declaration']=provider;report['residue_mapping']=mapping
    write_json(dest/(tag+'.report.json'),report)
    regions=[dict(r,color=color) for r,color in zip([r for r in variant['regions'] if r['kind']=='binder'],('cyan','orange','violet'))]
    write_json(dest/(tag+'.mapping.json'),{'object':tag,'binder_regions':regions})
    return report
