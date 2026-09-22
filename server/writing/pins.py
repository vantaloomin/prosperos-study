from server.database import now, one
from server.errors import require
from server.operations import previous, remember
from server.stories import check_revision
from server.writing.resources import version


def read_pins(connection, story_id):
    story = one(connection, 'SELECT revision FROM stories WHERE id=?', (story_id,))
    row = connection.execute('SELECT * FROM writing_pins WHERE story_id=?', (story_id,)).fetchone()
    return {'story_revision': story['revision'],
            'style': (row['style_version_id'] if row else None) or 'none',
            'recipe': (row['recipe_version_id'] if row else None) or 'none'}


def save_pins(database, story_id, body):
    payload = {'story_id': story_id, **body.model_dump()}
    with database.connect(write=True) as connection:
        saved = previous(connection, body.operation_id, 'writing-pins', payload)
        if saved is not None:
            return saved
        current = read_pins(connection, story_id)
        check_revision({'revision': current['story_revision']}, body.expected_revision)
        for kind in ('style', 'recipe'):
            selected = getattr(body, kind)
            require(selected != 'inherit', 'A Story default must choose a version or none.')
            if selected != 'none':
                target = version(connection, selected, kind)
                require(not target['archived'] or selected == current[kind],
                        'Unarchive this resource before selecting it for another Story.')
        connection.execute('INSERT INTO writing_pins VALUES (?,?,?,?) ON CONFLICT(story_id) '
                           'DO UPDATE SET style_version_id=excluded.style_version_id,'
                           'recipe_version_id=excluded.recipe_version_id,updated_at=excluded.updated_at',
                           (story_id, None if body.style == 'none' else body.style,
                            None if body.recipe == 'none' else body.recipe, now()))
        connection.execute('UPDATE stories SET revision=revision+1,updated_at=? WHERE id=?', (now(), story_id))
        connection.execute('UPDATE branches SET revision=revision+1 WHERE story_id=?', (story_id,))
        return remember(connection, body.operation_id, 'writing-pins', payload, read_pins(connection, story_id))
