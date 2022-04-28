from pathlib import Path
from .utils.io import GenericPath
from jinja2 import Template


def load_template(path: Path) -> Template:
    with open(path) as f:
        return Template(f.read())


def render_mdp(input: Path, output: GenericPath, **parameters):
    template = load_template(input)

    with open(output, "w") as f:
        f.write(template.render(**parameters))
