"""Optional ideal-linker scenario evaluated in ONE joint coordinate frame.

The existing WLC-moment-matched FJC kernel is reused with an explicit hard
contour cutoff. Regularized numerical densities are approximations, not an
experimental Ceff. No computation for direct fusions or very short linkers.
"""
import math
import numpy as np
from .core import finite, load_structure, chain_data
from .export import inspect_prediction


def ideal_ceff(chain,distance_nm,resolution_nm=.15):
    """Regularized isotropic volume density, truncated and renormalized to contour.

    1 molecule/nm^3 = 1.660539067 M. This is not the shell density 4πr²P(r).
    """
    from avidity.tether import TetherGrid
    dist=finite(distance_nm,'distance');eps=finite(resolution_nm,'resolution',strict=True)
    if not math.isfinite(chain.contour):raise ValueError('Finite linker kernel required; no Gaussian fallback accepted')
    if dist>=chain.contour:return 0.,{'outside_contour':True}
    kernel=TetherGrid(chain,eps=eps,n_grid=16385)
    integrate=np.trapezoid if hasattr(np,'trapezoid') else np.trapz
    r=np.append(kernel.z[kernel.z<chain.contour],chain.contour)
    p=kernel.radial_density(r)
    mass=float(integrate(4*np.pi*r*r*p,r))
    if not math.isfinite(mass) or mass<=0:raise ValueError('Linker density normalization failed')
    return 1.660539067*float(kernel.radial_density(dist))/mass,{
        'retained_mass_before_renormalization':mass,'normalized_mass':1.,
        'regularization_nm':eps,'near_contour_extension':dist/chain.contour>.8}


def closure_from_joint(variant,path,chain_map,persistence_nm=.5,resolution_nm=.15,
                       contour_per_step_nm=.38,model_index=None):
    from avidity.tether import Chain, Rod, TetherGrid, wlc
    lp=finite(persistence_nm,'persistence length',strict=True)
    eps=finite(resolution_nm,'numerical resolution',strict=True)
    step=finite(contour_per_step_nm,'contour length per step',strict=True)
    if any(len(s)<10 for s in variant['linkers']):
        return {'status':'NOT_APPLICABLE','reason':'Direct/short linker: fit an explicit junction or ensemble; no flexible-polymer surrogate'}
    report=inspect_prediction(variant,path,chain_map,model_index=model_index)
    if report['status']!='NO_LISTED_GEOMETRIC_DEFECT_DETECTED':
        return {'status':'WITHHELD_STRUCTURE_REVIEW','reasons':report['reasons']}
    d=chain_data(load_structure(path,model_index),chain_map['cassette'],variant['sequence'])
    regions=[r for r in variant['regions'] if r['kind']=='binder']
    ends=[(d['ca'][r['start']-1]/10.,d['ca'][r['end']-1]/10.) for r in regions]
    links=[wlc((len(s)+1)*step,lp) for s in variant['linkers']]
    body=float(np.linalg.norm(ends[1][1]-ends[1][0]))
    bridges={'12':(links[0],float(np.linalg.norm(ends[1][0]-ends[0][1]))),
             '23':(links[1],float(np.linalg.norm(ends[2][0]-ends[1][1]))),
             '13':(Chain.of(links[0],Rod(body),links[1]),float(np.linalg.norm(ends[2][0]-ends[0][1])))}
    factors={};details={}
    for key,(chain,dist) in bridges.items():
        ce,norm=ideal_ceff(chain,dist,eps)
        factors[key]=ce
        details[key]={'distance_nm':dist,'contour_nm':chain.contour,'Ceff_M':ce,
                      'extension_fraction':dist/chain.contour,'normalization_diagnostic':norm}
    factors['123']=factors['12']*factors['23']
    return {'status':'IDEAL_CHAIN_SCENARIO_ONLY','variant_id':variant['id'],'target_order':variant['order'],
            'closure_factors':factors,'source_sha256':report['sha256'],'details':details,
            'parameters':{'persistence_nm':lp,'resolution_nm':eps,'CA_step_nm':step},
            'assumptions':['fixed predicted receptor patch, not a membrane population',
                'independent freely jointed ideal segments; WLC first two moments only',
                'unbound middle binder approximated as freely rotating N-C rod for J13',
                'J123 factorized as J12*J23 only under this explicit ideal-chain assumption',
                'binding orientation, excluded volume, membrane and glycans not integrated into Ceff',
                'linker sequence affects real persistence; supplied lp is a scenario parameter',
                'regularized density truncated at contour and renormalized; not exact WLC distribution',
                'near-contour regularized density is not a calibrated stretching free energy']}
