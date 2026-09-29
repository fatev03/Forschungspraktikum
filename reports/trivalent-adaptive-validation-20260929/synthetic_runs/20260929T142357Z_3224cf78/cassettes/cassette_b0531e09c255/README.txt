One cassette molecule has one binder per target.
cassette.fasta is one covalently continuous sequence. Empty linkers mean direct peptide fusion.
AlphaFold Server: upload alphafold_server_jobs.json (jobs may exceed server limits; select individual jobs).
Local AF3/AF3-ReD: prediction_inputs/*.af3.json; receptor MSAs need the AF3 data pipeline.
Boltz: prediction_inputs/*.boltz.yaml. MSA server sends receptor sequences to the service.
Run cassette_alone AND joint for each retained variant; test single-target and cross-target jobs separately.
Plain sequence inputs omit unknown glycans, cofactors and membranes; edit model inputs with known chemistry.
Prediction files must be imported and sequence checked before they appear in PyMOL.
PyMOL: run view_results.py from this folder. Each pair is a separate object; enable one at a time.
No assembled coordinate model is fabricated from the separate pairwise structures.
