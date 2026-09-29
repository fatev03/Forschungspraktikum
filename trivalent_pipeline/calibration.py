"""Explicit, versioned calibration of the fixed-patch equilibrium model.

Weighted least squares with declared independent Gaussian measurement errors.
Positive free parameters are optimized in log10 space; fixed zero closures stay
zero. Local covariance intervals are conditional on the model and fixed inputs,
not Bayesian posteriors or a proof of global identifiability. Validation data
never enter optimization. No web scraping or silent literature pooling.
"""
from __future__ import annotations
import copy, csv, datetime, hashlib, io, json, math, platform, uuid
from pathlib import Path
import numpy as np
import scipy
from scipy.optimize import least_squares
from scipy.stats import chi2
from .core import finite, digest, write_json
from .thermo import fixed_patch_equilibrium

PARAMETERS=('kd_1_M','kd_2_M','kd_3_M','J12_M','J13_M','J23_M','J123_M2')
PATCH_OBSERVABLES=('p_any_ligand_bound','p_one_cassette_bridges_all_three',
                   'receptor_1_occupancy','receptor_2_occupancy','receptor_3_occupancy','mean_cassettes_bound')
MONO_OBSERVABLES=('mono_1_fraction','mono_2_fraction','mono_3_fraction')
OBSERVABLES=PARAMETERS+PATCH_OBSERVABLES+MONO_OBSERVABLES
FIELDS=('measurement_id','experiment_id','source_id','condition_id','split','observable','concentration_M','value','sd')


def parameters_from_scenario(scenario):
    k=scenario['kd_M'];j=scenario['closure_factors']
    fixed_patch_equilibrium(k,0.,j,scenario['temperature_K'])
    return dict(zip(PARAMETERS,map(float,[*k,j['12'],j['13'],j['23'],j['123']])))


def predict_observations(parameters,rows,temperature_K):
    k=[parameters[x] for x in PARAMETERS[:3]]
    j=dict(zip(('12','13','23','123'),[parameters[x] for x in PARAMETERS[3:]]))
    cache={};out=[]
    for r in rows:
        obs=r['observable']
        if obs in PARAMETERS:value=parameters[obs]
        elif obs in MONO_OBSERVABLES:
            c=r['concentration_M'];value=c/(c+k[int(obs[5])-1])
        else:
            c=r['concentration_M']
            if c not in cache:cache[c]=fixed_patch_equilibrium(k,c,j,temperature_K)
            state=cache[c]
            value=state['receptor_occupancy'][int(obs[9])-1] if obs.startswith('receptor_') else state[obs]
        out.append(value)
    return np.asarray(out,dtype=float)


def validate_data(variant,baseline,rows,metadata):
    if baseline.get('variant_id')!=variant['id'] or baseline.get('target_order')!=variant['order']:
        raise ValueError('Baseline must refer to this exact cassette variant and target order')
    if metadata.get('variant_id')!=variant['id'] or metadata.get('target_order')!=variant['order']:
        raise ValueError('Data metadata must refer to this exact cassette variant and target order')
    for key in ('condition_id','source_note','data_independence_note','affinity_transfer_assumption'):
        if not isinstance(metadata.get(key),str) or not metadata[key].strip():raise ValueError('Declare '+key)
    if metadata.get('error_model')!='independent_gaussian_known_sd':
        raise ValueError('This fitter requires independent_gaussian_known_sd; sd is the standard error of each supplied estimate')
    if metadata.get('equilibrium_confirmed') is not True:raise ValueError('Equilibrium must be established for these measurements')
    if metadata.get('concentration_basis')!='free':raise ValueError('Free ligand concentration required; total added concentration is not silently substituted')
    if metadata.get('evidence_kind') not in ('experimental','synthetic_test'):
        raise ValueError('Declare experimental or synthetic_test evidence')
    context=metadata['conditions']
    for key in ('temperature_K','pH','ionic_strength_M'):
        value=finite(context[key],key,strict=key=='temperature_K')
        if key=='pH' and value>14:raise ValueError('pH outside supported range 0..14')
    if context['temperature_K']!=baseline['temperature_K'] or context['temperature_K']!=baseline['kd_temperature_K']:
        raise ValueError('Temperature mismatch; no implicit Kd extrapolation')
    # The baseline must explicitly apply to the same buffer and construct/geometry context.
    if baseline.get('calibration_context')!=context:raise ValueError('Baseline calibration_context must match the complete declared data conditions')
    if not context.get('construct_note'):raise ValueError('Declare construct_note, including binder/receptor identity and relevant PTMs')
    parameters_from_scenario(baseline)
    if not rows:raise ValueError('No measurements supplied')
    sources=metadata.get('sources',{});seen=set();experiments={};clean=[]
    for row in rows:
        r=dict(row)
        if set(r)!=set(FIELDS):raise ValueError('Measurement columns must match '+','.join(FIELDS))
        for key in ('measurement_id','experiment_id','source_id'):
            if not isinstance(r[key],str) or not r[key].strip():raise ValueError('Missing '+key)
        if r['measurement_id'] in seen:raise ValueError('Duplicate measurement_id; do not count the same evidence twice')
        seen.add(r['measurement_id'])
        source=sources.get(r['source_id'])
        if not isinstance(source,str) or not source.strip():raise ValueError('Each source_id requires a citation or laboratory record in metadata.sources')
        if r['condition_id']!=metadata['condition_id']:raise ValueError('Mixed conditions: calibrate different buffers/geometries separately')
        if r['split'] not in ('train','validation'):raise ValueError('split must be train or validation')
        old=experiments.setdefault(r['experiment_id'],r['split'])
        if old!=r['split']:raise ValueError('Experiment leakage: one experiment cannot occur in train and validation')
        obs=r['observable']
        if obs not in OBSERVABLES:raise ValueError('Unsupported observable: '+str(obs)+'; raw SPR/BLI/RFU, EC50, apparent Kd and koff need their own observation model')
        r['value']=finite(r['value'],'measurement value');r['sd']=finite(r['sd'],'measurement sd',strict=True)
        if obs.startswith('kd_') and r['value']==0:raise ValueError('Measured Kd must be positive')
        if obs in PATCH_OBSERVABLES+MONO_OBSERVABLES:
            r['concentration_M']=finite(r['concentration_M'],'free concentration')
            limit=3. if obs=='mean_cassettes_bound' else 1.
            if r['value']>limit:raise ValueError('Observation outside its physical range')
        elif r['concentration_M'] not in ('',None):
            raise ValueError('Direct parameter observations must leave concentration_M empty')
        else:r['concentration_M']=None
        clean.append(r)
    if any(r['observable'] in PATCH_OBSERVABLES for r in clean):
        if metadata.get('system')!='fixed_patch_one_receptor_each' or not context.get('geometry_id'):
            raise ValueError('Patch occupancy needs a declared fixed one-of-each receptor patch and geometry_id; bulk cell binding is not this observable')
    return clean


def _jacobian(fn,x):
    # Explicit central log10 perturbation gives reproducible local rank diagnostics.
    h=1e-4;columns=[]
    for i in range(len(x)):
        delta=np.zeros(len(x));delta[i]=h
        columns.append((fn(x+delta)-fn(x-delta))/(2*h))
    return np.column_stack(columns)


def _rank(jac):
    _,s,vt=np.linalg.svd(jac,full_matrices=False)
    rank=int(np.sum(s>max(float(s[0])*1e-6,1e-10))) if len(s) else 0
    condition=float(s[0]/s[-1]) if len(s) and s[-1]>0 else None
    return rank,s,vt,condition


def fit_calibration(variant,baseline,rows,metadata,fit_parameters,bounds,n_starts=5,seed=0):
    rows=validate_data(variant,baseline,rows,metadata)
    names=list(fit_parameters)
    if not names or len(set(names))!=len(names) or any(n not in PARAMETERS for n in names):raise ValueError('Choose distinct supported fit_parameters')
    if set(bounds)!=set(names):raise ValueError('Explicit positive lower/upper bounds required for every fitted parameter only')
    if type(n_starts)!=int or not 2<=n_starts<=20:raise ValueError('n_starts must be 2..20')
    initial=parameters_from_scenario(baseline);lo=[];hi=[]
    for name in names:
        a,b=[finite(v,'parameter bound',strict=True) for v in bounds[name]]
        if not a<initial[name]<b:raise ValueError('Initial value must be strictly within positive bounds for '+name+'; a fixed zero cannot be log-fitted')
        lo.append(math.log10(a));hi.append(math.log10(b))
    lo=np.array(lo);hi=np.array(hi);x0=np.log10([initial[n] for n in names])
    train=[r for r in rows if r['split']=='train'];validation=[r for r in rows if r['split']=='validation']
    if len(train)<=len(names):raise ValueError('More independent training observations than fitted parameters are required')
    def unpack(x):return dict(initial,**dict(zip(names,map(float,10.**x))))
    def residual(x,data):
        return (predict_observations(unpack(x),data,baseline['temperature_K'])-np.array([r['value'] for r in data]))/np.array([r['sd'] for r in data])
    rng=np.random.default_rng(seed);starts=[x0]+[rng.uniform(lo,hi) for _ in range(n_starts-1)]
    fits=[least_squares(lambda x:residual(x,train),s,bounds=(lo,hi),jac='3-point',
                        loss='linear',max_nfev=2500,ftol=1e-10,xtol=1e-10,gtol=1e-10) for s in starts]
    successes=[f for f in fits if f.success and np.isfinite(f.fun).all()]
    best=min(successes or fits,key=lambda f:float(np.dot(f.fun,f.fun)))
    x=best.x;params=unpack(x);train_chi2=float(best.fun@best.fun);dof=len(train)-len(names)
    jac=_jacobian(lambda v:residual(v,train),x);rank,s,vt,condition=_rank(jac)
    warnings=[]
    if not successes:warnings.append('OPTIMIZATION_FAILED')
    if rank<len(names):warnings.append('PARAMETERS_NOT_SEPARATELY_IDENTIFIABLE')
    boundary=np.minimum(x-lo,hi-x)<1e-3
    if boundary.any():warnings.append('PARAMETER_AT_BOUND')
    similar=[f for f in successes if float(f.fun@f.fun)<=train_chi2+1. and np.max(np.abs(f.x-x))>.5]
    if similar:warnings.append('MULTISTART_ALTERNATIVE_PARAMETERS')
    ptrain=float(chi2.sf(train_chi2,dof))
    if ptrain<.01:warnings.append('TRAINING_MODEL_OR_ERROR_MISMATCH')
    covariance=None;intervals={}
    if rank==len(names) and not boundary.any() and successes:
        cov=(vt.T/(s*s))@vt
        covariance=cov.tolist();se=np.sqrt(np.diag(cov))
        for i,n in enumerate(names):
            lower=float(x[i]-1.96*se[i]);upper=float(x[i]+1.96*se[i])
            intervals[n]={'estimate':params[n],'log10_standard_error':float(se[i]),
                'approx_95_interval':[10.**lower if lower>-300 else None,10.**upper if upper<300 else None]}
        if np.max(1.96*se)>1.:warnings.append('WIDE_LOCAL_UNCERTAINTY')
        if np.any(x-1.96*se<lo) or np.any(x+1.96*se>hi):warnings.append('LOCAL_INTERVAL_CROSSES_PARAMETER_BOUNDS')
    # Local intervals are withheld for rank deficiency; never pseudoinvert to invent precision.
    prediction=predict_observations(params,rows,baseline['temperature_K'])
    original=predict_observations(initial,rows,baseline['temperature_K'])
    prediction_rows=[dict(r,predicted=float(p),baseline_predicted=float(b),standardized_residual=float((p-r['value'])/r['sd']))
                     for r,p,b in zip(rows,prediction,original)]
    vstats={'n':len(validation),'status':'NOT_PROVIDED'}
    if validation:
        rv=residual(x,validation);r0=residual(x0,validation);vchi=float(rv@rv);bchi=float(r0@r0)
        vjac=_jacobian(lambda v:residual(v,validation),x);vrank,_,_,_=_rank(vjac)
        pv=float(chi2.sf(vchi,len(validation)))
        # Conditional on fitted parameters and supplied errors; not a calibration-uncertainty predictive p-value.
        vstats={'n':len(validation),'status':'EVALUATED_ONLY','chi2':vchi,'baseline_chi2':bchi,
                'weighted_RMSE':math.sqrt(vchi/len(validation)),
                'conditional_residual_pvalue':pv,'local_sensitivity_rank':vrank,
                'scope':'conditional residual diagnostic, ignores fitted-parameter uncertainty'}
        if len(validation)<max(3,len(names)) or vrank<len(names):warnings.append('VALIDATION_INSUFFICIENT_SENSITIVITY')
        if pv<.01:warnings.append('VALIDATION_MODEL_OR_ERROR_MISMATCH')
        if vchi>bchi+1e-8:warnings.append('VALIDATION_WORSE_THAN_BASELINE')
    else:warnings.append('NO_INDEPENDENT_VALIDATION')
    calibration_id='cal_'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]
    candidate=copy.deepcopy(baseline)
    candidate['kd_M']=[params[n] for n in PARAMETERS[:3]]
    candidate['closure_factors']=dict(zip(('12','13','23','123'),[params[n] for n in PARAMETERS[3:]]))
    candidate['evidence_kind']='model_scenario'
    candidate['source_note']='Calibrated conditional model '+calibration_id+'; '+metadata['source_note']
    candidate['calibration_id']=calibration_id
    allowed=not warnings
    return {'calibration_id':calibration_id,'status':'CALIBRATED_CONDITIONAL_MODEL' if allowed else 'REVIEW_REQUIRED',
            'eligible_for_auto_use':allowed,'warnings':warnings,'variant_id':variant['id'],
            'metadata':copy.deepcopy(metadata),'baseline':copy.deepcopy(baseline),'candidate_scenario':candidate,
            'fit_parameters':names,'fixed_parameters':{n:v for n,v in initial.items() if n not in names},
            'bounds':bounds,'initial_parameters':initial,'fitted_parameters':params,'intervals':intervals,
            'interval_scope':'local Gaussian/Wald 95% intervals in log10 space; conditional on fixed parameters, known independent errors and model; not profile-likelihood or global intervals',
            'log10_covariance':covariance,'training':{'n':len(train),'dof':dof,'chi2':train_chi2,
                'conditional_residual_pvalue':ptrain,'weighted_RMSE':math.sqrt(train_chi2/len(train)),
                'local_jacobian_rank':rank,'jacobian_singular_values':s.tolist(),'jacobian_condition_number':condition},
            'validation':vstats,'predictions':prediction_rows,
            'optimization':{'successful_starts':len(successes),'n_starts':n_starts,'seed':seed,
                'costs':[float(f.fun@f.fun) for f in fits]},
            'diagnostic_rules':{'residual_pvalue_min':.01,'relative_jacobian_rank_cutoff':1e-6,
                'absolute_jacobian_rank_cutoff':1e-10,'bound_distance_log10':1e-3,
                'max_local_95_halfwidth_log10':1.,'minimum_validation_rows':max(3,len(names)),
                'validation_requires_full_local_sensitivity_rank':True,'validation_must_not_worsen_chi2':True},
            'software':{'python':platform.python_version(),'numpy':np.__version__,'scipy':scipy.__version__,
                        'calibration_source_sha256':digest(__file__)},
            'scope':'updates declared equilibrium parameters only; no receptor-density, kinetic, functional or in-vivo inference'}


def calibrate_files(variant,baseline,csv_path,metadata_path,fit_parameters,bounds,output_root,**kwargs):
    """Every run uses the entire cumulative CSV and saves a new immutable snapshot."""
    csv_bytes=Path(csv_path).read_bytes();metadata_bytes=Path(metadata_path).read_bytes()
    with io.StringIO(csv_bytes.decode('utf-8-sig'),newline='') as f:
        reader=csv.DictReader(f)
        if reader.fieldnames!=list(FIELDS):raise ValueError('CSV header must be '+','.join(FIELDS))
        rows=list(reader)
    metadata=json.loads(metadata_bytes)
    result=fit_calibration(variant,baseline,rows,metadata,fit_parameters,bounds,**kwargs)
    result['source_hashes']={'csv':hashlib.sha256(csv_bytes).hexdigest(),'metadata':hashlib.sha256(metadata_bytes).hexdigest()}
    out=Path(output_root)/result['calibration_id'];out.mkdir(parents=True,exist_ok=False)
    # Copy exact bytes for replay and audit; never overwrite an earlier fit or the input data.
    (out/'measurements.csv').write_bytes(csv_bytes)
    (out/'metadata.json').write_bytes(metadata_bytes)
    write_json(out/'calibration.json',result)
    write_json(out/'candidate_scenario.json',result['candidate_scenario'])
    write_json(out/'baseline_scenario.json',baseline)
    with open(out/'fitted_observations.csv','w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(result['predictions'][0]));writer.writeheader();writer.writerows(result['predictions'])
    return result,out


def select_scenario(baseline,result,auto_use=True):
    if result is None or not auto_use or not result['eligible_for_auto_use']:return copy.deepcopy(baseline)
    if result['baseline']!=baseline:raise ValueError('Calibration baseline changed; recalibrate rather than applying stale parameters')
    return copy.deepcopy(result['candidate_scenario'])


def write_templates(directory,variant):
    out=Path(directory);out.mkdir(parents=True,exist_ok=True)
    csvpath=out/'measurements_TEMPLATE.csv';metapath=out/'metadata_TEMPLATE.json'
    if not csvpath.exists():
        with open(csvpath,'w',newline='') as f:csv.writer(f).writerow(FIELDS)
    if not metapath.exists():write_json(metapath,{
        'variant_id':variant['id'],'target_order':variant['order'],'condition_id':'',
        'conditions':{'temperature_K':None,'pH':None,'ionic_strength_M':None,'construct_note':'','geometry_id':''},
        'source_note':'','sources':{},'data_independence_note':'','affinity_transfer_assumption':'',
        'error_model':'independent_gaussian_known_sd','equilibrium_confirmed':False,
        'concentration_basis':'free','evidence_kind':'experimental','system':'fixed_patch_one_receptor_each'})
    return csvpath,metapath
