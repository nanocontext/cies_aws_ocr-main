#
# create table script for local dynamodb
aws dynamodb delete-table --table-name TrackingTable --endpoint-url http://localhost:8000
aws dynamodb list-tables --endpoint-url http://localhost:8000
aws dynamodb create-table --cli-input-json file://json/create-table.json --endpoint-url http://localhost:8000
