# Source provenance

This repository contains no bundled datasets or domain-specific source catalogue.
Supply your own local inputs through a reviewed job configuration. Built-in CSV
and SQLite demonstrations generate small neutral synthetic fixtures only when
explicitly run; those fixtures and their checkpoints remain ignored local files.

For each real source used outside this repository, record the provider, access
terms and license, retrieval date, local path, file hash, schema/version, and
permitted use. Keep that source manifest beside your local job configuration or
inside the consuming project. Never place private inputs, credentials or
generated run evidence in this public framework repository.

The framework records run evidence and source/configuration identity in its
local audit stores. Source provenance still belongs to the caller: a successful
pipeline run does not establish source ownership, accuracy or permission to
redistribute the input.
