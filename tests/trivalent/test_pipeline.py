"""Synthetic correctness tests; no biological success or GPU inference implied."""
import copy, importlib.util, itertools, json, math, tempfile, unittest, sys, types
from pathlib import Path
import numpy as np
from trivalent_pipeline.core import *
from trivalent_pipeline.export import export_variant, import_prediction, inspect_prediction
from trivalent_pipeline.thermo import configurations, fixed_patch_equilibrium, evaluate_scenario
from trivalent_pipeline.runtime import normalize_rf_backbone, predict_boltz
from unittest.mock import patch

THREE={'A':'ALA','G':'GLY','S':'SER','T':'THR','V':'VAL','L':'LEU','K':'LYS','D':'ASP','E':'GLU','R':'ARG'}
def atom_rows(seq,cid,y=0.,serial=0):
    """Artificial extended atoms for software tests; not a physically relaxed protein."""
    lines=[]
    for i,aa in enumerate(seq,1):
        atoms=[('N',-1.17,0.),('CA',0.,0.),('C',1.30,0.),('O',1.30,1.2)]
        atoms += [(name,0.,1.5+j*.2) for j,name in enumerate(SIDECHAIN_ATOMS[aa].split())]
        for atom,offset,z in atoms:
            serial+=1;x=(i-1)*3.8+offset;elem=atom[0]
            lines.append(f'ATOM  {serial:5d} {atom:^4s} {THREE[aa]} {cid}{i:4d}    {x:8.3f}{y:8.3f}{z:8.3f}{1.:6.2f}{90.:6.2f}           {elem}\n')
    return lines,serial

def pdb(seqA,seqB):
    lines=[];serial=0
    for cid,seq,y in [('A',seqA,0.),('B',seqB,4.5)]:
        rows,serial=atom_rows(seq,cid,y,serial);lines+=rows
    return ''.join(lines)+'END\n'

def make_arms(root):
    arms=[]
    for i,(target,binder) in enumerate([('AGSTAGSTAG','KAKAKAKAKA'),('VLVLVLVLVL','SESESESESE'),('DKDKDKDKDK','RTRTRTRTRT')],1):
        p=root/f'pair{i}.pdb';p.write_text(pdb(target,binder))
        arms.append(analyse_pair({'target_id':f'R{i}','candidate_id':f'B{i}','path':str(p),
                                 'target_chain':'A','binder_chain':'B','target_sequence':target,
                                 'binder_sequence':binder,'provider':'synthetic_test'}))
    return arms

class StructureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.arms=make_arms(self.root)
    def tearDown(self):self.tmp.cleanup()
    def spec(self):
        a=self.arms[0]
        return {'target_id':'R1','candidate_id':'B1','path':a['source']['path'],'target_chain':'A','binder_chain':'B',
                'target_sequence':a['target_sequence'],'binder_sequence':a['binder_sequence']}
    def test_pair_geometry_identity(self):
        self.assertEqual(self.arms[0]['interface_CA_count'],10)
        self.assertAlmostEqual(self.arms[0]['geometry']['N_to_target_A'],4.5)
    def test_incomplete_sidechains_not_passed(self):
        spec=self.spec();p=Path(spec['path'])
        p.write_text(''.join(line for line in p.read_text().splitlines(True) if line[12:16].strip()!='NZ'))
        a=analyse_pair(spec);self.assertEqual(a['screen_state'],'INCOMPLETE_ATOMS')
        with self.assertRaises(ValueError):build_cassettes([a]+self.arms[1:],[{'name':'d','linkers':['','']}])
    def test_rf_target_binder_reordering_keeps_identity(self):
        p=self.root/'raw_rf.pdb';target=self.arms[0]['target_sequence']
        p.write_text(pdb('G'*10,target));normalize_rf_backbone(p,target,10)
        m=load_structure(p)
        self.assertEqual(chain_data(m,'A')['sequence'],target)
        self.assertEqual(chain_data(m,'B')['sequence'],'G'*10)
        self.assertTrue(p.with_suffix('.raw.pdb').is_file())
    def test_missing_interface_not_scored(self):
        spec=self.spec();m=load_structure(spec['path'])
        for a in m['B'].get_atoms():a.coord+=np.array([0,1000,0])
        from Bio.PDB import PDBIO
        io=PDBIO();io.set_structure(m);io.save(spec['path'])
        a=analyse_pair(spec);self.assertIsNone(a['geometry']);self.assertEqual(a['screen_state'],'NO_INTERFACE')
        with self.assertRaises(ValueError):build_cassettes([a]+self.arms[1:],[{'name':'direct','linkers':['','']}])
    def test_sequence_mismatch_refused(self):
        spec=self.spec();spec['binder_sequence']+='A'
        with self.assertRaises(ValueError):analyse_pair(spec)
    def test_same_chain_refused(self):
        spec=self.spec();spec['binder_chain']='A'
        with self.assertRaises(ValueError):analyse_pair(spec)
    def test_multimodel_requires_selection(self):
        p=Path(self.spec()['path']);raw=p.read_text().replace('END\n','')
        p.write_text('MODEL        1\n'+raw+'ENDMDL\nMODEL        2\n'+raw+'ENDMDL\n')
        with self.assertRaises(ValueError):load_structure(p)
        self.assertEqual(len(chain_data(load_structure(p,1),'B')['sequence']),10)
    def test_gap_exact_lower_and_symmetry(self):
        self.assertEqual(gap_interval(5,30,2),(23,37))
        for values in itertools.permutations((5,30,2)):self.assertEqual(gap_interval(*values)[0],23)
    def test_direct_linker_not_gaussian(self):
        r=spacing_screen(self.arms,['',''],[5,10]);self.assertIsNone(r['Ceff_export'])
        self.assertTrue(all(x['status'].startswith('DIRECT_FUSION') for x in r['rows']))
    def test_unreachable_envelope(self):
        r=spacing_screen(self.arms,['G'*20]*2,[100])
        self.assertTrue(all(x['status']=='OUTSIDE_LENGTH_ENVELOPE' for x in r['rows']))
        self.assertIsNone(r['Ceff_export'])
    def test_negative_and_empty_grid_refused(self):
        for grid in ([-1],[]):
            with self.assertRaises(ValueError):spacing_screen(self.arms,['GG']*2,grid)
    def test_assemble_two_connections_all_orders(self):
        v=build_cassettes(self.arms,[{'name':'direct','linkers':['','']},{'name':'GS','linkers':['GGGGS','GGGGS']}],True)
        self.assertEqual(len(v),12);self.assertEqual(len({x['id'] for x in v}),12)
        self.assertEqual(v[0]['sequence'],''.join(a['binder_sequence'] for a in self.arms))
        self.assertEqual(v[1]['sequence'],'GGGGS'.join(a['binder_sequence'] for a in self.arms))
        self.assertEqual(sum(v[0]['valency_by_target'].values()),3)
        self.assertEqual(v[1]['regions'][2]['start'],16)
    def test_distinct_receptors_required(self):
        aa=copy.deepcopy(self.arms);aa[1]['target_sequence']=aa[0]['target_sequence']
        with self.assertRaises(ValueError):build_cassettes(aa,[{'name':'d','linkers':['','']}])
    def test_exports_one_fused_chain(self):
        v=build_cassettes(self.arms,[{'name':'GS','linkers':['GGGGS','GGGGS']}])[0]
        out=export_variant(v,self.root/'exports')
        af=json.loads((out/'prediction_inputs/joint.af3.json').read_text())
        self.assertEqual(len(af['sequences']),4)
        self.assertEqual(af['sequences'][0]['protein']['sequence'],v['sequence'])
        self.assertEqual(af['sequences'][0]['protein']['pairedMsa'],'')
        server=json.loads((out/'alphafold_server_jobs.json').read_text())
        self.assertEqual(len(server),14)
        self.assertTrue(all(e['proteinChain']['count']==1 for e in server[1]['sequences']))
        compile((out/'view_results.py').read_text(),'pymol_script','exec')
        from unittest.mock import MagicMock
        fake=types.ModuleType('pymol');fake.cmd=MagicMock();fake.cmd.get_names.return_value=['pair_1','pair_2','pair_3']
        with patch.dict(sys.modules,{'pymol':fake}):
            exec((out/'view_results.py').read_text(),{'__file__':str(out/'view_results.py')})
        self.assertEqual(fake.cmd.load.call_count,3)
    def test_boltz_role_and_missing_sample_guard(self):
        v=build_cassettes(self.arms,[{'name':'direct','linkers':['','']}])[0]
        out=export_variant(v,self.root/'exports')
        def inference_stub(cmd,log):
            dest=Path(cmd[cmd.index('--out_dir')+1])/'arbitrary_model_0.cif';dest.write_text('synthetic filename only')
        with patch('trivalent_pipeline.runtime.checked',side_effect=inference_stub):
            r=predict_boltz({'boltz_bin':'unused'},out,samples=1)
        self.assertEqual([x['role'] for x in r],['cassette_alone','joint'])
        with patch('trivalent_pipeline.runtime.checked'):
            with self.assertRaises(RuntimeError):predict_boltz({'boltz_bin':'unused'},self.root/'missing',samples=1)
    def test_canonical_import_and_direct_junction(self):
        v=build_cassettes(self.arms,[{'name':'direct','linkers':['','']}])[0]
        out=export_variant(v,self.root/'exports');p=self.root/'fused.pdb'
        lines,_=atom_rows(v['sequence'],'X')
        p.write_text(''.join(lines)+'END\n')
        r=import_prediction(v,out,p,{'cassette':'X'},role='cassette_alone',provider='synthetic')
        self.assertEqual(r['peptide_bond_outliers'],[])
        self.assertEqual(r['missing_junction_positions'],[])
        self.assertEqual(r['status'],'NO_LISTED_GEOMETRIC_DEFECT_DETECTED')
        view=list((out/'predictions').glob('*.cif'))[0]
        self.assertEqual(chain_data(load_structure(view),'A')['sequence'],v['sequence'])
        with self.assertRaises(ValueError):import_prediction(v,out,p,{'cassette':'X'},role='cassette_alone')

class PolymerTests(unittest.TestCase):
    def test_finite_support_and_normalized_density(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'avidity_sim'))
        from avidity.tether import wlc, Chain, Gaussian
        from trivalent_pipeline.polymer import ideal_ceff, closure_from_joint
        chain=wlc(8.,.5)
        for d in (8.,8.1,100.):self.assertEqual(ideal_ceff(chain,d)[0],0.)
        c,diag=ideal_ceff(chain,2.)
        self.assertGreater(c,0.);self.assertAlmostEqual(diag['retained_mass_before_renormalization'],1.,places=3)
        with self.assertRaises(ValueError):ideal_ceff(Chain.of(Gaussian(5)),2.)
        self.assertEqual(closure_from_joint({'linkers':['','']},'unused',{})['status'],'NOT_APPLICABLE')

class ThermodynamicTests(unittest.TestCase):
    k=[1e-6,2e-6,3e-6]
    j={'12':1e-4,'13':8e-5,'23':2e-4,'123':2e-8}
    def test_all_15_disjoint_configurations(self):
        c=configurations();self.assertEqual(len(c),15)
        for blocks in c:
            flat=[i for b in blocks for i in b];self.assertEqual(len(flat),len(set(flat)))
    def test_nonbinding_linkers_reduce_to_independent_langmuir(self):
        c=4e-6;r=fixed_patch_equilibrium(self.k,c,dict.fromkeys(self.j,0.))
        np.testing.assert_allclose(r['receptor_occupancy'],[c/(c+k) for k in self.k])
        self.assertEqual(r['p_one_cassette_bridges_all_three'],0)
        self.assertAlmostEqual(r['p_any_ligand_bound'],1-math.prod(k/(k+c) for k in self.k))
    def test_zero_concentration(self):
        r=fixed_patch_equilibrium(self.k,0,self.j)
        self.assertEqual(r['p_any_ligand_bound'],0);self.assertEqual(r['receptor_occupancy'],[0,0,0])
    def test_probability_normalization(self):
        for c in np.logspace(-15,2,12):
            r=fixed_patch_equilibrium(self.k,c,self.j)
            self.assertAlmostEqual(sum(x['probability'] for x in r['configurations']),1)
            self.assertTrue(all(0<=x<=1+1e-12 for x in r['receptor_occupancy']))
    def test_first_Kd_changes_full_probability(self):
        a=fixed_patch_equilibrium(self.k,1e-9,self.j)
        b=fixed_patch_equilibrium([1.,*self.k[1:]],1e-9,self.j)
        self.assertGreater(a['p_one_cassette_bridges_all_three'],b['p_one_cassette_bridges_all_three'])
    def test_high_dose_competition_hook(self):
        a=fixed_patch_equilibrium(self.k,1e-6,self.j)
        b=fixed_patch_equilibrium(self.k,1.,self.j)
        self.assertGreater(a['p_one_cassette_bridges_all_three'],b['p_one_cassette_bridges_all_three'])
        self.assertGreater(b['mean_cassettes_bound'],2.9)
    def test_standard_free_energy_sign(self):
        r=fixed_patch_equilibrium(self.k,1e-6,self.j)
        self.assertTrue(all(x<0 for x in r['monovalent_standard_dG_kJ_mol']))
    def test_missing_or_invalid_inputs(self):
        with self.assertRaises(ValueError):fixed_patch_equilibrium([0,*self.k[1:]],1e-6,self.j)
        with self.assertRaises(ValueError):fixed_patch_equilibrium(self.k,1e-6,{'12':1e-4})
        with self.assertRaises(ValueError):fixed_patch_equilibrium(self.k,float('nan'),self.j)
    def test_missing_scenario_stays_unavailable(self):
        self.assertEqual(evaluate_scenario({'id':'test'},None)['status'],'NOT_COMPUTED')
    def test_scenario_variant_binding(self):
        with self.assertRaises(ValueError):evaluate_scenario({'id':'real'},{'variant_id':'other'})

if __name__=='__main__':unittest.main()
