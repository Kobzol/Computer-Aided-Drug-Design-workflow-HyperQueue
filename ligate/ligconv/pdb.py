import dataclasses
import os.path
from pathlib import Path
from typing import List

from ..utils.paths import GenericPath, use_dir
from ..wrapper.gmx import GMX


@dataclasses.dataclass
class GromacsTopologyFiles:
    files: List[Path]


def convert_pdb_to_gmx(
    gmx: GMX, pdb_path: GenericPath, output_dir: GenericPath
) -> GromacsTopologyFiles:
    """
    Generates `conf.gro` and topology files from a protein PDB file.
    """
    with use_dir(output_dir):
        gmx.execute(
            [
                "pdb2gmx",
                "-f",
                pdb_path,
                "-renum",
                "-ignh",
                # TODO: generalize
                "-water",
                "tip3p",
                "-ff",
                "amber99sb-ildn",
            ]
        )
        files = [
            "conf.gro",
            "topol.top",
            "topol_Protein.itp",
            "topol_Protein_chain_A.itp",
            "posre_Protein.itp",
            "posre_Protein_chain_A.itp",
        ]
        files = [Path(f).resolve() for f in files]
        for file in files:
            assert os.path.exists(file)
        return GromacsTopologyFiles(files=files)
