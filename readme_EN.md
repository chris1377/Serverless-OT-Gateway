# Serverless OT-Gateway: OPC UA FX and AWS Cloud Integration

This repository contains the complete boilerplate for implementing a highly efficient Edge-to-Cloud hybrid architecture. The system acts as a bridge between industrial operational networks based on Time-Sensitive Networking (TSN) and the AWS cloud, drastically reducing the ingestion costs of high-frequency data.

The gateway intercepts telemetry packets based on the OPC UA Field eXchange (FX) protocol and UADP encoding, accumulates them in an in-memory buffer, and transmits them to an AWS API Gateway in batch mode via asynchronous HTTP POST calls.

## System Architecture

The infrastructure is divided into two independent macro-modules:

*   **Edge Side (Factory):** A dockerized asynchronous Python application, designed to run on industrial PCs (e.g., Advantech) or edge devices (e.g., NVIDIA Jetson Orin). The container operates in `network_mode: "host"` to capture real-time UDP multicast traffic (Soft-RealTime) without network virtualization latency.
*   **Cloud Side (AWS):** A Serverless stack entirely managed as Infrastructure as Code (IaC) via AWS SAM. It includes an HTTP API Gateway, a Lambda function for batch parsing, and an Amazon DynamoDB table for the persistent storage of time-series data.

## Package Structure

```text
serverless-ot-gateway/
├── edge/
│   ├── Dockerfile
│   ├── Serverless_Gateway.py
│   └── requirements.txt
├── cloud/
│   ├── template.yaml
│   ├── samconfig.toml
│   └── src/
│       ├── app.py
│       └── requirements.txt
└── README.md
```

## Prerequisites

To deploy this infrastructure, the following are required:
*   An active AWS account with administrative privileges (IAM User with `AdministratorAccess` policy).
*   **AWS CLI** configured with your access keys (`aws configure`).
*   **AWS SAM CLI** installed on the development machine.
*   **Docker** installed on the target Edge device.

---

## Deployment Guide

### Phase 1: Cloud Infrastructure Creation (AWS)

The cloud backend is generated in a few minutes via AWS SAM. This process will create the necessary resources without manual configuration on the AWS console.

1. Open the terminal and navigate to the `cloud/` directory.
2. Build the project:
   ```bash
   sam build
   ```
3. Start the guided deployment:
   ```bash
   sam deploy --guided
   ```
4. During the interactive setup, accept the default parameters, making sure to answer `y` (yes) to the following prompts:
   * `Confirm changes before deploy`
   * `Allow SAM CLI IAM role creation`
   * `TelemetryPost may not have authorization defined, Is this okay?`
   * `Save arguments to configuration file`
5. At the end of the process, CloudFormation will output a green block containing the **GatewayEndpoint** (e.g., `https://xyz123.execute-api.eu-central-1.amazonaws.com/telemetry`). Copy this URL.

### Phase 2: Edge Gateway Configuration and Startup

The edge node must be configured to point to the newly created infrastructure.

1. Open the `edge/Serverless_Gateway.py` file.
2. Locate the `AWS_API_GATEWAY_URL` variable and replace the string with the **GatewayEndpoint** copied in the previous step.
3. Transfer the `edge/` folder to the factory device (e.g., the Jetson Orin module).
4. Navigate to the folder via terminal and build the Docker image:
   ```bash
   docker build -t serverless-ot-gateway .
   ```
5. Start the container, attaching it directly to the host's network interface:
   ```bash
   docker run -d --name ot-gateway --network host --restart always serverless-ot-gateway
   ```

---

## Optimization and Advanced Parameters

The core competitive advantage of this Gateway lies in the configurable asynchronous sending rules in the `Serverless_Gateway.py` file. The `ServerlessGateway` class accepts two fundamental parameters for performance tuning:

*   **`self.batch_size` (Default: 500):** Defines the maximum number of telemetry points (JointPosition, Temperature, Vibration, Voltage) to accumulate in RAM before forcing the upload to the cloud. Increasing this value further reduces API calls (and costs), but requires more memory on the edge device.
*   **`self.flush_interval` (Default: 1.0 seconds):** The maximum waiting time. If the OT network produces data slowly and the buffer does not reach the `batch_size` within this interval, a background asynchronous task will force the sending of the partial batch anyway to ensure data freshness on AWS.

To apply changes to these parameters, simply restart the Docker container build process and restart the service. The data will instantly start populating the designated DynamoDB table in the stack.