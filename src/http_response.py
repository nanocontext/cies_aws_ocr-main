import json

# Creates a response object with the status code and body, something like this:
# {
#     "statusCode": 200,
#     "statusDescription": "200 OK",
#     "isBase64Encoded": False,
#     "headers": {
#         "Content-Type": "application/json"
#     },
#     "body": "body"
# }
# Given a Dict of header keys and values, create a 200 response including the given headers
def format_200_response(headers: dict, body:  str):
    result = {}

    result["statusCode"] = 200
    result["statusDescription"] = "200 OK"

    if headers:
        result["headers"] = headers

    if body:
        result["body"] = body
    return result

def format_200_head_response(headers: dict):
    result = {}

    result["statusCode"] = 200
    result["statusDescription"] = "200 OK"

    if headers:
        result["headers"] = headers

    return result

def format_202_response(document_id : str) -> str:
    result = {}

    result["statusCode"] = 202
    result["statusDescription"] = "202 Accepted"

    return result

# The HyperText Transfer Protocol (HTTP) 302 Found redirect status response code indicates 
# that the resource requested has been temporarily moved to the URL given by the Location header.
def format_302_response(destination : str) -> str:
    result = {}

    result["statusCode"] = 302
    result["statusDescription"] = "302 Found"

    result["headers"] = {
        "Location": destination
    }

    return result

def format_400_response(err_msg : str):
    result = {}

    result["statusCode"] = 400
    result["statusDescription"] = "400 Bad Request"

    if err_msg:
        result["body"] = err_msg

    return result

def format_404_response(document_id : str):
    result = {}

    result["statusCode"] = 404
    result["statusDescription"] = "404 Not Found"

    if document_id:
        result["body"] = f"Document {document_id} not found"

    return result

def format_409_response(document_id : str):
    result = {}

    result["statusCode"] = 409
    result["statusDescription"] = "409 Conflict"

    if document_id:
        result["body"] = f"Document {document_id} already exists and may not be re-created"
    else:
        result["body"] = f"Document already exists and may not be re-created"

    return result

def format_500_response(err_msg : str):
    result = {}

    result["statusCode"] = 500
    result["statusDescription"] = "500 Internal Server Error"

    if err_msg:
        result["body"] = err_msg

    return result
