"""Explicit protein identities and geometry. No affinity inference or silent repairs."""
from __future__ import annotations
import copy, hashlib, itertools, json, math, re
from pathlib import Path
import numpy as np
from Bio.PDB import PDBParser, MMCIFParser, PDBIO
from Bio.SeqUtils import seq1
from Bio.SeqUtils.ProtParam import ProteinAnalysis
from scipy.spatial import cKDTree

AA20 = set('ACDEFGHIKLMNPQRSTVWY')
SIDECHAIN_ATOMS={
    'A':'CB','R':'CB CG CD NE CZ NH1 NH2','N':'CB CG OD1 ND2','D':'CB CG OD1 OD2',
    'C':'CB SG','E':'CB CG CD OE1 OE2','Q':'CB CG CD OE1 NE2','G':'',
    'H':'CB CG ND1 CD2 CE1 NE2','I':'CB CG1 CG2 CD1','L':'CB CG CD1 CD2',
    'K':'CB CG CD CE NZ','M':'CB CG SD CE','F':'CB CG CD1 CD2 CE1 CE2 CZ',
    'P':'CB CG CD','S':'CB OG','T':'CB OG1 CG2','W':'CB CG CD1 CD2 NE1 CE2 CE3 CZ2 CZ3 CH2',
    'Y':'CB CG CD1 CD2 CE1 CE2 CZ OH','V':'CB CG1 CG2'}

def missing_heavy_atoms(data):
    """Expected unmodified AA20 atoms; terminal OXT and hydrogens are optional."""
    result=[]
    for i,(aa,res) in enumerate(zip(data['sequence'],data['residues']),1):
        expected=set(('N CA C O '+SIDECHAIN_ATOMS[aa]).split())
        missing=sorted(expected-set(a.name for a in res))
        if missing:result.append({'position':i,'aa':aa,'missing_atoms':missing})
    return result

def finite(value, name, minimum=0., strict=False):
    if isinstance(value, bool):
        raise ValueError(f'{name} must be a finite number')
    x=float(value)
    if not math.isfinite(x) or (x<=minimum if strict else x<minimum):
        raise ValueError(f'{name} must be finite and {">" if strict else ">="} {minimum}')
    return x

def sequence(s):
    if not isinstance(s,str) or not s or set(s)-AA20:
        raise ValueError('A nonempty uppercase AA20 sequence is required; no silent residue conversion')
    return s

def safe_id(s):
    if not isinstance(s,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,59}',s):
        raise ValueError('IDs must begin with a letter and contain only letters, digits, _ or -')
    return s

def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()

def write_json(path,obj):
    Path(path).write_text(json.dumps(obj,indent=2,allow_nan=False,ensure_ascii=False)+'\n')

def load_structure(path, model_index=None):
    path=Path(path)
    if path.suffix.lower() in ('.cif','.mmcif'):
        parser=MMCIFParser(QUIET=True,auth_chains=True,auth_residues=True)
    elif path.suffix.lower()=='.pdb':
        parser=PDBParser(QUIET=True,PERMISSIVE=False)
    else: raise ValueError('Expected .pdb, .cif or .mmcif')
    st=parser.get_structure('input',str(path));models=list(st)
    if model_index is None:
        if len(models)!=1: raise ValueError('Multiple models: supply an explicit zero-based model_index')
        model_index=0
    if type(model_index)!=int or not 0<=model_index<len(models):raise ValueError('Invalid model_index')
    model=models[model_index]
    # Altloc policy: choose A if present, otherwise a unique conformer; never blend.
    for chain in model:
        for res in chain:
            if res.is_disordered()==2: raise ValueError('Disordered residue identity requires explicit resolution')
            for atom in res:
                if atom.is_disordered():
                    alts=atom.disordered_get_id_list()
                    if 'A' in alts:atom.disordered_select('A')
                    elif len(alts)==1:atom.disordered_select(alts[0])
                    else:raise ValueError('Ambiguous atom alternate locations')
                if not np.isfinite(atom.coord).all():raise ValueError('Nonfinite coordinates')
    return model

def chain_data(model, chain_id, expected_sequence=None):
    if chain_id not in model:raise ValueError(f'chain {chain_id} missing')
    residues=[r for r in model[chain_id] if r.id[0]==' ']
    if not residues:raise ValueError(f'chain {chain_id} has no standard protein residues')
    names=[r.resname for r in residues]
    seq=sequence(''.join(seq1(n,undef_code='X') for n in names))
    if expected_sequence is not None and seq!=sequence(expected_sequence):
        raise ValueError(f'chain {chain_id}: observed sequence differs from declared complete construct; missing residues or wrong mapping')
    if any('CA' not in r for r in residues):raise ValueError(f'chain {chain_id}: missing CA')
    atoms=[a for r in residues for a in r if a.element not in ('H','D')]
    ids=[{'chain':chain_id,'resnum':r.id[1],'icode':r.id[2].strip(),'aa':seq[i]} for i,r in enumerate(residues)]
    return {'sequence':seq,'residues':residues,'ca':np.array([r['CA'].coord for r in residues]),
            'heavy':np.array([a.coord for a in atoms]),'residue_map':ids}

def distances(a,b):
    if not len(a) or not len(b):raise ValueError('Empty coordinate set')
    return cKDTree(b).query(a)[0]

def contacts(a,b,cutoff=5.):
    finite(cutoff,'contact cutoff',strict=True)
    return int(sum(len(x) for x in cKDTree(a).query_ball_tree(cKDTree(b),cutoff)))

def sequence_report(seq,ph=7.4):
    seq=sequence(seq);p=ProteinAnalysis(seq)
    return {'length':len(seq),'molecular_weight_Da':p.molecular_weight(),'theoretical_pI':p.isoelectric_point(),
            'charge_at_pH':p.charge_at_pH(finite(ph,'pH')),'pH':ph,'gravy':p.gravy(),
            'cysteine_positions':[i+1 for i,a in enumerate(seq) if a=='C'],
            'N_glycosylation_sequon_positions':[m.start()+1 for m in re.finditer(r'(?=(N[^P][ST]))',seq)],
            'hydrophobic_runs_8plus':[[m.start()+1,m.end()] for m in re.finditer(r'[AVILMFWY]{8,}',seq)],
            'scope':'sequence descriptors and flags, not expression/solubility/glycosylation predictions'}

def analyse_pair(spec, iface_cutoff_A=8., clash_cutoff_A=2.):
    # Complete expected sequences are required: a coordinate fragment is not a complete binder.
    for key in ('target_id','candidate_id'):safe_id(spec[key])
    if spec['target_chain']==spec['binder_chain']:raise ValueError('Target and binder chains must differ')
    model=load_structure(spec['path'],spec.get('model_index'))
    t=chain_data(model,spec['target_chain'],spec['target_sequence'])
    b=chain_data(model,spec['binder_chain'],spec['binder_sequence'])
    iface_cutoff_A=finite(iface_cutoff_A,'interface cutoff',strict=True)
    clash_cutoff_A=finite(clash_cutoff_A,'clash cutoff',strict=True)
    mask=distances(b['ca'],t['heavy'])<iface_cutoff_A
    inter=int(mask.sum()); clash=contacts(b['heavy'],t['heavy'],clash_cutoff_A)
    heavy_contacts=contacts(b['heavy'],t['heavy'])
    incomplete={'target':missing_heavy_atoms(t),'binder':missing_heavy_atoms(b)}
    origin=b['ca'][mask].mean(0) if inter else None
    geom=None
    if inter:
        center=b['ca'].mean(0);away=center-origin
        def direction(x):
            v=x-center;den=np.linalg.norm(v)*np.linalg.norm(away)
            return float(np.dot(v,away)/den) if den>1e-9 else None
        geom={'n_offset_A':float(np.linalg.norm(b['ca'][0]-origin)),
              'c_offset_A':float(np.linalg.norm(b['ca'][-1]-origin)),
              'N_to_target_A':float(distances(b['ca'][:1],t['heavy'])[0]),
              'C_to_target_A':float(distances(b['ca'][-1:],t['heavy'])[0]),
              'body_span_A':float(np.linalg.norm(b['ca'][-1]-b['ca'][0])),
              'N_outward_proxy':direction(b['ca'][0]),'C_outward_proxy':direction(b['ca'][-1]),
              'scope':'CA based endpoint proxy; not peptide exit orientation'}
    hetero=[{'chain':c.id,'name':r.resname,'resnum':r.id[1]} for c in model for r in c if r.id[0] not in (' ','W')]
    return {'target_id':spec['target_id'],'candidate_id':spec['candidate_id'],
            'source':{'path':str(Path(spec['path']).resolve()),'sha256':digest(spec['path']),
                      'provider':spec.get('provider','external_unspecified'),'model_index':spec.get('model_index',0),
                      'target_chain':spec['target_chain'],'binder_chain':spec['binder_chain']},
            'target_sequence':t['sequence'],'binder_sequence':b['sequence'],
            'target_residue_map':t['residue_map'],'binder_residue_map':b['residue_map'],
            'interface_CA_count':inter,'heavy_atom_contact_pairs':heavy_contacts,
            'missing_heavy_atoms':incomplete,
            'severe_close_atom_pairs':clash,'geometry':geom,
            'screen_state':('NO_INTERFACE' if not inter or not heavy_contacts else
                            'INCOMPLETE_ATOMS' if any(incomplete.values()) else
                            'CLASH_REVIEW' if clash else 'GEOMETRY_CANDIDATE'),
            'hetero_residues_present':hetero,'sequence_properties':sequence_report(b['sequence']),
            'confidence':copy.deepcopy(spec.get('confidence')),
            'biological_context':copy.deepcopy(spec.get('biological_context',{})),
            'unresolved':['binding_experiment','cross_reactivity','activation_or_inhibition','expression_and_aggregation',
                          'membrane_context_unless_explicitly_supplied','glycans_not_listed_are_unknown_not_absent']}

def prepare_target(path,chain_id,expected_sequence,out_path,model_index=None):
    """Extract declared construct; renumber A1..N; return recoverable original numbering."""
    model=load_structure(path,model_index);d=chain_data(model,chain_id,expected_sequence)
    from Bio.PDB.Structure import Structure
    from Bio.PDB.Model import Model
    from Bio.PDB.Chain import Chain
    s=Structure('target');m=Model(0);c=Chain('A');s.add(m);m.add(c)
    for i,r in enumerate(d['residues'],1):
        rr=copy.deepcopy(r);rr.detach_parent();rr.id=(' ',i,' ');c.add(rr)
    io=PDBIO();io.set_structure(s);io.save(str(out_path))
    mapping=[dict(x,design_chain='A',design_resnum=i+1) for i,x in enumerate(d['residue_map'])]
    return {'sequence':d['sequence'],'mapping':mapping,'path':str(out_path),'source_sha256':digest(path),
            'omitted_context':'other chains, waters and HETATM omitted from RFdiffusion input; retained in original source'}

def gap_interval(s,a,b):
    s,a,b=[finite(v,'distance') for v in (s,a,b)]
    return max(0.,s-a-b,a-s-b,b-s-a),s+a+b

def spacing_screen(arms,linker_sequences,spacing_nm,contour_per_step_nm=.38):
    if len(arms)!=3 or len(linker_sequences)!=2:raise ValueError('Exactly three arms and two junctions required')
    step=finite(contour_per_step_nm,'contour per CA step',strict=True)
    if any(a['geometry'] is None for a in arms):return {'status':'UNAVAILABLE_NO_INTERFACE','rows':[]}
    if not spacing_nm:raise ValueError('Nonempty spacing grid required')
    rows=[]
    for spacing in spacing_nm:
        s=finite(spacing,'spacing',strict=True)*10
        for i,linker in enumerate(linker_sequences):
            if linker:sequence(linker)
            lo,hi=gap_interval(s,arms[i]['geometry']['c_offset_A'],arms[i+1]['geometry']['n_offset_A'])
            # N inserted residues imply N+1 CA steps between endpoint binder residues.
            contour=(len(linker)+1)*step*10
            if not linker:status='DIRECT_FUSION_REQUIRES_ATOMIC_JUNCTION_MODEL'
            elif lo>=contour:status='OUTSIDE_LENGTH_ENVELOPE'
            elif hi<contour:status='LENGTH_SCREEN_ONLY'
            else:status='ORIENTATION_DEPENDENT_LENGTH_SCREEN'
            rows.append({'spacing_nm':s/10,'junction':i+1,'gap_min_A':lo,'gap_max_A':hi,
                         'inserted_residues':len(linker),'CA_contour_A':contour,'status':status})
    return {'status':'COARSE_ENVELOPE_ONLY','rows':rows,
            'assumptions':['equally spaced collinear binder-interface centers, not receptor membrane anchors',
                           'free independent rotations give envelopes, not jointly attained extrema',
                           'no joint steric/membrane/glycan feasibility established'],
            'Ceff_export':None}

def build_cassettes(arms,connections,all_orders=False):
    if len(arms)!=3 or len({a['target_id'] for a in arms})!=3:raise ValueError('Three distinct target IDs required')
    if len({a['target_sequence'] for a in arms})!=3:raise ValueError('Target sequences are identical; verify three distinct constructs')
    if any(a['screen_state']!='GEOMETRY_CANDIDATE' for a in arms):raise ValueError('Incomplete/no-interface/clash candidates require repair and re-evaluation')
    orders=list(itertools.permutations(range(3))) if all_orders else [(0,1,2)]
    variants=[]
    for order in orders:
        ordered=[arms[i] for i in order]
        for conn in connections:
            safe_id(conn['name']);links=conn['linkers']
            if len(links)!=2:raise ValueError('Exactly two linker sequences (empty = direct fusion)')
            seq='';regions=[]
            for i,a in enumerate(ordered):
                start=len(seq)+1;seq+=sequence(a['binder_sequence'])
                regions.append({'kind':'binder','target_id':a['target_id'],'candidate_id':a['candidate_id'],
                                'start':start,'end':len(seq)})
                if i<2:
                    start=len(seq)+1
                    if links[i]:seq+=sequence(links[i])
                    regions.append({'kind':'linker','name':f'L{i+1}','start':start,'end':len(seq),'sequence':links[i]})
            key=json.dumps([order,conn['name'],seq,[a['source']['sha256'] for a in ordered]])
            vid='cassette_'+hashlib.sha256(key.encode()).hexdigest()[:12]
            variants.append({'id':vid,'connection':conn['name'],'order':[a['target_id'] for a in ordered],
                             'sequence':seq,'regions':regions,'linkers':list(links),'valency_by_target':{a['target_id']:1 for a in arms},
                             'arms':ordered,'sequence_properties':sequence_report(seq),
                             'status':'SEQUENCE_CANDIDATE_REQUIRES_FUSED_STRUCTURE_AND_EXPERIMENT'})
    return variants
