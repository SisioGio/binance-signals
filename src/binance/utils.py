import os
import boto3
import json

def get_secret():
    secret_name = os.environ['SECRET_NAME']
    region_name = 'eu-central-1'

    client = boto3.client('secretsmanager', region_name=region_name)
    response = client.get_secret_value(SecretId=secret_name)
    return json.loads(response['SecretString'])