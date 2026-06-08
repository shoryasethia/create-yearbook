import logging


class HealthCheckFilter(logging.Filter):
    def filter(self, record):
        return "/health" not in record.getMessage()


def on_starting(server):
    logging.getLogger("gunicorn.access").addFilter(HealthCheckFilter())
