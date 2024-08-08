import json
import os

import boto3
from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.utilities.data_classes import S3Event, event_source

from cies_ocr_core import CiesOcrCore;

# This Lambda handler is triggered by a new document message from S3.
# It will submit the document to Textract for OCR and update the 'ocr-status' tag in S3 to reflect
# a 'Submitted' status

tracer = Tracer()
logger = Logger()
logger.setLevel('DEBUG')
metrics = Metrics(namespace="SpiTestApp", service="APP")
s3 = boto3.client('s3')
sns = boto3.client('sns')
txt = boto3.client('textract')

cies_ocr_core = CiesOcrCore(
    os.getenv('SOURCE_BUCKET'), 
    os.getenv('DESTINATION_BUCKET'), 
    os.getenv('TEXTRACT_SERVICE_ROLE'), 
    os.getenv('TEXTRACT_STATUS_TOPIC'), 
    os.getenv("AWS_REGION"))

# ==========================================================================================
# S3 Event handling, this Lambda is notified when the "source" S3 bucket receives new documents
# ==========================================================================================
@logger.inject_lambda_context(log_event=True)
def lambda_handler(event: S3Event, context):
    logger.info(f"S3Event Event Lambda Handler - Inside lambda: event {event} context {context}")
    # Multiple records can be delivered in a single event
    for record in event["Records"]:
        logger.info(f"ocr_submission_handler record is {record}")

        s3 = record["s3"]
        logger.info(f"ocr_submission_handler s3 is {s3}")

        # the bucket ARN must reference the default source bucket, 'cause this value is ignored
        bucket = s3["bucket"]
        bucket_arn = bucket["arn"]

        object = s3["object"]
        object_key = object["key"]

        cies_ocr_core.submit_document_to_analysis(object_key)
        #cies_ocr_core.submit_document_to_ocr(object_key)

# {
#   "Records": [
#     {
#       "eventVersion": "2.1",
#       "eventSource": "aws:s3",
#       "awsRegion": "us-east-2",
#       "eventTime": "2019-09-03T19:37:27.192Z",
#       "eventName": "ObjectCreated:Put",
#       "userIdentity": {
#         "principalId": "AWS:AIDAINPONIXQXHT3IKHL2"
#       },
#       "requestParameters": {
#         "sourceIPAddress": "205.255.255.255"
#       },
#       "responseElements": {
#         "x-amz-request-id": "D82B88E5F771F645",
#         "x-amz-id-2": "vlR7PnpV2Ce81l0PRw6jlUpck7Jo5ZsQjryTjKlc5aLWGVHPZLj5NeC6qMa0emYBDXOo6QBU0Wo="
#       },
#       "s3": {
#         "s3SchemaVersion": "1.0",
#         "configurationId": "828aa6fc-f7b5-4305-8584-487c791949c1",
#         "bucket": {
#           "name": "DOC-EXAMPLE-BUCKET",
#           "ownerIdentity": {
#             "principalId": "A3I5XTEXAMAI3E"
#           },
#           "arn": "arn:aws:s3:::lambda-artifacts-deafc19498e3f2df"
#         },
#         "object": {
#           "key": "b21b84d653bb07b05b1e6b33684dc11b",
#           "size": 1305107,
#           "eTag": "b21b84d653bb07b05b1e6b33684dc11b",
#           "sequencer": "0C0F6F405D6ED209E1"
#         }
#       }
#     }
#   ]
# }