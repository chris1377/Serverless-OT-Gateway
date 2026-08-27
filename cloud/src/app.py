import json
import os
import boto3
from decimal import Decimal

# Inizializza la connessione al DB usando la variabile d'ambiente
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['TABLE_NAME'])

def lambda_handler(event, context):
    try:
        body = json.loads(event.get('body', '{}'))
        batch = body.get('telemetry_batch', [])
        
        if not batch:
            return {"statusCode": 200, "body": "Nessun dato nel batch"}
            
        # Scrittura massiva su DynamoDB
        with table.batch_writer() as writer:
            for item in batch:
                # DynamoDB richiede che i numeri float siano convertiti in Decimal
                item_decimal = json.loads(json.dumps(item), parse_float=Decimal)
                writer.put_item(Item=item_decimal)
                
        print(f"Successo: {len(batch)} record salvati nel database.")
        
        return {
            "statusCode": 200,
            "body": json.dumps({"message": f"Batch da {len(batch)} record processato e salvato."})
        }
    except Exception as e:
        print(f"Errore di scrittura DB: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"message": "Errore interno del server"})
        }