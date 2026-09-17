"""Create a labeled long-history fixture only in the isolated browser-review database."""
from pathlib import Path

from server.branches import insert_node, touch_branch
from server.database import Database, one
from server.models import StoryCreate
from server.stories import Stories, create_branch

PARAGRAPH = """Rain gathers along the station windows, turning the far platform into a study of silver lines.
Mara sets a notebook between the two cups and waits for the room to settle. There is no hurry in her
gesture, only a careful invitation to look again at what they already know. The timetable still shows
the same departure. Beyond the glass, a porter moves a trolley beneath the shelter and pauses to fold
an abandoned newspaper. Its pages lift in the draft before he weighs them down with a gloved hand.
The clock sounds once. Mara follows the sound with her eyes, then returns to the page. A small mark
beside the destination has caught her attention: a circle drawn twice, the second line slightly darker.
She turns the notebook so the mark can be seen clearly. 'I remember this part differently,' she says.
Nothing has yet been decided. The letter remains sealed, the cups are warm, and the other platform
is still close enough to reach without running. A conversation at the next table falls into a gentle
pause as someone searches for a familiar name. Mara leaves the question open, giving the moment room
to become whatever the person across from her chooses next.""".replace("\n", " ")


def add_pairs(connection, branch, start, end, variation):
    for index in range(start, end):
        user = f"Fixture exchange {index + 1}. I examine the note and ask what the mark means. {variation}"
        branch["head_id"] = insert_node(connection, branch, user, "user", {"source": "performance_fixture"})
        branch["head_id"] = insert_node(connection, branch, f"Response {index + 1} · {variation}\n\n{PARAGRAPH}",
                                        "assistant", {"source": "performance_fixture"})
    touch_branch(connection, branch["id"], branch["head_id"])


def seed():
    database = Database(Path(__file__).resolve().parents[1] / "data" / "browser-review.sqlite3")
    result = Stories(database).create(StoryCreate(title="Performance fixture · 120 responses",
             premise="UI benchmark only. Each path contains 120 assistant responses and 120 user messages. No model calls."))
    with database.connect(write=True) as connection:
        main = one(connection, "SELECT * FROM branches WHERE id=?", (result["branch_id"],))
        add_pairs(connection, main, 0, 80, "Shared beginning")
        fork_head = main["head_id"]
        alternate_id = create_branch(connection, result["story_id"], main["manifest_id"], "The other platform")
        connection.execute("UPDATE branches SET head_id=?,forked_from=?,fork_node_id=? WHERE id=?",
                           (fork_head, main["id"], fork_head, alternate_id))
        alternate = one(connection, "SELECT * FROM branches WHERE id=?", (alternate_id,))
        add_pairs(connection, main, 80, 120, "Main path")
        add_pairs(connection, alternate, 80, 120, "The other platform")
    print(f"Created performance fixture story {result['story_id']} with two 240-message paths.")


if __name__ == "__main__":
    seed()
