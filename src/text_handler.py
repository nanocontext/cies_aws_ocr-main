
import os
import boto3
import json

from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.logging import correlation_paths
from cies_ocr_core import CiesOcrCore
import http_response

from cies_ocr_core import METADATA_KEY_FILE_NAME
from cies_ocr_core import METADATA_KEY_USER_ID
from cies_ocr_core import METADATA_KEY_SITE_ID
from cies_ocr_core import TAG_KEY_STATUS
from cies_ocr_core import TAG_JOB_ID

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

@tracer.capture_lambda_handler
@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST, log_event=True)
@metrics.log_metrics(capture_cold_start_metric=True)
def lambda_handler(event, context) -> dict:
    logger.debug(f"OCR API - Inside GET lambda: event {event} context {context}")

    try:
        path = event.get("path")
        # the path is expected to be something like: /text/<job_id>, where text is a constant
        document_id = cies_ocr_core.return_last_path_element(path)
        logger.debug(f"document_id={document_id}")
        
        headers = cies_ocr_core.get_headers(event)
        logger.debug(f"newHeaders={headers}")

        user_id = headers.get(METADATA_KEY_USER_ID) if METADATA_KEY_USER_ID in headers else "unknown"
        site_id = headers.get(METADATA_KEY_SITE_ID) if METADATA_KEY_SITE_ID in headers else "unknown"
        if 'ACCEPT' in headers:
            accept_type = headers.get('ACCEPT') 
        else:
            accept_type = "application/json"

        if accept_type == "application/json":
            metadata = cies_ocr_core.get_json_metadata(document_id)
        else:
            metadata = cies_ocr_core.get_text_metadata(document_id)

        if metadata is None:
            return http_response.format_404_response(document_id)
        
        logger.debug(f"metadata={metadata}")
        if 'Content-Length' in metadata:
            content_length = metadata['Content-Length'] 
        else:
           content_length = cies_ocr_core.LARGE_FILE_THRESHOLD + 1
        # results greater than 1MB must be retrieved directly from S3 using a presigned URL
        logger.debug(f"content_length is {content_length}")
        if int(content_length) >= cies_ocr_core.LARGE_FILE_THRESHOLD:
            logger.debug(f"handling as a large file")
            presigned_url = cies_ocr_core.get_presigned_get_url(document_id, accept_type)
            return http_response.format_302_response(presigned_url)
        else:
            # results less than 1MB may be returned as the response body
            logger.debug(f"NOT handling as a large file")
            result = cies_ocr_core.get_text(user_id, site_id, document_id)
            logger.debug(f"result={result}")
            return http_response.format_200_response(metadata, json.dumps(result))
    except Exception as e:
        logger.error(f"Error: {e}")
        return http_response.format_500_response(e)

# ============================================================================================================================================
# The request, from an Application Load Balancer looks something like the following.
# ============================================================================================================================================
#
# {
#     "requestContext": {
#         "elb": {
#             "targetGroupArn": "arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/lambda-279XGJDqGZ5rsrHC2Fjr/49e9d65c45c6791a"
#         }
#     },
#     "httpMethod": "GET",
#     "path": "/text/<document_id>"
#     "headers": {
#         "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
#         "accept-encoding": "gzip",
#         "accept-language": "en-US,en;q=0.9",
#         "connection": "keep-alive",
#         "host": "lambda-alb-123578498.us-east-1.elb.amazonaws.com",
#         "upgrade-insecure-requests": "1",
#         "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/71.0.3578.98 Safari/537.36",
#         "x-amzn-trace-id": "Root=1-5c536348-3d683b8b04734faae651f476",
#         "x-forwarded-for": "72.12.164.125",
#         "x-forwarded-port": "80",
#         "x-forwarded-proto": "http",
#         "x-imforwards": "20"
#     },
#     "body": "",
#     "isBase64Encoded": False
# }

# ============================================================================================================================================
# The expected response, to the Application Load Balancer should look something like the following.
# ============================================================================================================================================
# {
#     "statusCode": 200,
#     "statusDescription": "200 OK",
#     "isBase64Encoded": False,
#     "headers": {
#         "Content-Type": "text/html"
#     },
#     "body": "<h1>Hello from Lambda!</h1>"
# }