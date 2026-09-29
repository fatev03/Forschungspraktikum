"""Parameter estimation and held-out-data guards; all values are synthetic."""
import copy, csv, json, tempfile, unittest
from pathlib import Path
import numpy as np
from trivalent_pipeline.calibration import *


def fixture(observable='p_one_cassette_bridges_all_three'):
    variant={'id':'cassette_test','order':['R1','R2','R3']}
    context={'temperature_K':298.15,'pH':7.4,'ionic_strength_M':.15,
             'construct_note':'synthetic three-domain cassette and three fixed receptors','geometry_id':'synthetic_patch'}
    baseline={'variant_id':variant['id'],'target_order':variant['order'],'kd_M':[1e-6,2e-6,3e-6],
              'closure_factors':{'12':1e-4,'13':8e-5,'23':2e-4,'123':3e-9},
              'temperature_K':298.15,'kd_temperature_K':298.15,'calibration_context':context,
              'source_note':'theory for software testing only','evidence_kind':'model_scenario','concentrations_M':[1e-9,1e-6,1e-3]}
    metadata={'variant_id':variant['id'],'target_order':variant['order'],'condition_id':'test',
              'conditions':context,'source_note':'synthetic data, no experiment','sources':{'S1':'synthetic fixture'},
              'data_independence_note':'separate artificial observations','affinity_transfer_assumption':'assumed for this software test',
              'error_model':'independent_gaussian_known_sd','equilibrium_confirmed':True,'concentration_basis':'free',
              'system':'fixed_patch_one_receptor_each','evidence_kind':'synthetic_test'}
    truth=parameters_from_scenario(baseline);truth['J123_M2']=2e-8
    rows=[]
    for split,grid in [('train',np.logspace(-10,-3,12)),('validation',np.logspace(-9.5,-3.5,7))]:
        for i,c in enumerate(grid):
            rows.append({'measurement_id':f'{split}_{i}','experiment_id':split+'_run','source_id':'S1','condition_id':'test',
                         'split':split,'observable':observable,'concentration_M':float(c),'value':0.,'sd':.01})
    for row,value in zip(rows,predict_observations(truth,rows,298.15)):row['value']=float(value)
    return variant,baseline,rows,metadata,truth


class CalibrationTests(unittest.TestCase):
    def fit(self,rows=None,metadata=None,baseline=None,names=None,bounds=None):
        v,b,r,m,_=fixture()
        return fit_calibration(v,baseline or b,r if rows is None else rows,metadata or m,
                               names or ['J123_M2'],bounds or {'J123_M2':[1e-12,1e-5]},n_starts=3)
    def test_recover_known_closure_and_interval(self):
        r=self.fit()
        self.assertTrue(r['eligible_for_auto_use'],r['warnings'])
        self.assertAlmostEqual(r['fitted_parameters']['J123_M2']/2e-8,1.,places=5)
        a,b=r['intervals']['J123_M2']['approx_95_interval'];self.assertLess(a,2e-8);self.assertGreater(b,2e-8)
        self.assertLess(r['validation']['chi2'],r['validation']['baseline_chi2'])
    def test_validation_never_changes_fit(self):
        v,b,rows,m,_=fixture();good=self.fit()
        for row in rows:
            if row['split']=='validation':row['value']=0.
        bad=self.fit(rows=rows)
        self.assertAlmostEqual(good['fitted_parameters']['J123_M2'],bad['fitted_parameters']['J123_M2'],places=15)
        self.assertFalse(bad['eligible_for_auto_use']);self.assertIn('VALIDATION_MODEL_OR_ERROR_MISMATCH',bad['warnings'])
        self.assertEqual(select_scenario(b,bad),b)
    def test_no_validation_no_automatic_update(self):
        _,_,r,_,_=fixture();r=[x for x in r if x['split']=='train']
        fit=self.fit(rows=r);self.assertFalse(fit['eligible_for_auto_use']);self.assertIn('NO_INDEPENDENT_VALIDATION',fit['warnings'])
    def test_same_experiment_leakage_refused(self):
        _,_,r,_,_=fixture();r[-1]['experiment_id']=r[0]['experiment_id']
        with self.assertRaisesRegex(ValueError,'leakage'):self.fit(rows=r)
    def test_duplicate_and_wrong_units_refused(self):
        _,_,r,_,_=fixture();r[-1]['measurement_id']=r[0]['measurement_id']
        with self.assertRaisesRegex(ValueError,'Duplicate'):self.fit(rows=r)
        _,_,r,_,_=fixture();r[0]['observable']='EC50_nM'
        with self.assertRaisesRegex(ValueError,'Unsupported'):self.fit(rows=r)
    def test_conditions_and_temperature_refused(self):
        _,_,_,m,_=fixture();m=copy.deepcopy(m);m['conditions']['temperature_K']=310.
        with self.assertRaisesRegex(ValueError,'Temperature'):self.fit(metadata=m)
        _,_,r,_,_=fixture();r[-1]['condition_id']='different_buffer'
        with self.assertRaisesRegex(ValueError,'Mixed conditions'):self.fit(rows=r)
    def test_unknown_error_and_total_concentration_refused(self):
        _,_,_,m,_=fixture();m['concentration_basis']='total'
        with self.assertRaisesRegex(ValueError,'Free ligand'):self.fit(metadata=m)
        _,_,r,_,_=fixture();r[0]['sd']=0.
        with self.assertRaises(ValueError):self.fit(rows=r)
    def test_nonidentifiability_with_total_occupancy(self):
        v,b,r,m,truth=fixture('p_any_ligand_bound');b['kd_M']=[1e-6]*3
        truth=parameters_from_scenario(b);truth.update(J12_M=3e-4,J13_M=2e-4,J23_M=1e-4)
        for row,y in zip(r,predict_observations(truth,r,298.15)):row['value']=float(y)
        names=['J12_M','J13_M','J23_M']
        fit=fit_calibration(v,b,r,m,names,{n:[1e-7,1e-2] for n in names},n_starts=3)
        self.assertIn('PARAMETERS_NOT_SEPARATELY_IDENTIFIABLE',fit['warnings'])
        self.assertEqual(fit['intervals'],{});self.assertFalse(fit['eligible_for_auto_use'])
    def test_known_sd_weighted_mean(self):
        v,b,_,m,_=fixture();b['kd_M'][0]=3e-6
        ys=[1e-6,2e-6,2.5e-6];sd=[1e-8,1e-6,1e-6]
        mean=float(np.average(ys,weights=1/np.square(sd)))
        rows=[]
        for i,(value,sigma) in enumerate(zip(ys+[mean]*3,sd+[1e-8]*3)):
            split='train' if i<3 else 'validation'
            rows.append(dict(zip(FIELDS,[str(i),split,'S1','test',split,'kd_1_M',None,value,sigma])))
        fit=fit_calibration(v,b,rows,m,['kd_1_M'],{'kd_1_M':[1e-8,1e-4]},n_starts=3)
        self.assertAlmostEqual(fit['fitted_parameters']['kd_1_M']/mean,1.,places=6)
    def test_fixed_zeros_and_positive_bounds(self):
        _,b,_,_,_=fixture();b['closure_factors']['123']=0.
        with self.assertRaisesRegex(ValueError,'fixed zero'):self.fit(baseline=b)
    def test_revision_snapshots_and_activation(self):
        v,b,rows,m,_=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cp,mp=write_templates(root,v);mp.write_text(json.dumps(m))
            with cp.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
            args=(v,b,cp,mp,['J123_M2'],{'J123_M2':[1e-12,1e-5]},root/'history')
            r1,d1=calibrate_files(*args,n_starts=2);r2,d2=calibrate_files(*args,n_starts=2)
            self.assertNotEqual(d1,d2);self.assertTrue((d1/'calibration.json').is_file())
            self.assertEqual(r1['source_hashes'],r2['source_hashes'])
            self.assertEqual(select_scenario(b,r1)['calibration_id'],r1['calibration_id'])
            self.assertEqual(select_scenario(b,r1,False),b)
            b2=copy.deepcopy(b);b2['kd_M'][0]*=2
            with self.assertRaisesRegex(ValueError,'changed'):select_scenario(b2,r1)

if __name__=='__main__':unittest.main()
