from server.background.interpretation_context import parse_interpretation
from server.workflow.runner import ReviewRunner


class BackgroundRunner(ReviewRunner):
    prefix = 'background'
    label = 'private interpretation'

    def parse_result(self, output, snapshot):
        return parse_interpretation(output, snapshot)
