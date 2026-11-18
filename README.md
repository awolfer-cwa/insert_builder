# production-insertbuilder

Python port of the `insert_builder` Ruby gem — builds CARMA journal/handbook
inserts in InDesign and files the output. Orchestrated by `carma_controller`
on a 30-minute cycle (or manual trigger), the same way `production-templatebuilder`
and `production-adfiler` are.

InDesign is driven via `carma_controller`'s script bridge (job-queue + ExtendScript),
not COM — see `insert_builder/indesign/bridge.py` and `insert_builder/scripts/`.
