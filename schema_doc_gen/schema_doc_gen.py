"""Generate schema documentation."""

from __future__ import annotations

import argparse
import json
import pkgutil
import sys
from contextlib import contextmanager
from pathlib import Path
from shutil import rmtree
from textwrap import indent
from typing import TYPE_CHECKING

import jsonschema_markdown
from schema import Schema

from . import __version__

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

INDEX_MD = """\
{filename}
{underline}

This page documents the available schemas.

.. toctree::
   :maxdepth: 1
   :caption: Schemas:

{schemas}

"""
SCHEMAS = {}
get_schema = SCHEMAS.get


def get_arg_parser() -> argparse.ArgumentParser:
    """Get parser for CLI.

    Returns
    -------
    argparse.ArgumentParser
        Arg parser.
    """
    parser = argparse.ArgumentParser(
        description="Convert a schema to a markdown document.",
    )

    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s v{__version__}",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print while generating schemas",
    )
    parser.add_argument(
        "-F",
        "--force",
        action="store_true",
        help="Force removal of output directory (if not CWD). (default: %(default)s)",
    )

    parser.add_argument(
        "-L",
        "--location",
        help="Resolvable path to dictionary containing Schema key-value pairs.",
        required=True,
    )
    parser.add_argument(
        "-P",
        "--path",
        help="Temporary addition to system path for finding relative location",
        type=Path,
        default=Path.cwd(),
    )

    parser.add_argument(
        "schemas",
        nargs="*",
        help=(
            "Schemas to convert or 'all' if all are to be done. "
            "If given as a colon-separated list, "
            "the first key is the name and the following are the "
            "components to be written consecutively to the same file. "
            "(default: %(default)r)"
        ),
        default=["all"],
    )

    parser.add_argument(
        "--clear",
        action=argparse.BooleanOptionalAction,
        help="Clear folder before writing. (default: %(default)s)",
        default=True,
    )
    parser.add_argument(
        "--index",
        action=argparse.BooleanOptionalAction,
        help="Write index file with toctree to folder. (default: %(default)s)",
        default=True,
    )

    parser.add_argument(
        "--header",
        help="Title of index file. (default: %(default)r)",
        default="Schemas",
    )

    parser.add_argument(
        "-O",
        "--out-name",
        help=(
            "Format to use for naming output, "
            "substituting '%%s' for schema key. (default: %(default)r)"
        ),
        default="%s.md",
    )
    parser.add_argument(
        "-o",
        "--out-folder",
        help="Folder to write formatted docs in. (default: %(default)r)",
        default="schemas",
        type=Path,
    )

    return parser


def process_schema(
    schema_key: Schema | str,
    *,
    name: str | None = None,
) -> str:
    """Process a schema into markdown.

    Parameters
    ----------
    schema_key : Schema or str
        Key for schemas.
    name : str, optional
        Override for name (mandatory if passing :class:`schema` directly).

    Returns
    -------
    str
        Markdown rendered documentation.

    Raises
    ------
    ValueError
        Name not passed with Schema.
    """
    match (schema_key, name):
        case (_, str() as inp):
            name = inp
        case (str() as inp, _):
            name = inp
        case _:
            raise ValueError(
                f"Cannot reliably determine name from {type(schema_key).__name__}",
            )

    schema = get_schema(schema_key)

    match schema:
        case Schema():
            json_schema = schema.json_schema(name)
        case dict():
            json_schema = schema
        case str():
            json_schema = json.loads(schema)

    return jsonschema_markdown.generate(
        json_schema,
        title=name,
        footer=False,
        hide_empty_columns=True,
    )


def get_filename(fmt: str, key: str) -> str:
    """Format filename from CLI.

    Parameters
    ----------
    fmt : str
        CLI format.
    key : str
        Schema key.

    Returns
    -------
    str
        Formatted filename.

    Examples
    --------
    >>> get_filename("%s.md", "base")
    'base.md'
    """
    return fmt % key


def clear_folder(folder: Path, *, force: bool = False, verbose: bool = False) -> None:
    """Delete folder and create new (empty) one.

    Parameters
    ----------
    folder : Path
        Folder to clear.
    force : bool
        Do not ask whether to remove folder.
    verbose : bool
        Print status.
    """
    if not folder.exists():
        folder.mkdir()
        return

    if folder.samefile(Path.cwd()):
        print("Cannot clear folder as this is current working directory.")
        return

    if (
        not force
        and input(
            f"Running this will clear {folder}, are you sure you want to continue? [y/N] ",
        )
        .strip()
        .lower()
        != "y"
    ):
        print("Cancelling.")
        sys.exit()

    if verbose:
        print(f"Deleting {folder}...")

    rmtree(folder, ignore_errors=True)
    folder.mkdir()


def build_schema_set(schema_in: Sequence[str]) -> dict[str, Sequence[str]]:
    """Build the full schema set.

    Parameters
    ----------
    schema_in : Sequence[str]
        List of schema to include.

    Returns
    -------
    schema_set : dict[str, Sequence[str]]
        Dict mapping output name to set of schema to include in that file.
    """
    schema_set = {
        name: schemas if schemas != ["all"] else list(SCHEMAS.keys())
        for block in schema_in
        if ":" in block
        for name, *schemas in block.split(":")
    }
    schema_set.update(
        {schema: [schema] for schema in schema_in if ":" not in schema and schema != "all"},
    )

    if "all" in schema_in:
        schema_set.update({schema: [schema] for schema in SCHEMAS})

    return schema_set


@contextmanager
def temp_syspath(path: Path | str) -> Iterator[None]:
    """Set temporary system path.

    Parameters
    ----------
    path : Path
        Path to prepend.

    Raises
    ------
    ValueError
        Unable to prepend path.
    """
    try:
        sys.path.insert(0, str(path))
        yield None
    except Exception as err:
        raise ValueError(f"Couldn't insert {path} into system.") from err
    else:
        sys.path.pop(0)


def main(args_in: Sequence[str] | None = None, /) -> None:
    """Parse schemas and dump to file.

    Parameters
    ----------
    args_in : Sequence[str], optional
        Pass CLI params directly.
    """
    global SCHEMAS

    parser = get_arg_parser()
    args = parser.parse_args(args_in)

    with temp_syspath(args.path):
        SCHEMAS |= pkgutil.resolve_name(args.location)
    schema_set = build_schema_set(args.schemas)

    indiv_schemas = {schema for schemas in schema_set.values() for schema in schemas}

    # Get unique (by schema), but ordered keys matching reqs
    schemas = {
        schema: key
        for key, schema in reversed(SCHEMAS.items())
        if "all" in args.schemas or key in indiv_schemas
    }
    out_names = [get_filename(args.out_name, name) for name in schema_set]

    if args.verbose:
        print(f"Generating schemas for keys {', '.join(map(repr, schemas.values()))}...")

    if args.clear:
        clear_folder(args.out_folder, force=args.force, verbose=args.verbose)

    for (name, block), out_name in zip(schema_set.items(), out_names, strict=True):
        out_path = args.out_folder / out_name

        if args.verbose:
            print(f"Generating schema for {name!r} to {out_path}...")

        markdown = "\n\n".join(map(process_schema, block))

        with out_path.open("w", encoding="utf-8") as out:
            out.write(markdown)

    if args.index:
        if args.verbose:
            print(f"Writing index to {args.out_folder / 'index.rst'}...")

        with (args.out_folder / "index.rst").open("w", encoding="utf-8") as out:
            out.write(
                INDEX_MD.format(
                    filename=args.header,
                    underline="=" * len(args.header),
                    schemas=indent("\n".join(Path(key).stem for key in out_names), " " * 3),
                ),
            )

    if args.verbose:
        print("Done with schemas")


if __name__ == "__main__":
    main()
