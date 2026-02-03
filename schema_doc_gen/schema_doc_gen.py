"""Generate schema documentation."""

from __future__ import annotations

import argparse
import json
import pkgutil
import sys
from collections import defaultdict
from contextlib import contextmanager
from functools import partial
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


@contextmanager
def temp_syspath(path: Sequence[Path | str]) -> Iterator[None]:
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
    pth = sys.path.copy()
    try:
        sys.path = list(map(str, path)) + sys.path
        yield None
    except Exception as err:
        raise ValueError(f"Couldn't insert {path} into system.") from err
    finally:
        sys.path = pth


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
        action="append",
        help="Resolvable path to dictionary containing Schema key-value pairs.",
        required=True,
    )
    parser.add_argument(
        "-P",
        "--path",
        action="append",
        help="Temporary additions to system path for finding relative location",
        type=Path,
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
    schemas: dict[str, Schema],
    schema_key: str,
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
    KeyError
        Schema not in dict or invalid type.
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

    schema = schemas.get(schema_key)

    match schema:
        case Schema():
            json_schema = schema.json_schema(name)
        case dict():
            json_schema = schema
        case str():
            json_schema = json.loads(schema)
        case _:
            raise KeyError(f"Schema ({schema_key}) not found or invalid type ({schema!r})")

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


def build_schema_set(
    schema_dict: dict[str, Schema],
    schema_keys: Sequence[str],
) -> tuple[dict[str, Sequence[str]], set[str]]:
    """Build the full schema set.

    Parameters
    ----------
    schema_dict : dict[str, Schema]
        Dictionary of schemas.
    schema_keys : Sequence[str]
        Keys to process.

    Returns
    -------
    schema_set : dict[str, Sequence[str]]
        Dict mapping output name to set of schema to include in that file.
    """
    # Get all schemas as groups
    schema_set = {}
    for key in schema_keys:
        match key.split(":"):
            case ["all"]:
                for schema in schema_dict:
                    schema_set[schema] = [schema]
            case [name]:
                schema_set[name] = [name]
            case [name, *_] if ":all" in key:
                schema_set[name] = list(schema_dict)
            case [name, *schemas]:
                schema_set[name] = schemas

    # Dedup schema_set
    # Get unique (by schema), but ordered keys matching reqs
    indiv_schemas = {schema for schemas in schema_set.values() for schema in schemas}
    schemas_rev = defaultdict(list)
    for key, schema in reversed(schema_dict.items()):
        if key in indiv_schemas:
            schemas_rev[schema].append(key)

    def get_main_key(key: str) -> str:
        """Find main key excluding aliases.

        Parameters
        ----------
        key : str
            Key to find.

        Returns
        -------
        str
            Main unaliased key to grab.

        Raises
        ------
        KeyError
            Key unavailable.
        """
        for avail in schemas_rev.values():
            if key in avail:
                return avail[0]

        raise KeyError(f"{key} not found in schemas")

    return {
        name: list(dict.fromkeys(map(get_main_key, keys))) for name, keys in schema_set.items()
    }, indiv_schemas


def main(
    *,
    schemas: dict[str, Schema],
    schema_keys: Sequence[str] = ("all",),
    out_name_fmt: str = "%s.md",
    out_folder: Path | str = "schemas",
    verbose: bool = False,
    clean: bool = True,
    force_clear: bool = False,
    write_index: bool = True,
    title: str = "",
) -> None:
    """Parse schemas and dump to file.

    FIXME: Long description.

    Parameters
    ----------
    schemas : dict[str, Schema]
        Schemas to process.
    schema_keys : Sequence[str]
        Keys to use.
    out_name_fmt : str
        Format to use for output names.
    out_folder : Path or str
        Folder to dump markdown to.
    verbose : bool
        Whether to print during processing.
    clean : bool
        Whether to clean folder before writing.
    force_clear : bool
        Whether to force clearing without asking.
    write_index : bool
        Whether to dump an .rst toctree into folder.
    title : str
        Title of rst page.
    """
    schema_set, requested_schema = build_schema_set(schemas, schema_keys)

    out_names = [get_filename(out_name_fmt, name) for name in schema_set]
    out_folder = Path(out_folder)

    if verbose:
        print(f"Generating schemas for keys {', '.join(map(repr, requested_schema))}...")

    if clean:
        clear_folder(out_folder, force=force_clear, verbose=verbose)

    process = partial(process_schema, schemas)

    for (name, block), out_name in zip(schema_set.items(), out_names, strict=True):
        out_path = out_folder / out_name

        if verbose:
            print(f"Generating schema for {name!r} to {out_path}...")

        markdown = "\n\n".join(map(process, block))

        with out_path.open("w", encoding="utf-8") as out:
            out.write(markdown)

    if write_index:
        if verbose:
            print(f"Writing index to {out_folder / 'index.rst'}...")

        with (out_folder / "index.rst").open("w", encoding="utf-8") as out:
            out.write(
                INDEX_MD.format(
                    filename=title,
                    underline="=" * len(title),
                    schemas=indent("\n".join(Path(key).stem for key in out_names), " " * 3),
                ),
            )

    if verbose:
        print("Done with schemas")


def cli(args_in: Sequence[str] | None = None, /) -> None:
    """Run through CLI.

    Parameters
    ----------
    args_in : Sequence[str], optional
        Argument overrides.
    """
    parser = get_arg_parser()
    args = parser.parse_args(args_in)

    schemas: dict[str, Schema] = {}
    with temp_syspath(args.path):
        for location in args.location:
            schemas |= pkgutil.resolve_name(location)

    main(
        schemas=schemas,
        schema_keys=args.schemas or ("all",),
        out_name_fmt=args.out_name,
        out_folder=args.out_folder,
        verbose=args.verbose,
        clean=args.clear,
        force_clear=args.force,
        write_index=args.index,
        title=args.header,
    )


if __name__ == "__main__":
    cli()
