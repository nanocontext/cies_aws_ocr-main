# file test.py
import os
import uuid
from datetime import datetime

import boto3
from boto3.dynamodb.conditions import Attr, Key

# Get environment variable if it's defined
# Make sure to set the environment variable before running
# If the value is not set, it will use default boto behaviour
# and use values from AWS_REGION or AWS_DEFAULT_REGION.
endpoint_url = os.environ.get('AWS_DYNAMODB_ENDPOINT_URL', None)
# Using (high level) resource, same keyword for boto3.client
#resource = boto3.resource('dynamodb', endpoint_url=endpoint_url)
resource = boto3.resource('dynamodb')
resource.region_name = 'us-east-2'
tables = resource.tables.all()
for table in tables:
    print(table)
userid = 'lmfao123'
jobid = str(uuid.uuid4())
ddbTable = resource.Table('spi-api-gw-TrackingTable-18KN491GOIIEA')
documenet_id = str(uuid.uuid4())
ddbTable.put_item(Item={'documentId': documenet_id, 'userId': userid, 'siteId': 'xxx123', 'filename': 'test', 'jobId': jobid, 'jobStatus': 'SUBMITTED',
            'jobSubmitTime':  datetime.now().isoformat()})
# print(f"Running in AWS SAM local: {os.environ}")
# print(f"{resource}")
# print(ddbTable.query(
#     IndexName='jobIdByUserIdGSI',
#     KeyConditionExpression=Key('userId').eq(userid))
# )
items = ddbTable.scan()['Items']
for item in items:
    print(item)


item={'jobId': '0b168aac2805e14b5236504a0b53797b9edb7994833397b44dd0e4b37075032d', 'status': 'SUCCEEDED'}
# response = table.get_item(
#     Key= {'jobId' : item['jobId']}
# )
# print(f"response is: {response}")

# response = table.query(
#     KeyConditionExpression=Key('jobId').eq(item['jobId'])
# )
response = ddbTable.scan(
    FilterExpression=Attr('jobId').eq(item['jobId'])
)
items = response['Items']
print(f"items: {items}")
if len(items) == 0 or items is None:
    print("no items")
    exit(1)
print(f"status is {items[0].get('jobStatus')}")