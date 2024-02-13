import json
from dataclasses import dataclass
from pathlib import Path

from hyperqueue import Job
from hyperqueue.ffi.protocol import ResourceRequest
from hyperqueue.task.task import Task

from .common import LigenTaskContext
from .container import ligen_container
from .expansion import SubmittedExpansion


@dataclass
class ScreeningConfig:
    input_mol2: Path
    input_pdb: Path
    ligand_expansion: SubmittedExpansion
    output_path: Path

    input_protein_name: str

    cores: int
    num_parser: int = 20
    num_workers_unfold: int = 20
    num_workers_docknscore: int = 100


@dataclass
class SubmittedScreening:
    config: ScreeningConfig
    task: Task


def screening_task(ctx: LigenTaskContext, config: ScreeningConfig, dep=None):
    with ligen_container(container=ctx.container_path) as ligen:
        input_smi = ligen.map_input(config.ligand_expansion.config.output_smi)
        input_pdb = ligen.map_input(config.input_pdb)
        input_mol2 = ligen.map_input(config.input_mol2)
        output_csv = ligen.map_output(config.output_path)

        description = {
            "name": "vscreen",
            "pipeline": [
                {
                    "kind": "reader_mol2",
                    "name": "reader",
                    "input_filepath": str(input_smi),
                },
                {"kind": "parser_mol2", "number_of_workers": config.num_parser},
                {"kind": "bucketizer_ligand", "name": "bucketizer"},
                {"kind": "unfold", "cpp_workers": config.num_workers_unfold},
                {
                    "kind": "dock_n_score",
                    "wait_setup": "reader",
                    "number_of_restart": "256",
                    "clipping_factor": "256",
                    "scoring_functions": ["d22"],
                    "cpp_workers": config.num_workers_docknscore,
                },
                {
                    "kind": "writer_csv_bucket",
                    "name": "writer",
                    "wait_setup": "reader",
                    "output_filepath": str(output_csv),
                    "print_preamble": "1",
                    "csv_fields": ["SCORE_PROTEIN_NAME", "D22_SCORE"],
                },
                {"kind": "tracker_bucket", "wait_setup": "reader"},
                {"kind": "sink_bucket", "number_of_workers": "1"},
            ],
            "targets": [
                {
                    "name": config.input_protein_name,
                    "configuration": {
                        "input": {"format": "protein", "protein_path": str(input_pdb)},
                        "filtering": {
                            "algorithm": "probe",
                            "path": str(input_mol2),
                            "radius": "8",
                        },
                        "pocket_identification": {"algorithm": "caviar_like"},
                        "anchor_points": {
                            "algorithms": "maximum_points",
                            "separation_radius": "4",
                        },
                    },
                }
            ],
        }

        ligen.run(
            "ligen",
            input=json.dumps(description).encode("utf8"),
        )


def submit_screening(
    ctx: LigenTaskContext, config: ScreeningConfig, job: Job
) -> SubmittedScreening:
    task = job.function(
        screening_task,
        args=(
            ctx,
            config,
        ),
        deps=(config.ligand_expansion.task,),
        name=f"screening-{config.output_path.name}",
        resources=ResourceRequest(cpus=config.cores),
    )
    return SubmittedScreening(config=config, task=task)