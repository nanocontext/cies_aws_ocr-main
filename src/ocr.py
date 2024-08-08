import base64
import json
import os
from datetime import datetime
from pathlib import Path

import boto3
from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.event_handler import (
    APIGatewayRestResolver,
    CORSConfig,
    Response,
    content_types,
)
from aws_lambda_powertools.logging import correlation_paths
from botocore.exceptions import ClientError

tracer = Tracer()
logger = Logger()
logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))
metrics = Metrics(namespace="SpiTestApp", service="APP")
cors_config = CORSConfig(allow_origin="*", allow_headers=["x-test"], max_age=300)
app = APIGatewayRestResolver(cors=cors_config, debug=True)

s3 = boto3.client('s3')
sns = boto3.client('sns')
txt = boto3.client('textract')

s3_bucket = os.getenv('S3_TEXTRACT_BUCKET')
role_arn = os.getenv('OCR_ROLE_ARN')
sns_topic_arn = os.getenv('SNS_TOPIC_ARN')


def get_secret(secret_name, region_name):
    """ get username/password from AWS key store, return a dict object
    """
    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )
    secret = None

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
        secret = json.loads(get_secret_value_response['SecretString'])
    except ClientError as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        raise e

    return secret

def save_file(filename, fileBlob):
    logger.debug(f"saving file: {filename} to bucket {s3_bucket}")
    try:
        s3.put_object(
        Bucket= s3_bucket,
        Key=filename,
        Body=fileBlob
    )
    except Exception as e:
        logger.error(f"Error saving file: {e}")

def save_to_ddb(item):
    sam_local = os.getenv("AWS_SAM_LOCAL", "false")
    region = os.getenv("AWS_REGION")
    table_name = os.getenv("TRACKING_TABLE", "TrackingTable")
    ddbTable = None
    if sam_local == "true" :
        logger.debug(f"Running in AWS SAM local: {os.environ}")
        ddbTable = boto3.resource('dynamodb', endpoint_url="http://dynamo-local:8000").Table(table_name)

    else:
        logger.debug(f"Running in AWS: {os.environ}")
        ddbTable = boto3.resource('dynamodb', region_name=region).Table(table_name)
    logger.debug(f"ddbTable={ddbTable}, item={item}")
    # update the database
    if ddbTable is not None:
        ddbTable.put_item(
            Item=item
        )
    else:
        raise Exception("ddbTable is None")

@app.post("/ocr", cors=True)
@tracer.capture_method
def submit_job():
    event = app.current_event
    logger.debug(f"this is a POST single page ocr event: {event}")

    try:
        # file_content = base64.b64decode(event['content'])
        body = base64.b64decode(event['body'])
        logger.debug(" have a body, getting headers")
        headers = event.get("headers")
        logger.debug(f"headers={headers}")
        newHeaders = {k.upper():v for k,v in headers.items()}
        logger.debug(f"newHeaders={newHeaders}")
        file_name = newHeaders.get("FILENAME")
        logger.debug(f"saving file {file_name}")
        document_id = Path(file_name).stem
        logger.debug(f"document_id={document_id}")
        save_file(file_name, body)
        logger.debug("starting text analysis")
        result = txt.start_document_analysis(
            DocumentLocation={
                'S3Object': {
                    'Bucket': s3_bucket,
                    'Name': file_name
                }},
            FeatureTypes=['LAYOUT'],
            JobTag=document_id,
            NotificationChannel={'RoleArn': role_arn, 'SNSTopicArn': sns_topic_arn})
        logger.debug(f"result={result}")

        job = {
            'documentId': document_id,
            'userId': newHeaders.get('USERID'),
            'siteId': newHeaders.get('SITEID'),
            'jobId': result['JobId'],
            'filename': file_name,
            'jobStatus': 'SUBMITTED',
            'jobSubmitTime':  datetime.now().isoformat(),
        }
        save_to_ddb(job)

        response = {"JobId": result['JobId']}
        logger.debug(f"response = {response}")

        return response
    except Exception as e:
        logger.error(f"Error submitting job: {e}")
        raise e



@tracer.capture_lambda_handler
@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST, log_event=True)
def lambda_handler(event, context) -> dict:
    logger.info(f"OCR API - Inside OCR lambda: event {event} context {context}")
    logger.info(f"s3_bucket {s3_bucket}, role_arn {role_arn}, sns_topic_arn {sns_topic_arn}")
    try:
        return app.resolve(event, context)
    except Exception as e:
        raise e
