from server.scenes.output import parse_scene
from server.workflow.runner import ReviewRunner


class SceneRunner(ReviewRunner):
    prefix = "scene"
    label = "scene stage"

    def parse_result(self, output, snapshot):
        return parse_scene(output, snapshot)
