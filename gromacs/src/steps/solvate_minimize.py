import dataclasses
import enum
import logging
from pathlib import Path
from typing import List

from hyperqueue.job import Job
from hyperqueue.output import default_stdout
from hyperqueue.task.task import Task

from ..ctx import Context
from ..input import ComputationTriple
from ..input.properties import get_cl, get_na, protein_ff
from ..mdp import render_mdp
from ..utils.io import GenericPath, delete_file, replace_in_place


@dataclasses.dataclass
class MinimizationParams:
    steps: int = 100


class LigandOrProtein(enum.Enum):
    Ligand = enum.auto()
    Protein = enum.auto()

    def __repr__(self) -> str:
        return self.name


@dataclasses.dataclass
class MinimizationWorkload:
    lop: LigandOrProtein
    directory: Path

    def __repr__(self) -> str:
        return f"{self.lop} at `{str(self.directory)}`"


@dataclasses.dataclass
class MinimizationPreparedData:
    mdp: Path


def modify_grofile_inplace(path: GenericPath):
    replace_in_place(path, [
        ("1HD1", "HD11"),
        ("2HD1", "HD12"),
        ("3HD1", "HD13"),
        ("1HD2", "HD21"),
        ("2HD2", "HD22"),
        ("3HD2", "HD23"),
        ("1HE2", "HE21"),
        ("2HE2", "HE22"),
        ("1HG1", "HG11"),
        ("2HG1", "HG12"),
        ("3HG1", "HG13"),
        ("1HG2", "HG21"),
        ("2HG2", "HG22"),
        ("3HG2", "HG23"),
        ("1HH1", "HH11"),
        ("2HH1", "HH12"),
        ("1HH2", "HH21"),
        ("2HH2", "HH22"),
        ("1HH3", "HH31"),
        ("2HH3", "HH32"),
        ("3HH3", "HH33"),
        ("HOH      O", "HOH     OW"),
        ("HOH     H1", "HOH    HW1"),
        ("HOH     H2", "HOH    HW2")
    ])


def solvated_path(input: MinimizationWorkload) -> Path:
    return input.directory / "solvated.gro"


def corrected_box_path(input: MinimizationWorkload) -> Path:
    return input.directory / "correctBox.gro"


TopName = str


def topology_path(topname: TopName) -> str:
    return f"topology/topol_{topname}.top"


def get_topname(input: MinimizationWorkload, triple: ComputationTriple) -> TopName:
    return {
        LigandOrProtein.Ligand: "ligandInWater",
        LigandOrProtein.Protein: protein_ff(triple)
    }[input.lop]


def solvate(ctx: Context, input: MinimizationWorkload, triple: ComputationTriple):
    logging.info(f"Running solvate step on {input}, {triple}")

    solvated = solvated_path(input)
    topname = get_topname(input, triple)

    ctx.gmx.execute([
        "solvate",
        "-cp", corrected_box_path(input),
        "-cs", "spc216.gro",
        "-p", ctx.workdir / topology_path(topname),
        "-o", solvated,
    ])
    delete_file(ctx.workdir / f"topology/#topol_{topname}.top.1#")
    replace_in_place(solvated, [("HOH", "SOL")])


def add_ions(ctx: Context, input: MinimizationWorkload, triple: ComputationTriple,
             params: MinimizationParams) -> MinimizationPreparedData:
    logging.info(f"Running add_ions step on {input}, {triple}")

    topname = get_topname(input, triple)
    topology = ctx.workdir / topology_path(topname)
    add_ions = input.directory / "addIons.tpr"

    generated_mdp = "generated_em_l0.mdp"
    render_mdp(ctx.mdpdir / "em_l0.mdp", generated_mdp, nsteps=params.steps)

    ctx.gmx.execute([
        "grompp",
        "-f", generated_mdp,
        "-c", solvated_path(input),
        "-p", topology,
        "-o", add_ions,
        "-maxwarn", "2"
    ])
    delete_file("mdout.mdp")
    ctx.gmx.execute([
        "genion",
        "-s", add_ions,
        "-o", input.directory / "ions.gro",
        "-p", topology,
        "-pname", get_na(triple),
        "-nname", get_cl(triple),
        "-conc", "0.15",
        "-neutral"
    ], input=b"SOL\n")
    delete_file(ctx.workdir / f"topology/#topol_{topname}.top.1#")
    delete_file(add_ions)

    return MinimizationPreparedData(mdp=Path(generated_mdp))


def energy_minimize(ctx: Context, input: MinimizationWorkload, triple: ComputationTriple,
                    prepared: MinimizationPreparedData):
    logging.info(f"Running energy_minimize step on {input}, {triple}")

    topname = get_topname(input, triple)
    ctx.gmx.execute([
        "grompp",
        "-f", prepared.mdp,
        "-c", input.directory / "ions.gro",
        "-p", ctx.workdir / topology_path(topname),
        "-o", input.directory / "EM.tpr",
        "-po", input.directory / "EMout.mdp",
        "-maxwarn", "2"
    ])
    ctx.gmx.execute(["mdrun", "-v", "-deffnm", "EM"], workdir=input.directory)


def editconf_task(ctx: Context, input_ligand: MinimizationWorkload,
                  input_protein: MinimizationWorkload):
    # Place the molecule of interest in a rhombic dodecahedron of the desired size (1.5 nm
    # distance to the edges)
    logging.info(f"Running editconf step on {input_ligand} and {input_protein}")
    ctx.gmx.editconf(ctx.workdir / "structure/mergedA.pdb", corrected_box_path(input_ligand))
    ctx.gmx.editconf(ctx.workdir / "structure/full.pdb", corrected_box_path(input_protein))
    modify_grofile_inplace(corrected_box_path(input_protein))


def energy_minimization_task(ctx: Context, input: MinimizationWorkload, triple: ComputationTriple,
                             params: MinimizationParams):
    solvate(ctx, input, triple)
    prepared = add_ions(ctx, input, triple, params)
    energy_minimize(ctx, input, triple, prepared)


def solvate_prepare(ctx: Context, triple: ComputationTriple, params: MinimizationParams,
                    job: Job) -> List[Task]:
    ligand_dir = ctx.workdir / "ligand"
    ligand_dir.mkdir(exist_ok=True)

    protein_dir = ctx.workdir / "protein"
    protein_dir.mkdir(exist_ok=True)

    inputs = [
        MinimizationWorkload(lop=LigandOrProtein.Ligand, directory=ligand_dir),
        MinimizationWorkload(lop=LigandOrProtein.Protein, directory=protein_dir)
    ]
    task = job.function(editconf_task, args=(ctx, inputs[0], inputs[1]))
    return [job.function(energy_minimization_task, args=(ctx, input, triple, params), deps=[task],
                         stdout=default_stdout())
            for input in inputs]
