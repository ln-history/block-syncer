# 🧱 Block Syncer

This Python-based Kafka producer queries a [Bitcoin JSON-RPC explorer](https://github.com/janoside/btc-rpc-explorer) accessible via a `.onion` address using Tor. It retrieves blocks that are 6 confirmations deep and publishes them to a Kafka topic, avoiding duplicates even across restarts.

## 🛠 Requirements

- [Docker](https://www.docker.com/) & [Docker Compose](https://docs.docker.com/compose/) 
- [Kafka](https://kafka.apache.org/) cluster (SSL/SASL enabled)

## 🧠 How it works

After startup, the `block-syncer` waits for the Tor service to be fully operational using the [script](./wait-for-tor.sh) script. Once Tor is ready, the syncer begins querying the Bitcoin JSON-RPC explorer over the Tor network at regular intervals. The request interval can be configured via the `$REQUEST_INTERVAL_SECONDS` environment variable (default: `60` seconds).

## 🚀 Run 

- Setup environment variables
```bash
cp .example.env .env
```
Edit the secrets accordingly.

- Setup Kafka certs, for more information see [here](https://github.com/bitnami/containers/blob/main/bitnami/kafka/README.md#security).
```bash
touch certs/kafka.keystore.pem
touch certs/kafka.truststore.pem
```

- Run it
```bash
docker compose up -d --build
```
