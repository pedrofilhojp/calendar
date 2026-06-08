import json
from contextlib import contextmanager

import pika

from .config import settings


QUEUE_NAME = "appointment_notifications"


def _parameters() -> pika.URLParameters:
    params = pika.URLParameters(settings.rabbitmq_url)
    params.heartbeat = 30
    params.blocked_connection_timeout = 30
    return params


@contextmanager
def rabbitmq_channel():
    connection = pika.BlockingConnection(_parameters())
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    try:
        yield channel
    finally:
        connection.close()


def publish_appointment(payload: dict) -> None:
    with rabbitmq_channel() as channel:
        channel.basic_publish(
            exchange="",
            routing_key=QUEUE_NAME,
            body=json.dumps(payload, default=str).encode("utf-8"),
            properties=pika.BasicProperties(
                delivery_mode=pika.DeliveryMode.Persistent,
                content_type="application/json",
            ),
        )


def check_rabbitmq() -> bool:
    with rabbitmq_channel():
        return True
