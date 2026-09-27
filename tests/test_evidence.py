from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from structure_audit.evidence import CandidateEvidence, sequence_hash, supplied_metric, filter_candidates
from structure_audit.adapters import import_mpnn_csv, import_boltz_confidence
from structure_audit.provenance import hash_file
from helpers import FIXTURES

PROV={'model_id':'supplied-fixture-id','checkpoint_id':None,'seed':None}
SOURCE={'path':str(FIXTURES/'confidence.json'),'sha256':hash_file(FIXTURES/'confidence.json'),'row':None}


class EvidenceTest(unittest.TestCase):
    def candidate(self,raw=0.7):
        metric=supplied_metric('iptm',raw,context='complex',category='model_confidence',source=SOURCE,provenance=PROV)
        return CandidateEvidence('fixture',None,'supplied-target','supplied-conformer',[metric],PROV,
                                 missing_values={'sequence_hash':'no sequence supplied for geometric fixture'})

    def test_raw_values_categories_and_missing(self):
        for raw in ('0.70',None,'NaN',{'A':{'B':0.7}}):
            data=self.candidate(raw).to_dict()
            self.assertEqual(data['metrics'][0]['raw_value'],raw)
            self.assertEqual(data['metrics'][0]['category'],'model_confidence')
            if raw!='0.70':
                self.assertIsNone(data['metrics'][0]['value'])
                self.assertTrue(data['metrics'][0]['missing_reason'])
        self.assertNotIn('final_score',self.candidate().to_dict())

    def test_sequence_hash_exact_text(self):
        self.assertNotEqual(sequence_hash('G'),sequence_hash('g'))
        self.assertEqual(sequence_hash('G'),sequence_hash('G'))

    def test_missing_identity_reason_required(self):
        candidate=self.candidate();candidate.missing_values={}
        with self.assertRaises(ValueError):
            candidate.to_dict()

    def test_duplicate_metric_rejected(self):
        candidate=self.candidate();candidate.metrics*=2
        with self.assertRaises(ValueError):
            candidate.to_dict()

    def test_filter_bounds_without_composite(self):
        rules=[{'context':'complex','name':'iptm','min':0.8}]
        result=filter_candidates([self.candidate()],rules)
        self.assertFalse(result[0]['accepted'])
        self.assertTrue(result[0]['reasons'])
        self.assertEqual(self.candidate().metrics[0]['value'],0.7)

    def test_filter_missing_policies(self):
        rules=[{'context':'counter_screen','name':'iptm','max':0.3}]
        self.assertFalse(filter_candidates([self.candidate()],rules)[0]['accepted'])
        self.assertTrue(filter_candidates([self.candidate()],rules,missing='include')[0]['accepted'])
        with self.assertRaises(ValueError):
            filter_candidates([self.candidate()],rules,missing='error')

    def test_metric_contexts_not_conflated(self):
        candidate=self.candidate()
        candidate.metrics.append(supplied_metric('iptm',0.2,context='counter_screen',category='model_confidence',source=SOURCE,provenance=PROV))
        rules=[{'context':'complex','name':'iptm','min':0.6},{'context':'counter_screen','name':'iptm','max':0.3}]
        self.assertTrue(filter_candidates([candidate],rules)[0]['accepted'])

    def test_invalid_metric_and_rules_rejected(self):
        candidate=self.candidate();candidate.metrics[0]['context']='inferred'
        with self.assertRaises(ValueError):
            candidate.to_dict()
        for rule in ({'context':'complex','name':'iptm','min':float('nan')},{'context':'complex','name':'iptm','min':1,'max':0}):
            with self.assertRaises(ValueError):
                filter_candidates([self.candidate()],[rule])

    def test_boltz_nested_values_preserved(self):
        metrics=import_boltz_confidence(FIXTURES/'confidence.json',provenance=PROV)
        nested=next(m for m in metrics if m['name']=='pair_chains_iptm')
        self.assertEqual(nested['raw_value'],{'A':{'B':0.7}})
        self.assertIsNone(nested['value'])
        self.assertEqual(nested['source']['sha256'],SOURCE['sha256'])

    def test_mpnn_explicit_roles_and_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'supplied.csv'
            # Single-residue labels exercise bookkeeping; no designed sequence.
            path.write_text('design,n,seq,mpnn,plddt,i_ptm,i_pae,rmsd,extra\n0,0,G/G,1.2,0.8,0.7,,1.0,raw\n')
            kwargs=dict(target_id='target',conformer_id='conformer',chain_roles=['target','candidate'],
                        provenance=PROV,metric_contexts={k:'complex' for k in ('mpnn','plddt','i_ptm','i_pae','rmsd')})
            candidate=import_mpnn_csv(path,**kwargs)[0]
            self.assertEqual(candidate.sequence_hash,sequence_hash('G'))
            self.assertEqual(candidate.metrics[0]['raw_value'],'1.2')
            self.assertEqual(candidate.metrics[-1]['context'],'unassigned')
            self.assertEqual(candidate.metrics[-1]['raw_value'],{'extra':'raw'})
            with self.assertRaises(ValueError):
                import_mpnn_csv(path,**{**kwargs,'chain_roles':['candidate']})

    def test_no_inference_imports(self):
        import sys
        for mod in ('torch','jax','colabdesign','pyrosetta','boltz'):
            self.assertNotIn(mod,sys.modules)
