import logging
from pathlib import Path

import hyperqueue.cluster
from hyperqueue import Job

from ligate.awh.input import AWHInput
from ligate.awh.ligen.common import LigenTaskContext
from ligate.awh.pipeline.check_protein.tasks import hq_submit_check_protein
from ligate.awh.pipeline.ligen import hq_submit_ligen_workflow
from ligate.utils.io import ensure_directory

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(name)s:%(levelname)-4s %(message)s",
        datefmt="%d-%m-%Y %H:%M:%S",
    )

    DATA_DIR = Path("data/awh-2").absolute()
    WORKDIR = Path("workdir").absolute()

    WORKDIR = ensure_directory(WORKDIR, clear=True)

    awh_input = AWHInput(protein_pdb=DATA_DIR / "protein.pdb")

    ligen_container_path = Path("ligen.sif").absolute()
    ligen_workdir = WORKDIR / "ligen"
    ligen_ctx = LigenTaskContext(
        workdir=ligen_workdir, container_path=ligen_container_path
    )

    job = Job(default_workdir=WORKDIR / "hq", default_env=dict(HQ_PYLOG="DEBUG"))
    task = hq_submit_check_protein(awh_input.protein_pdb, WORKDIR, job)

    hq_submit_ligen_workflow(
        ligen_ctx,
        ligen_workdir,
        input_smi=DATA_DIR / "ligands.smi",
        input_mol2=DATA_DIR / "crystal.mol2",
        input_protein=awh_input.protein_pdb,
        job=job,
        deps=[task],
    )

    # Run the workflow
    with hyperqueue.cluster.LocalCluster() as cluster:
        cluster.start_worker()
        client = cluster.client()
        submitted = client.submit(job)
        client.wait_for_jobs([submitted])
