import base64
import os
import boto3

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
    logger.info(f"OCR API - Inside OCR lambda: event {event} context {context}")

    try:
        method = event.get("httpMethod")
        document_id = cies_ocr_core.return_last_path_element(event.get("path"))

        logger.debug(f"httpMethod={method}, document_id={document_id}")

        headers = cies_ocr_core.get_headers(event)
        user_id = headers.get('USERID') if "USERID" in headers else "unknown"
        site_id = headers.get('SITEID') if "SITEID" in headers else "unknown"

        match method:
            case "HEAD":
                document_metadata = cies_ocr_core.get_document_metadata(document_id)
                if document_metadata is None:
                    result = http_response.format_404_response(document_id)
                else:
                    result = http_response.format_200_head_response(document_metadata)

            case "GET":
                document_metadata = cies_ocr_core.get_document_metadata(document_id)
                if document_metadata is None:
                    result = http_response.format_404_response(document_id)
                else:
                    # the stored_document result is the document body, metadata plus a bunch of other stuff
                    stored_document = cies_ocr_core.get_document_from_source_bucket(user_id, site_id, document_id)
                    body = stored_document['Body'].read()
                    body_base64 = str(base64.b64encode(body))
                    result = http_response.format_200_response(document_metadata, body_base64)

            case "POST":
                logger.info(f"lambda_handler POST {document_id}")
                document_metadata = cies_ocr_core.get_document_metadata(document_id)
                if document_metadata is None:
                    file_name = headers.get(METADATA_KEY_FILE_NAME) if METADATA_KEY_FILE_NAME in headers else document_id
                    base64_encoded = event.get("isBase64Encoded") if "isBase64Encoded" in event else False
                    content_type = headers.get("CONTENT-TYPE") if "CONTENT-TYPE" in headers else "text/plain"

                    logger.debug(f"base64_encoded={base64_encoded}, file_name={file_name},content_type={content_type}")
                    if base64_encoded:
                        body = base64.b64decode(event['body'])
                    else:
                        body = event['body']
                    logger.debug(f"body={body[:128]}")
                    cies_ocr_core.save_document_to_source_bucket(user_id, site_id, document_id, file_name, content_type, "New", body)
                    result = http_response.format_202_response(document_id)
                else:
                    result = http_response.format_409_response(document_id)

            case "PUT":
                logger.info(f"lambda_handler PUT {document_id}")
                document_metadata = cies_ocr_core.get_document_metadata(document_id)
                if document_metadata is None:
                    result = http_response.format_404_response(document_id)
                else:
                    file_name = headers.get("FILENAME") if "FILENAME" in headers else document_id
                    content_type = headers.get("CONTENT-TYPE") if "CONTENT-TYPE" in headers else "text/plain"
                    base64_encoded = event.get("isBase64Encoded") if "isBase64Encoded" in event else False

                    logger.debug(f"base64_encoded={base64_encoded}")
                    if base64_encoded:
                        body = base64.b64decode(event['body'])
                    else:
                        body = event['body']
                    logger.debug(f"body={body[:128]}")
                    cies_ocr_core.save_document_to_source_bucket(user_id, site_id, document_id, file_name, content_type, "New", body)
                    result = http_response.format_202_response(document_id)
                    
        logger.debug(f"result={result}")   
        return result
    except Exception as e:
        raise e

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