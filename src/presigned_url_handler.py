import os
import json

from cies_ocr_core import CiesOcrCore
from aws_lambda_powertools import Logger, Metrics, Tracer

tracer = Tracer()
logger = Logger()
logger.setLevel(os.getenv('LOG_LEVEL', 'DEBUG'))
metrics = Metrics(namespace="SpiTestApp", service="APP")

cies_ocr_core = CiesOcrCore(
    os.getenv('SOURCE_BUCKET'), 
    os.getenv('DESTINATION_BUCKET'), 
    os.getenv('TEXTRACT_SERVICE_ROLE'), 
    os.getenv('TEXTRACT_STATUS_TOPIC'), 
    os.getenv("AWS_REGION"))

# handles only the GET method
# Gets a "presigned" URL to allow the user to write directly to an S3 bucket/key
@tracer.capture_lambda_handler
def lambda_handler(event, context) -> dict:
    logger.info(f"OCR API - Inside OCR lambda: event {event} context {context}")

    try:
        document_id = cies_ocr_core.return_last_path_element(event.get("path"))
        presigned_post_result = cies_ocr_core.get_presigned_post_url(document_id)

        result = {
            'statusCode': 200,
            'statusDescription': '200 OK',
            'multiValueHeaders': False,
            'headers': {
                'content-type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'isBase64Encoded': False,
            'body': json.dumps(presigned_post_result)
        }

        logger.info(f"Returning {result}")
        return result
    
    except Exception as e:
        raise e

# The response from get_presigned_post_url looks something like this:
# {
# 	"url": "https://project-ocr-cies-bucket-source-local.s3.amazonaws.com/",
# 	"fields": {
# 		"key": "1DAE93F8-646C-43B7-9981-9B41AE047884",
# 		"AWSAccessKeyId": "ASIAZVYELKCWKNO6KRPX",
# 		"x-amz-security-token": "IQoJb3JpZ2luX2VjEA8aCXVzLWVhc3QtMSJIMEYCIQC+Xc88dgOaKMQf7TbYcD1qASRbSxfQfNzWqbqVhGFiuAIhAITdvVNIn2NUnFfP64z6cm5+avRMN9divmzCeAxXQcHKKpwDCKf//////////wEQAxoMNjY1MTkyMTkwMTI0Igw3wSxiUucqcoM7QEYq8AJC0Gqkh5a/Bv7lh6Y0xoD+zN4rM3qhWYr3gu3Hf+Ew1a0SIMbnZNBRynFwCbNj+Vh1fmYmjPR8qJtP/YPcfkWZ3QxXT6ZKXGcT65KFwz9PzxNEpuvTROdU35Bgx55S7kvRkv8hNrgu4tn39HtI0+3OSh5hZLcBq2F/pGHdBWv+TWHFe+5xD47DS7Ncr6N8L9aCYtnXVi8Sxcg9yMLaHs+GtocKXnV1u2gHj8Un1QnYV+Vg60PEbovZ17DDXVkDePWLoJLeHdubSNv2vWfYjNpfWrmaSl2uFkfxE3r2s8bXXhZRbvOB88PIwSUXUANi+e+v+kyXpKFSwxoTRlxhs7KtoRgpHg3GQuL7nMgkZAD27d2PhWMsB14P3oQo2rQvwgRQvDrw2eZDtyvHruK+ZfrcvpnEm40ODJoyqKrwY/o3EiLL4NAc8g5Q3e+6dljHYoyly/CxJ/6h24rrd90Bp7I1dvt6PqnpBWrKBAop7NgbCzC4nLGzBjqcAV4xb6Qm/m6ZJAzfbAgGxBUSMrdvOK8Twhg5cEDu0IB7+OZrA8ueJsTn3rkC4hdrFuvEYLdCfq7WaQL/TDBaWMaKvM74MvzmLGqirmLvZC795i14cS6JG3pL4MFuNPbah5qMeMTYHfpxZE85sBlSu1ueCkEwIhDtWD7oWfaUsNA9aRBQXByGUpwxE3E/46fFiH304xIr2EEaQxiaUA==",
# 		"policy": "eyJleHBpcmF0aW9uIjogIjIwMjQtMDYtMTRUMTQ6MTI6MDRaIiwgImNvbmRpdGlvbnMiOiBbeyJidWNrZXQiOiAicHJvamVjdC1vY3ItY2llcy1idWNrZXQtc291cmNlLWxvY2FsIn0sIHsia2V5IjogIjFEQUU5M0Y4LTY0NkMtNDNCNy05OTgxLTlCNDFBRTA0Nzg4NCJ9LCB7IngtYW16LXNlY3VyaXR5LXRva2VuIjogIklRb0piM0pwWjJsdVgyVmpFQThhQ1hWekxXVmhjM1F0TVNKSU1FWUNJUUMrWGM4OGRnT2FLTVFmN1RiWWNEMXFBU1JiU3hmUWZOeldxYnFWaEdGaXVBSWhBSVRkdlZOSW4yTlVuRmZQNjR6NmNtNSthdlJNTjlkaXZtekNlQXhYUWNIS0twd0RDS2YvLy8vLy8vLy8vd0VRQXhvTU5qWTFNVGt5TVRrd01USTBJZ3czd1N4aVV1Y3Fjb003UUVZcThBSkMwR3FraDVhL0J2N2xoNlkweG9EK3pONHJNM3FoV1lyM2d1M0hmK0V3MWEwU0lNYm5aTkJSeW5Gd0NiTmorVmgxZm1ZbWpQUjhxSnRQL1lQY2ZrV1ozUXhYVDZaS1hHY1Q2NUtGd3o5UHp4TkVwdXZUUk9kVTM1Qmd4NTVTN2t2Umt2OGhOcmd1NHRuMzlIdEkwKzNPU2g1aFpMY0JxMkYvcEdIZEJXditUV0hGZSs1eEQ0N0RTN05jcjZOOEw5YUNZdG5YVmk4U3hjZzl5TUxhSHMrR3RvY0tYblYxdTJnSGo4VW4xUW5ZVitWZzYwUEVib3ZaMTdERFhWa0RlUFdMb0pMZUhkdWJTTnYydldmWWpOcGZXcm1hU2wydUZrZnhFM3IyczhiWFhoWlJidk9CODhQSXdTVVhVQU5pK2UrditreVhwS0ZTd3hvVFJseGhzN0t0b1JncEhnM0dRdUw3bk1na1pBRDI3ZDJQaFdNc0IxNFAzb1FvMnJRdndnUlF2RHJ3MmVaRHR5dkhydUsrWmZyY3ZwbkVtNDBPREpveXFLcndZL28zRWlMTDROQWM4ZzVRM2UrNmRsakhZb3lseS9DeEovNmgyNHJyZDkwQnA3STFkdnQ2UHFucEJXcktCQW9wN05nYkN6QzRuTEd6QmpxY0FWNHhiNlFtL202WkpBemZiQWdHeEJVU01yZHZPSzhUd2hnNWNFRHUwSUI3K09ackE4dWVKc1RuM3JrQzRoZHJGdXZFWUxkQ2ZxN1dhUUwvVERCYVdNYUt2TTc0TXZ6bUxHcWlybUx2WkM3OTVpMTRjUzZKRzNwTDRNRnVOUGJhaDVxTWVNVFlIZnB4WkU4NXNCbFN1MXVlQ2tFd0loRHRXRDdvV2ZhVXNOQTlhUkJRWEJ5R1Vwd3hFM0UvNDZmRmlIMzA0eElyMkVFYVF4aWFVQT09In1dfQ==",
# 		"signature": "5hrrSIT81oag985GT6dFu7ybGpI="
# 	}
# }

