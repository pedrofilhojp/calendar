import json
import logging
import os
import smtplib
import threading
import time
from dataclasses import dataclass
from email.message import EmailMessage
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer

import pika


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
LOGGER = logging.getLogger("agenda.worker")

QUEUE_NAME = "appointment_notifications"
REQUIRED_ENV = (
    "RABBITMQ_HOST",
    "RABBITMQ_USER",
    "RABBITMQ_PASSWORD",
    "SMTP_HOST",
    "SMTP_PORT",
)


@dataclass(frozen=True)
class Settings:
    rabbitmq_host: str
    rabbitmq_user: str
    rabbitmq_password: str
    smtp_host: str
    smtp_port: int
    health_port: int = 8080

    @property
    def rabbitmq_url(self) -> str:
        return (
            f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}"
            f"@{self.rabbitmq_host}:5672/%2F"
        )


class HealthState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.consumer_running = False
        self.last_message_at = 0.0
        self.last_loop_at = time.time()
        self.last_error = ""

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "consumer_running": self.consumer_running,
                "last_message_at": self.last_message_at,
                "last_loop_at": self.last_loop_at,
                "last_error": self.last_error,
            }

    def mark_loop(self) -> None:
        with self.lock:
            self.consumer_running = True
            self.last_loop_at = time.time()
            self.last_error = ""

    def mark_message(self) -> None:
        with self.lock:
            self.last_message_at = time.time()

    def mark_error(self, error: Exception) -> None:
        with self.lock:
            self.consumer_running = False
            self.last_error = str(error)


def load_settings() -> Settings:
    missing = [name for name in REQUIRED_ENV if not os.getenv(name)]
    if missing:
        LOGGER.error("Missing required environment variables: %s", ", ".join(missing))
        raise RuntimeError(
            "Worker startup failed. Missing required environment variables: " + ", ".join(missing)
        )
    return Settings(
        rabbitmq_host=os.environ["RABBITMQ_HOST"],
        rabbitmq_user=os.environ["RABBITMQ_USER"],
        rabbitmq_password=os.environ["RABBITMQ_PASSWORD"],
        smtp_host=os.environ["SMTP_HOST"],
        smtp_port=int(os.environ["SMTP_PORT"]),
        health_port=int(os.getenv("HEALTH_PORT", "8080")),
    )


SETTINGS = load_settings()
STATE = HealthState()


def html_body(event: dict) -> str:
    priority = int(event.get("priority", 1))
    colors = {1: "#34d399", 2: "#a3e635", 3: "#facc15", 4: "#fb923c", 5: "#ef4444"}
    color = colors.get(priority, "#94a3b8")
    return f"""
    <html>
      <body style="font-family: Arial, sans-serif; background: #0f172a; color: #e2e8f0; padding: 24px;">
        <div style="max-width: 640px; margin: auto; background: #111827; border: 1px solid #334155; border-radius: 12px; padding: 24px;">
          <p style="margin: 0 0 12px;">Você foi convidado para um compromisso:</p>
          <h1 style="margin: 0 0 16px; color: #ffffff;">{escape(event.get("title", "Compromisso"))}</h1>
          <p><strong>Data e hora:</strong> {escape(event.get("event_time", ""))}</p>
          <p><strong>Prioridade:</strong> <span style="color: {color}; font-weight: 700;">Nível {priority}</span></p>
          <p><strong>Organizador:</strong> {escape(event.get("owner_email", ""))}</p>
          <p style="line-height: 1.5;">{escape(event.get("description", ""))}</p>
        </div>
      </body>
    </html>
    """


def send_email(recipient: str, event: dict) -> None:
    message = EmailMessage()
    message["Subject"] = f"Novo compromisso: {event.get('title', 'Agenda')}"
    message["From"] = "agenda@k8s.local"
    message["To"] = recipient
    message.set_content(
        f"Você foi convidado para: {event.get('title')} em {event.get('event_time')}"
    )
    message.add_alternative(html_body(event), subtype="html")

    with smtplib.SMTP(SETTINGS.smtp_host, SETTINGS.smtp_port, timeout=15) as smtp:
        smtp.send_message(message)


def handle_message(channel, method, properties, body: bytes) -> None:
    try:
        event = json.loads(body.decode("utf-8"))
        recipients = event.get("guest_emails", [])
        LOGGER.info("Processing appointment %s for %s recipients", event.get("id"), len(recipients))
        for recipient in recipients:
            send_email(recipient, event)
        STATE.mark_message()
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception:
        LOGGER.exception("Failed to process notification. Message will be requeued.")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def consume_forever() -> None:
    while True:
        try:
            params = pika.URLParameters(SETTINGS.rabbitmq_url)
            params.heartbeat = 30
            params.blocked_connection_timeout = 30
            connection = pika.BlockingConnection(params)
            channel = connection.channel()
            channel.queue_declare(queue=QUEUE_NAME, durable=True)
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=QUEUE_NAME, on_message_callback=handle_message)
            LOGGER.info("Worker consuming queue %s", QUEUE_NAME)
            while channel.is_open:
                STATE.mark_loop()
                connection.process_data_events(time_limit=1)
        except Exception as exc:
            STATE.mark_error(exc)
            LOGGER.exception("Consumer loop failed. Retrying in 5 seconds.")
            time.sleep(5)


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        snapshot = STATE.snapshot()
        loop_recent = time.time() - snapshot["last_loop_at"] < 45
        healthy = snapshot["consumer_running"] and loop_recent
        if self.path == "/healthz/live":
            self.respond(200, {"status": "alive"})
        elif self.path == "/healthz/ready":
            status = 200 if healthy else 503
            self.respond(status, {"status": "ready" if healthy else "not-ready", **snapshot})
        else:
            self.respond(404, {"detail": "not found"})

    def log_message(self, format: str, *args) -> None:
        return

    def respond(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def serve_health() -> None:
    server = HTTPServer(("0.0.0.0", SETTINGS.health_port), HealthHandler)
    LOGGER.info("Worker health server listening on %s", SETTINGS.health_port)
    server.serve_forever()


if __name__ == "__main__":
    threading.Thread(target=serve_health, daemon=True).start()
    consume_forever()
