"""
DESCRIZIONE:
    Serverless OT-Gateway (Ex Subscriber).
    Riceve pacchetti UDP (UADP) ad alta frequenza da reti TSN, 
    effettua un batching intelligente in memoria e li inoltra 
    verso un endpoint Cloud (AWS API Gateway) via HTTP POST.
"""

import asyncio
import logging
import time
from datetime import datetime
import aiohttp
import json

from asyncua import ua, pubsub
from asyncua.pubsub.udp import UdpSettings
from dataclasses import dataclass, field

# --- CONFIGURAZIONE CLOUD ---
# Endpoint AWS API Gateway o Webhook di test
AWS_API_GATEWAY_URL = ""

# --- CONFIGURAZIONE PUBSUB ---
@dataclass
class PubSubCFG:
    PublisherID: ua.Variant = field(default_factory=lambda: ua.Variant(ua.UInt16(1)))
    # FIX 1: Il Publisher invia un UInt32, il Subscriber deve filtrare per UInt32 (non UInt16)
    WriterGroupId: ua.UInt32 = field(default_factory=lambda: ua.UInt32(1))
    DataSetWriterId: ua.UInt16 = field(default_factory=lambda: ua.UInt16(100)) 
    # FIX 2: In ascolto su tutte le interfacce per evitare i blocchi del loopback di Windows
    Url: str = "opc.udp://0.0.0.0:4840"

CFG = PubSubCFG()


def create_meta_data():
    dataset = pubsub.DataSetMeta.Create("100")
    dataset.add_scalar("JointPosition", ua.VariantType.Double)
    dataset.add_scalar("Temperature", ua.VariantType.Double)
    dataset.add_scalar("Vibration", ua.VariantType.Double)
    dataset.add_scalar("Voltage", ua.VariantType.Double)
    return dataset


class ServerlessGateway:
    def __init__(self):
        # 1. REGOLE DEL BATCHING CUSTOM
        self.batch_size = 500
        self.flush_interval = 1.0  # 1 secondo
        
        self.buffer = []
        self.last_flush_time = time.time()
        self.session = None  # Inizializzato al primo uso nell'event loop
        self.flush_task = None  # Inizializzato esternamente per evitare errori di event loop
        
        print(f"Serverless Gateway Inizializzato (Batch: {self.batch_size}pt o {self.flush_interval}s)")

    async def start_background_task(self):
        """Avvia il task in background quando l'event loop è effettivamente in esecuzione"""
        self.flush_task = asyncio.create_task(self.periodic_flush())

    async def get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def on_dataset_received(self, _meta: pubsub.DataSetMeta, fields: list[pubsub.DataSetValue]):
        def get_val(obj):
            while hasattr(obj, 'Value'):
                obj = obj.Value
            return obj

        try:
            # Estrazione timestamp
            ts_source = None
            if hasattr(fields[0], 'Value') and hasattr(fields[0].Value, 'SourceTimestamp'): 
                 ts_source = fields[0].Value.SourceTimestamp
            if ts_source is None:
                ts_source = datetime.now()
            
            # Estrazione dati
            pos = float(get_val(fields[0]))
            temp = float(get_val(fields[1]))
            vib = float(get_val(fields[2]))
            volt = float(get_val(fields[3]))
            
            # Creiamo il dizionario JSON
            payload = {
                "timestamp": ts_source.isoformat(),
                "source": "Advantech_Device",
                "JointPosition": pos,
                "Temperature": temp,
                "Vibration": vib,
                "Voltage": volt
            }
            
            # Aggiungiamo al buffer in RAM
            self.buffer.append(payload)

            # CONDIZIONE 1: Abbiamo raggiunto i 500 punti (Batch Size)
            if len(self.buffer) >= self.batch_size:
                await self.flush_data()

        except Exception as e:
            print(f"Errore elaborazione pacchetto locale: {e}")

    async def periodic_flush(self):
        """Task in background che controlla la CONDIZIONE 2: Timeout di 1 secondo"""
        while True:
            await asyncio.sleep(0.1)  # Controlla ogni 100ms
            if len(self.buffer) > 0 and (time.time() - self.last_flush_time) >= self.flush_interval:
                await self.flush_data()

    async def flush_data(self):
        """Impacchetta i dati accumulati e fa la POST su Cloud"""
        if not self.buffer:
            return

        # "Congeliamo" il batch attuale e svuotiamo subito il buffer 
        # per non bloccare la ricezione dei nuovi pacchetti UDP
        batch_to_send = self.buffer[:]
        self.buffer.clear()
        self.last_flush_time = time.time()

        try:
            session = await self.get_session()
            
            # Invio asincrono verso il Webhook/API Gateway Cloud
            async with session.post(AWS_API_GATEWAY_URL, json={"telemetry_batch": batch_to_send}) as response:
                if response.status not in (200, 201):
                    print(f"Errore AWS API Gateway [{response.status}]: {await response.text()}")
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] OK: Batch di {len(batch_to_send)} elementi inviato ad AWS.")
        
        except Exception as e:
            print(f"Errore di rete durante l'invio ad AWS: {e}")

    async def on_state_change(self, meta: pubsub.DataSetMeta, state: ua.PubSubState):
        print(f"Stato connessione PubSub: {state.name}")

    async def close(self):
        print("Svuotamento buffer e chiusura connessioni...")
        if self.flush_task:
            self.flush_task.cancel()
        await self.flush_data()
        if self.session and not self.session.closed:
            await self.session.close()
        print("Chiuso correttamente.")


if __name__ == "__main__":
    handler_ref = None
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        handler_ref = ServerlessGateway()
        metadata = create_meta_data()
        logging.basicConfig(level=logging.WARNING)

        reader_group = pubsub.ReaderGroup.new(
            name="ReaderGroup1",
            enable=True,
            reader=[
                pubsub.DataSetReader.new(
                    CFG.PublisherID,
                    CFG.WriterGroupId,
                    CFG.DataSetWriterId,
                    metadata,
                    name="FXReader",
                    subscribed=handler_ref,
                    enabled=True,
                )
            ],
        )

        connection = pubsub.PubSubConnection.udp_uadp(
            "Subscriber Connection",
            ua.UInt16(1),
            UdpSettings(Url=CFG.Url),
            reader_groups=[reader_group],
        )

        ps = pubsub.PubSub.new(connections=[connection])
        connection._app = ps

        async def runner():
             print("In attesa di pacchetti UADP sulla porta 4840...")
             
             # Avvio del task in background all'interno dell'event loop attivo
             await handler_ref.start_background_task()
             
             async with ps:
                while True:
                    await asyncio.sleep(1)

        loop.run_until_complete(runner())

    except KeyboardInterrupt:
        print("\nStop richiesto dall'utente.")
    finally:
        if handler_ref:
            # Chiusura asincrona per garantire l'invio dell'ultimo batch
            loop.run_until_complete(handler_ref.close())