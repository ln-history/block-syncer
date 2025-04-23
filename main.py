import os
import time
import json
import signal
import logging
import argparse
import sqlite3
import requests
import hashlib
from datetime import datetime, timezone
from kafka import KafkaProducer
from dotenv import load_dotenv

load_dotenv(".env")

from logging.handlers import RotatingFileHandler

# Set up log directory and file
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_path = os.path.join(log_dir, "block_syncer.log")

# Create rotating file handler
file_handler = RotatingFileHandler(log_path, maxBytes=5_000_000, backupCount=5)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

# Create stream handler for stdout
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)
stream_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

# Apply handlers to root logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.handlers = [file_handler, stream_handler]

RUNNING = True
RPC_URL = os.getenv("EXPLORER_RPC_URL", "").rstrip("/")

def signal_handler(sig, frame):
    global RUNNING
    logger.info("Shutdown signal received. Stopping gracefully...")
    RUNNING = False


def init_db(db_path="data/seen_blocks.db"):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS seen_blocks (height INTEGER PRIMARY KEY)"
    )
    conn.commit()
    return conn


def has_seen_block(conn, height):
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM seen_blocks WHERE height = ?", (height,))
    return cursor.fetchone() is not None


def mark_block_as_seen(conn, height):
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO seen_blocks (height) VALUES (?)", (height,))
    conn.commit()


def create_kafka_producer() -> KafkaProducer:
    bootstrap_servers = f"{os.getenv('SERVER_IP_ADDRESS')}:{os.getenv('SERVER_PORT')}"
    return KafkaProducer(
        bootstrap_servers=[bootstrap_servers],
        client_id="block-producer",
        security_protocol="SASL_SSL",
        ssl_cafile="./certs/kafka.truststore.pem",
        ssl_certfile="./certs/kafka.keystore.pem",
        ssl_keyfile="./certs/kafka.keystore.pem",
        ssl_password=os.getenv("SSL_PASSWORD"),
        sasl_mechanism="SCRAM-SHA-512",
        sasl_plain_username=os.getenv("SASL_PLAIN_USERNAME"),
        sasl_plain_password=os.getenv("SASL_PLAIN_PASSWORD"),
        ssl_check_hostname=False,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )

def get_tip_height() -> int:
    url = f"{RPC_URL}/blocks/tip"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()["height"]
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error while fetching tip height: {http_err}")
    except Exception as err:
        logger.error(f"Error fetching tip height: {err}")
    return -1


def get_block(height: int) -> dict:
    url = f"{RPC_URL}/block/{height}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error while fetching block {height}: {http_err}")
    except Exception as err:
        logger.error(f"Error fetching block {height} from node: {err}")
    return None


def send_block(producer: KafkaProducer, block: dict):
    topic = os.getenv("TOPIC_NAME", "blocks")
    try:
        timestamp = datetime.now(timezone.utc).isoformat() + "Z"  # ISO 8601 UTC
        payload = {
            "timestamp": timestamp,
            "data": block,
        }

        # Hash based on timestamp + data JSON
        to_hash = f"{timestamp}{json.dumps(block, sort_keys=True)}"
        payload["id"] = hashlib.sha256(to_hash.encode("utf-8")).hexdigest()

        future = producer.send(topic, value=payload)
        record_metadata = future.get(timeout=10)
        logger.info(
            f"Block {block['height']} sent to Kafka with ID {payload['id']} "
            f"→ partition {record_metadata.partition}, offset {record_metadata.offset}"
        )
    except Exception as e:
        logger.error(f"Failed to send block {block.get('height', '?')}: {e}")


def main(interval: int):
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    conn = init_db()
    producer = create_kafka_producer()

    logger.info(f"Starting block producer with {interval}s interval.")
    try:
        while RUNNING:
            try:
                tip_height = get_tip_height()
                confirmed_height = tip_height - 6

                if confirmed_height < 0:
                    logger.warning("Chain too short to publish any blocks.")
                    continue

                if not has_seen_block(conn, confirmed_height):
                    block = get_block(confirmed_height)
                    if block:
                        send_block(producer, block)
                        mark_block_as_seen(conn, confirmed_height)
                    else:
                        logger.warning(f"No block data returned for height {confirmed_height}")
                else:
                    logger.info(f"Block {confirmed_height} already sent.")
            except Exception as e:
                logger.error(f"Error during processing: {e}")

            time.sleep(interval)
    finally:
        logger.info("Shutting down producer and closing DB.")
        producer.flush()
        producer.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bitcoin block Kafka producer")
    parser.add_argument("--interval", type=int, default=60, help="Polling interval in seconds")
    args = parser.parse_args()

    main(args.interval)
