"""Compatibility schema for collaboration records from older workspaces.

The public core does not expose collaboration delivery tools. Keeping the table
migration lets an existing schema-8 database open without discarding history.
"""


def schema(db):
    db.execute(
        'CREATE TABLE handoff_versions(project TEXT NOT NULL, id TEXT NOT NULL, '
        'revision INTEGER NOT NULL, kind TEXT NOT NULL, body TEXT NOT NULL, '
        'created TEXT NOT NULL, PRIMARY KEY(project,id,revision))'
    )


class Handoffs:
    def __init__(self, workbench):
        self.workbench = workbench

    @staticmethod
    def _unavailable(*_args, **_kwargs):
        raise ValueError('Collaboration delivery tools are not included in the public core')

    preview = _unavailable
    save = _unavailable
