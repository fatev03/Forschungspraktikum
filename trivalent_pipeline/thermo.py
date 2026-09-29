"""Equilibrium of a fixed patch containing one receptor of each of three types.

Each ligand has exactly one domain for each target. A configuration is a set of
non-overlapping receptor subsets, each subset occupied by one cassette molecule.
All 15 configurations (including the empty patch) are enumerated. Positive state
weights define a common equilibrium distribution, not path-specific gains.

Closure factors J12,J13,J23 have units M; J123 has units M^2. They must come from
one declared model/ensemble or experiment for the actual cassette and patch.
They are NOT inferred from model confidence, PRODIGY, independent distance
extrema, or the geometric mean of two different linkers.
"""
import itertools, math
import numpy as np
from scipy.special import logsumexp
from .core import finite


def configurations():
    subsets=[tuple(i for i in range(3) if mask&(1<<i)) for mask in range(1,8)]
    result=[()]
    for n in range(1,4):
        for blocks in itertools.combinations(subsets,n):
            sites=[i for b in blocks for i in b]
            if len(sites)==len(set(sites)):result.append(blocks)
    return result


def fixed_patch_equilibrium(kd_M,concentration_M,closure,temperature_K=298.15):
    if len(kd_M)!=3:raise ValueError('Exactly three measured/declared Kd values required')
    k=[finite(v,'Kd_M',strict=True) for v in kd_M]
    c=finite(concentration_M,'ligand concentration');t=finite(temperature_K,'temperature K',strict=True)
    expected={'12','13','23','123'}
    if set(closure)!=expected:raise ValueError('Need J12,J13,J23 in M and J123 in M^2; no implicit triple factorization')
    j={key:finite(v,'closure '+key) for key,v in closure.items()}
    def log_block(b):
        if c==0:return -math.inf
        val=math.log(c)-sum(math.log(k[i]) for i in b)
        if len(b)>1:
            factor=j[''.join(str(i+1) for i in b)]
            if factor==0:return -math.inf
            val+=math.log(factor)
        return val
    configs=configurations()
    logs=np.array([sum(log_block(b) for b in blocks) for blocks in configs])
    logz=float(logsumexp(logs));probs=np.exp(logs-logz)
    rows=[]
    for blocks,p in zip(configs,probs):
        rows.append({'configuration':[list(i+1 for i in b) for b in blocks],
                     'probability':float(p),'ligands_bound':len(blocks),
                     'receptors_occupied':sum(map(len,blocks))})
    triple=sum(r['probability'] for r in rows if r['configuration']==[[1,2,3]])
    occupied=[sum(float(p) for blocks,p in zip(configs,probs) if any(i in b for b in blocks)) for i in range(3)]
    return {'concentration_M':c,'temperature_K':t,'partition_logZ':logz,'configurations':rows,
            'p_any_ligand_bound':1-float(probs[0]),'p_one_cassette_bridges_all_three':triple,
            'receptor_occupancy':occupied,'mean_cassettes_bound':sum(r['probability']*r['ligands_bound'] for r in rows),
            'monovalent_standard_dG_kJ_mol':[8.314462618e-3*t*math.log(x/1.) for x in k],
            'scope':'fixed patch with one of each receptor; free ligand reservoir; no lateral mobility or tissue selectivity',
            'assumptions':['all three domains remain binding-competent in the fused cassette',
                           'one binding site per target; intended specificity only, cross-binding excluded',
                           'supplied Kd values apply to the fused domains under the declared conditions',
                           'ideal free ligand activity approximated by molar concentration; no ligand depletion',
                           'closure factors encode a single declared equilibrium model; not kinetic rates'],
            'reference_state':'Kd/1 M; Kd values apply at supplied temperature/pH/assay conditions'}


def evaluate_scenario(variant,scenario):
    if not scenario:return {'status':'NOT_COMPUTED','reason':'No explicit Kd and closure-factor scenario'}
    if scenario.get('variant_id')!=variant['id']:raise ValueError('Thermodynamic scenario must bind to this exact variant_id')
    if scenario.get('target_order')!=variant['order']:raise ValueError('Kd and closure labels must match cassette target_order')
    if not scenario.get('source_note'):raise ValueError('Declare source/assumptions for Kd and closure factors')
    if scenario.get('evidence_kind') not in ('measured_inputs','model_scenario'):
        raise ValueError('evidence_kind must identify measured_inputs or model_scenario')
    if not scenario.get('concentrations_M'):raise ValueError('Nonempty concentration series required')
    if scenario.get('kd_temperature_K')!=scenario.get('temperature_K'):
        raise ValueError('Kd reference temperature must match calculation temperature; no implicit extrapolation')
    rows=[fixed_patch_equilibrium(scenario['kd_M'],c,scenario['closure_factors'],scenario['temperature_K'])
          for c in scenario['concentrations_M']]
    return {'status':'CONDITIONAL_MODEL_RESULT','scenario':scenario,'rows':rows,
            'biological_claims_not_established':['cell_selectivity','activation','inhibition','toxicity','in_vivo_efficacy']}
