import json
import os

import boto3
from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.utilities.data_classes import SNSEvent, event_source

from cies_ocr_core import CiesOcrCore;

tracer = Tracer()
logger = Logger()
logger.setLevel('DEBUG')
metrics = Metrics(namespace="SpiTestApp", service="APP")

cies_ocr_core = CiesOcrCore(
    os.getenv('SOURCE_BUCKET'), 
    os.getenv('DESTINATION_BUCKET'), 
    os.getenv('TEXTRACT_SERVICE_ROLE'), 
    os.getenv('TEXTRACT_STATUS_TOPIC'), 
    os.getenv("AWS_REGION"))

# ============================================================================================================
# This Lambda handler is triggered by a notification from Textract.
# It will update the 'ocr-status' tag in S3 to reflect either a 'Successful' or
# a 'Failed' status. If the document recognition was successful then the document
# text (results of the OCR) will be copied to the #s destination bucket.
# ============================================================================================================
@event_source(data_class=SNSEvent)
@logger.inject_lambda_context(log_event=True)
def lambda_handler(event: SNSEvent, context):
    logger.info(f"SNS Event Lambda Handler - Inside lambda: event {event} context {context}")
    # Multiple records can be delivered in a single event
    for record in event.records:
        message = json.loads(record.sns.message)
        subject = record.sns.subject
        logger.debug(f"SNS Event Lambda Handler - Inside lambda: message {message} subject {subject}")

        document_id = message["JobTag"]
        status = message["Status"]

        cies_ocr_core.ocr_complete(document_id, status)

# Sample "failed" message
# 
# {
# 'JobId': 'd69cacc045ec1186bc58d995726df05b9ebe61f8892d07b89a06bcd97e538b7a', 
# 'Status': 'FAILED', 
# 'API': 'StartDocumentAnalysis', 
# 'JobTag': '1DAE93F8-646C-43B7-9981-9B41AE047881', 
# 'Timestamp': 1717616867091, 
# 'DocumentLocation': 
# {
#   'S3ObjectName': '1DAE93F8-646C-43B7-9981-9B41AE047881', 
#   'S3Bucket': 'project-ocr-cies-bucket-source-local'
# }
# }
