# Serverless OT-Gateway: Integrazione OPC UA FX e AWS Cloud

Questo repository contiene il boilerplate completo per l'implementazione di un'architettura ibrida Edge-to-Cloud ad altissima efficienza. Il sistema funge da ponte tra le reti operative industriali basate su Time-Sensitive Networking (TSN) e il cloud AWS, abbattendo drasticamente i costi di ingestione dei dati ad alta frequenza.

Il gateway intercetta i pacchetti di telemetria basati su protocollo OPC UA Field eXchange (FX) e codifica UADP, li accumula in un buffer in memoria e li trasmette ad AWS API Gateway in modalità batch tramite chiamate HTTP POST asincrone.

## Architettura del Sistema

L'infrastruttura si divide in due macro-moduli indipendenti:

*   **Lato Edge (Fabbrica):** Un'applicazione Python asincrona dockerizzata, concepita per essere eseguita su PC industriali (es. Advantech) o dispositivi edge (es. NVIDIA Jetson Orin). Il container opera in modalità `network_mode: "host"` per catturare il traffico UDP multicast in tempo reale (Soft-RealTime) senza latenze di virtualizzazione di rete.
*   **Lato Cloud (AWS):** Uno stack Serverless gestito interamente come codice (IaC) tramite AWS SAM. Include un API Gateway HTTP, una funzione Lambda per il parsing dei batch e una tabella Amazon DynamoDB per la storicizzazione persistente delle serie temporali.

## Struttura del Pacchetto

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

## Prerequisiti

Per eseguire il deployment di questa infrastruttura sono richiesti:
*   Un account AWS attivo con privilegi di amministrazione (IAM User con policy `AdministratorAccess`).
*   **AWS CLI** configurata con le proprie chiavi di accesso (`aws configure`).
*   **AWS SAM CLI** installata sulla macchina di sviluppo.
*   **Docker** installato sul dispositivo Edge di destinazione.

---

## Guida al Deployment

### Fase 1: Creazione dell'infrastruttura Cloud (AWS)

Il backend cloud viene generato in pochi minuti tramite AWS SAM. Questo processo creerà le risorse necessarie senza configurazioni manuali sulla console AWS.

1. Aprire il terminale e navigare nella directory `cloud/`.
2. Eseguire la build del progetto:
   ```bash
   sam build
   ```
3. Avviare il deployment guidato:
   ```bash
   sam deploy --guided
   ```
4. Durante il setup interattivo, accettare i parametri di default, assicurandosi di rispondere `y` (yes) alle seguenti voci:
   * `Confirm changes before deploy`
   * `Allow SAM CLI IAM role creation`
   * `TelemetryPost may not have authorization defined, Is this okay?`
   * `Save arguments to configuration file`
5. Al termine del processo, CloudFormation restituirà un output verde contenente il **GatewayEndpoint** (es. `https://xyz123.execute-api.eu-central-1.amazonaws.com/telemetry`). Copiare questo URL.

### Fase 2: Configurazione e Avvio del Gateway Edge

Il nodo edge deve essere configurato per puntare alla nuova infrastruttura appena creata.

1. Aprire il file `edge/Serverless_Gateway.py`.
2. Individuare la variabile `AWS_API_GATEWAY_URL` e sostituire la stringa con il **GatewayEndpoint** copiato nel passaggio precedente.
3. Trasferire la cartella `edge/` sul dispositivo di fabbrica (es. il modulo Jetson Orin).
4. Navigare nella cartella tramite terminale e costruire l'immagine Docker:
   ```bash
   docker build -t serverless-ot-gateway .
   ```
5. Avviare il container agganciandolo direttamente alla scheda di rete dell'host:
   ```bash
   docker run -d --name ot-gateway --network host --restart always serverless-ot-gateway
   ```

---

## Ottimizzazione e Parametri Avanzati

Il core del vantaggio competitivo di questo Gateway risiede nelle regole di invio asincrono configurabili nel file `Serverless_Gateway.py`. La classe `ServerlessGateway` accetta due parametri fondamentali per il tuning delle prestazioni:

*   **`self.batch_size` (Default: 500):** Definisce il numero massimo di punti di telemetria (JointPosition, Temperature, Vibration, Voltage) da accumulare in RAM prima di forzare l'invio al cloud. Aumentare questo valore riduce ulteriormente le chiamate API (e i costi), ma richiede più memoria sul dispositivo edge.
*   **`self.flush_interval` (Default: 1.0 secondi):** Il tempo massimo di attesa. Se la rete OT produce dati lentamente e il buffer non raggiunge il `batch_size` entro questo intervallo, un task asincrono in background forza comunque l'invio del batch parziale per garantire la freschezza del dato su AWS.

Per applicare modifiche a questi parametri, è sufficiente riavviare il processo di build del container Docker e riavviare il servizio. I dati inizieranno a popolare istantaneamente la tabella DynamoDB designata nello stack.