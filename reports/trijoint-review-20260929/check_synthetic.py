"""Independent synthetic checks. Fixtures are geometric toys, not protein models."""
import contextlib, io, json, math, tempfile
from pathlib import Path
SRC=Path(__file__).with_name('trijoint_submitted.py').read_text()
def load(spec,links='25,25',kds='500,2000,5000',spacing='5,10'):
 ns={'__name__':'review'}
 exec(compile(SRC.replace('TRIJOINT = run()',''),'trijoint_submitted.py','exec'),ns)
 ns.update(pair_specs=spec,linker_lengths=links,kd_mono_nM=kds,spacing_nm=spacing)
 return ns

def run(ns):
 with contextlib.redirect_stdout(io.StringIO()):return ns['run']()
def pdb_atom(i,ch,res,xyz):
 x,y,z=xyz
 return f'ATOM  {i:5d}  CA  ALA {ch}{res:4d}    {x:8.3f}{y:8.3f}{z:8.3f}{1.:6.2f}{90.:6.2f}           C\n'

with tempfile.TemporaryDirectory() as td:
 td=Path(td)
 tgt=[(0,0,z) for z in (0,2,4,6)]
 bnd=[(6,0,z) for z in (0,2,4,6)]+[(x,9,7) for x in (14,16,18,20,22,24)]
 raw=''.join(pdb_atom(i+1,'A',i+1,v) for i,v in enumerate(tgt))+''.join(pdb_atom(i+5,'B',i+1,v) for i,v in enumerate(bnd))
 p=td/'pair.pdb';p.write_text(raw+'END\n')
 spec=';'.join(f'{name}:{p}:A:B' for name in ('GIPR','GLP1R','GCGR'))
 ns=load(spec);a=ns['analyse_pair']({'name':'t','pdb':str(p),'tgt':'A','bnd':'B'},8.)
 assert a['nres']==10 and a['iface_res']==4
 assert abs(a['n_off']-3)<1e-9 and abs(a['c_off']-math.sqrt(421))<1e-9
 assert a['n_to_tgt']==6 and a['n_outward']<-.9 and a['c_outward']>.9 and a['clash_atoms']==0
 assert abs(ns['MSQ_PREFACTOR']-6*1.927**2)<1e-9
 assert abs(ns['coil_span'](ns['optimal_linker'](60.))-60.)<1e-9
 r=run(ns);rows={x['spacing (nm)']:x for x in r['rows']}
 assert rows[5.]['all linkers reach (worst case)']=='yes'
 assert rows[10.]['all linkers reach (worst case)']=='NO'
 assert rows[10.]['trivalent gain, worst']==0
 assert rows[5.]['trivalent gain, best']>rows[5.]['trivalent gain, worst']>=0
 off=a['n_off']+a['c_off'];cb=float(ns['ceff_molar'](50-off,25));cw=float(ns['ceff_molar'](50+off,25))
 assert abs(r['CEFF_M']-cb)/cb<1e-12
 assert r['ARM_REACH_WITH_BODY_NM']>r['ARM_REACH_NM']>0
 out={'baseline_geometry':a,'rows':r['rows'], 'export_best_Ceff_uM':cb*1e6,'actual_worst_Ceff_uM':cw*1e6,'export_over_worst_factor':cb/cw}
 # First affinity is unused in gain computation.
 r2=run(load(spec,kds='500000,2000,5000'))
 assert r2['rows']==r['rows'];out['first_Kd_1000x_change_leaves_gain_identical']=True
 # Out-of-contour best-case Gaussian tails still exported.
 far=run(load(spec,spacing='12'))
 assert far['rows'][0]['_detail'][0]['gap best (A)']>87.5
 assert far['CEFF_M']>0
 out['unreachable_best_gap_export']={'gap_A':far['rows'][0]['_detail'][0]['gap best (A)'],'contour_A':87.5,'Ceff_M':far['CEFF_M']}
 # Missing interface: no admission gate, replaced by whole-chain centroid.
 q=td/'separated.pdb';q.write_text(''.join(pdb_atom(i+1,'A',i+1,(x+1000,y,z)) for i,(x,y,z) in enumerate(tgt))+''.join(pdb_atom(i+5,'B',i+1,v) for i,v in enumerate(bnd)))
 qspec=';'.join(f'{name}:{q}:A:B' for name in ('GIPR','GLP1R','GCGR'))
 sep=run(load(qspec,spacing='5'));assert all(a['iface_res']==0 for a in sep['arms'])
 out['no_interface_still_scored']={'iface_res':[a['iface_res'] for a in sep['arms']], 'gain':sep['rows'][0]['trivalent gain, best']}
 # Multi-model records are mixed, so the last model provides the C terminus.
 multi=td/'multi.pdb';multi.write_text('MODEL        1\n'+raw+'ENDMDL\nMODEL        2\n'+raw+'ENDMDL\nEND\n')
 out['two_model_binder_CA_count']=ns['read_chains'](multi)['B']['nres']
 assert out['two_model_binder_CA_count']==20
 # Scalar distance envelopes are not the exact minimum if one offset dominates.
 s,aa,bb=5.,30.,2.
 out['distance_min_counterexample']={'spacing_A':s,'offsets_A':[aa,bb],'implemented_min_A':max(s-aa-bb,0.),'exact_free_rotation_min_A':max(0.,s-aa-bb,aa-s-bb,bb-s-aa)}
 # Original count and parsing error guards.
 checks=[(load(spec,links='25')['run'],'linkers'),(load(spec,kds='500,2000')['run'],'Kd values'),(load(f'GIPR:{p}:A:Z',links='',kds='500')['run'],'chain Z'),(lambda:ns['parse_pairs'](f'GIPR:{p}:A'),'name:pdb')]
 for fn,msg in checks:
  try:
   with contextlib.redirect_stdout(io.StringIO()):fn()
  except ValueError as e:assert msg in str(e)
  else:raise AssertionError(msg)
 one=run(load(f'GIPR:{p}:A:B',links='',kds='500'))
 assert one['rows'][0]['trivalent gain, best']==1.
 out['baseline_checks_and_four_error_guards']='passed'
 # Validate biological input guard gaps without changing the submitted code.
 fractional=run(load(spec,links='25.9,25.9',spacing='5'))
 out['fractional_linker_silently_truncated_to']=fractional['rows'][0]['_detail'][0]['residues']
 neg=run(load(spec,spacing='-5'))
 out['negative_spacing_accepted']=neg['spacing_nm']
 Path(__file__).with_name('results.json').write_text(json.dumps(out,indent=2))
 print(json.dumps({k:v for k,v in out.items() if k not in ('baseline_geometry','rows')},indent=2))
