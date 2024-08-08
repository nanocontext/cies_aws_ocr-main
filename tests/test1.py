import argparse
import datetime
import json
import uuid
from time import sleep

import requests


def main():
    # parse cmd line arguments
    argParser = argparse.ArgumentParser()
    argParser.add_argument("-u", "--url", help="url to connect to ", required=True)
    argParser.add_argument("-s", "--sample", help="sample file", required=True)


    args = vars(argParser.parse_args())

    t = datetime.datetime.utcnow()
    amz_date = t.strftime('%Y%m%dT%H%M%SZ')

    document_id = uuid.uuid4()
    filename = f'{document_id}.pdf'
    url = args['url']
    earl =  url + '/' + document_id
    #url = 'http://127.0.0.1:3000'
    # Specify the content type
    headers = {
        'Content-Type': 'application/octet-stream',
        'x-amz-date': amz_date,
            'Filename' : filename,
            'Siteid': 'site-r',
            'Userid' : 'buzzard-lips',
            'httpMethod':'POST'}

    # Read the file
    samplefile = args['sample']
    data = open(samplefile, 'rb').read()
    response = requests.post(url=earl,
            data=data,
            headers=headers)
    print(f"response: {response}")
    jobIdJson = json.loads(response.content.decode('utf-8'))
    print(f"jobId: {jobIdJson}")


    if response.status_code != 200:
        raise Exception(f"Error: {response.status}")

    print(f"response jobid: {jobIdJson['JobId']}")

    get_response = None
    sleep_time = 5
    # test status retrieval
    qstr = f"{url}/get_status?jobId={jobIdJson['JobId']}"
    get_response = requests.get(qstr)
    print(f"get_response: {get_response.content}")

    # loop on the get_status call, this hits the database not Textract
    # so we can bang away at it
    while True:
        get_response = requests.get(qstr)
        content = json.loads(get_response.content.decode('utf-8'))

        if content['status'].casefold() == 'SUCCEEDED'.casefold():
            print("\nJob Suceeded")
            break
        elif content['status'].casefold() == 'FAILED'.casefold():
            print("Job Failed, exiting")
            exit(1)
        elif content['status'].casefold() == 'ERROR'.casefold() :
            print("Job Error, exiting")
            exit(2)
        else:
            print(".",end='',flush=True)
        sleep(1)

    # test report retrieval

    print("Fetching OCR'd text")

    qstr = f"{url}/get_text?jobId={jobIdJson['JobId']}"
    get_response = requests.get(qstr)
    print(f"get_response: {get_response}")
    if get_response.status_code == 200:
        content = json.loads(get_response.content)
        reportText = content["parsedText"]
        print(reportText)
        # pages = len(reportText)
        # for i in range(pages):
        #     print(list(reportText.values())[i])


if __name__ == '__main__':
    main()