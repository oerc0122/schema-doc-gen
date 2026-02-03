# schema-doc-gen
Generate docs from a python Schema through a simplified interface.

## General usage

By default generates a folder containing documentation in markdown format for all of the Schemas listed in a dictionary of schemas.

In order to run, use:

```shell
$ schema_doc_gen -L <resolution.to.schema:dict>
```

If the schema dict is not on the system path (i.e. installed or in cwd) it is possible to pass a path to the base of the library from which the dict can be imported.

```shell
$ schema_doc_gen -L <module.specs:schemadict> -P /path/to/import/module
```

**Note**: it is possible to add multiple paths/locations by adding multiple `-L` or `-P`s. For multiple dictionaries which will be combined in the order they are specified.

## Generating subsets of docs

It is possible to select which keys from the dict you will add to which files. By default, all keys will be used. This is equivalent to

```shell
$ schema_doc_gen ... all
```

Each key will create a separate file. To select a subset of keys to use simply enter those keys:

```shell
$ schema_doc_gen ... keya keyb
```

By default, files will be generated using the key as the name of the file. To override this behaviour give a key a file name using a colon.

```shell
$ schema_doc_gen ... out:keya out2:keyb
```

If you want more than one schema to be in the same file, simply add more colon separated values. The head will be the pseudo-key and the schemas will all be dumped to the same file.

```shell
$ schema_doc_gen ... out:keya:keyb
```
