# This class implements the capabilities of the CIES OCR process.
# This class is not specific to the external facing interface. In other words there should be no dependency 
# on whether this code is called from a Lambda, application server, etc ...

import json
import os
from datetime import datetime
import mimetypes

import boto3
from botocore.exceptions import ClientError
from botocore.client import Config

from aws_lambda_powertools import Logger, Metrics, Tracer
from collections import defaultdict

from textractcaller import (
    Textract_API,
    get_full_json,
)
from textractprettyprinter.t_pretty_print import get_text_from_layout_json

# ====================================================================================================
# Global Constants
# ====================================================================================================
# S3 metadata tags MUST be prefixed with x-amz-meta- to allow them to be written with S3 REST calls
METADATA_KEY_FILE_NAME = "x-amz-meta-file-name"
METADATA_KEY_USER_ID = "x-amz-meta-user-id"
METADATA_KEY_SITE_ID = "x-amz-meta-site-id"
# Tags are not sent or received as HTTP headers and are not prefixed
TAG_KEY_STATUS = "ocr-status"
TAG_JOB_ID = "job-id"

# ====================================================================================================
# Global References
# ====================================================================================================
tracer = Tracer()
logger = Logger()
logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))
metrics = Metrics(namespace="SpiTestApp", service="APP")

s3 = boto3.client('s3',config=Config(signature_version='s3v4'))
sns = boto3.client('sns')
txt = boto3.client('textract')

class CiesOcrCore:
    # Documents with a size above this number must be POSTed directly to the S3 destination
    # (OCR'd) Text files with greater than this number must be GET'd firectly from S3
    # The defined value should be less than the ELB (ALB) limit, allowing room for headers.
    LARGE_FILE_THRESHOLD = (1024 * 1024) - 2048

    source_bucket = None
    destination_bucket = None
    textract_service_role = None
    textract_status_topic = None
    aws_region = None
    presigned_url_expiration = 120

    def __init__(self, source_bucket: str, destination_bucket: str, textract_service_role: str, textract_status_topic: str, aws_region: str):
        logger.info(f"__init__({source_bucket}, {destination_bucket}, {textract_service_role}, {textract_status_topic}, {aws_region})")

        self.source_bucket = source_bucket
        self.destination_bucket = destination_bucket
        self.textract_service_role = textract_service_role
        self.textract_status_topic = textract_status_topic
        self.aws_region = aws_region

    # ====================================================================================================
    # This function generates a URL that allow a client to POST a document directly to S3
    def get_presigned_post_url(self, document_id: str):
        if not document_id:
            raise ValueError("document_id cannot be None or an empty string")
        
        logger.debug(f"get_presigned_post_url({self.source_bucket}, {document_id}, {self.presigned_url_expiration})")
        try:
            response = s3.generate_presigned_post(
                Bucket=self.source_bucket,
                Key=document_id,
                ExpiresIn=self.presigned_url_expiration                
            )
            return response
        except ClientError as e:
            logger.error(f"Error generating presigned post URL: {e}")
            raise

    # ====================================================================================================
    # This function saves the file to the S3 bucket along with whatever metadata is provided.
    # The job status is saved to an S3 tag.
    # The S3 bucket has an event listener lambda, which submits the document to Textract for OCR
    # NOTE: the Metadata is stored with the S3 object with the prefix "x-amz-meta-" added.
    # i.e. site_id becomes x-amz-meta-site_id in S3
    def save_document_to_source_bucket(self, user_id : str, site_id : str, document_id : str, file_name: str, content_type: str, ocr_status: str, body : str):
        logger.debug(f"saving document: {document_id} to bucket {self.source_bucket}, body starts with {body[:32]}")
        if not document_id:
            raise ValueError("document_id cannot be None or an empty string")

        # The status is stored as a tag so that it may be modified without copying the
        # entire S3 object
        if not ocr_status:
            ocr_status = "New"
        # Note that when first writing an object to S3 the tag_set must be a String
        # and must be encoded as URL Query parameters. (For example, “Key1=Value1”)
        # The TagSet is treated as a List of Dict for getObjectTagging and putObjectTagging.
        tag_set = f"{TAG_KEY_STATUS}={ocr_status}"

        # Immutable properties are stored as metadata in S3
        if not file_name:
            file_name = document_id
        if not site_id:
            site_id = "unknown"
        if not user_id:
            user_id = "unknown"
        if not content_type:
            content_type = self.get_mime_type(file_name)
        
        logger.debug(f"file_name={file_name}, content_type={content_type}, user_id={user_id}, site_id={site_id}, body starts with {body[:128]}")
        try:
            s3.put_object(
                Bucket= self.source_bucket,
                Key=document_id,
                Body=body,
                ContentType=content_type,
                Metadata= {
                    METADATA_KEY_FILE_NAME: file_name,
                    METADATA_KEY_USER_ID: user_id,
                    METADATA_KEY_SITE_ID: site_id
                },
                Tagging= tag_set
            )
        except Exception as e:
            logger.error(f"Error saving file: {e}")
            raise

    # ====================================================================================================
    # This function retrieves the original docuemnt given the document_id
    # ====================================================================================================
    def get_document_from_source_bucket(self, user_id: str, site_id: str, document_id: str) -> dict:
        logger.debug(f"get_document_from_source_bucket({user_id}, {site_id}, {document_id})")
        if not document_id:
            raise ValueError("document_id cannot be None or an empty string")

        try:
            result = s3.get_object(
                Bucket= self.source_bucket,
                Key=document_id
            )
        except Exception as e:
            logger.error(f"Error retreiving file: {e}")
            raise

        return result

    # ====================================================================================================
    # Submit a document to Textract for recognition and analysis.
    # This method is called by a Lambda which is triggered when a new document is added to the source S3 bucket
    # ====================================================================================================
    def submit_document_to_analysis(self, document_id: str):
        if not document_id:
            raise ValueError("document_id cannot be None or an empty string")

        try:
            logger.debug(f"starting text analysis of {self.source_bucket} : {document_id} as {self.textract_service_role}, with notification on {self.textract_status_topic}")
            # the response looks something like: {'JobId': 'string'}
            result = txt.start_document_analysis(
                DocumentLocation={
                    'S3Object': {
                        'Bucket': self.source_bucket,
                        'Name': document_id
                    }},
                FeatureTypes=['LAYOUT'],
                JobTag=document_id,
                NotificationChannel={'RoleArn': self.textract_service_role, 'SNSTopicArn': self.textract_status_topic})
            job_id = result['JobId']

            tags = [{"Key": TAG_KEY_STATUS, "Value": "Submitted"}, {"Key": TAG_JOB_ID, "Value": job_id}]
            self.update_tag_in_S3(document_id, tags)
            return
        except Exception as e:
            logger.error(f"Error submitting job: {e}")
            raise e

    # ====================================================================================================
    # Submit a document to Textract for recognition only.
    # ====================================================================================================
    def submit_document_to_ocr(self, document_id: str):
        if not document_id:
            raise ValueError("document_id cannot be None or an empty string")

        try:
            logger.debug(f"starting text detection of {self.source_bucket} : {document_id} as {self.textract_service_role}, with notification on {self.textract_status_topic}")
            # the response looks something like: {'JobId': 'string'}
            result = txt.start_document_text_detection(
                DocumentLocation={
                    'S3Object': {
                        'Bucket': self.source_bucket,
                        'Name': document_id
                    }},
                JobTag=document_id,
                NotificationChannel={'RoleArn': self.textract_service_role, 'SNSTopicArn': self.textract_status_topic})
            logger.debug(f"result={result}")

            job_id = result['JobId']

            tags = [{"Key": TAG_KEY_STATUS, "Value": "Submitted"}, {"Key": TAG_JOB_ID, "Value": job_id}]
            self.update_tag_in_S3(document_id, tags)
            return
        except Exception as e:
            logger.error(f"Error submitting job: {e}")
            raise e

    # ====================================================================================================
    # Copy a document from the Textract result to the destination bucket
    # ====================================================================================================
    def ocr_complete(self, document_id: str, status: str):
        if not document_id:
            raise ValueError("document_id cannot be None or an empty string")
        if not status:
            raise ValueError("status cannot be None or an empty string")
        try:
            match status:
                case "SUCCEEDED":
                    logger.info(f"{document_id} OCR status SUCCEEDED, moving results to output bucket")
                    self.move_text_to_destination(document_id)
                    self.move_json_to_destination(document_id)
                    code = 200
                    msg = {"Content-Type": "application/json"}
                case "FAILED":
                    logger.info(f"{document_id} OCR status FAILED, no results available")
                    code = 500
                    msg = {"Content-Type": "application/json"}
                case _:
                    logger.info(f"{document_id} OCR status unknown, no results available")
                    code = 400
                    msg = {"Content-Type": "application/json"}

            tags = [{"Key": TAG_KEY_STATUS, "Value": status}]
            self.update_tag_in_S3(document_id, tags)
            return code, msg
        except Exception as e:
            raise e
        
    # ====================================================================================================
    # Copy a document from the Textract result to the destination bucket
    # The document_id should be a UUID but it can be any string. When a file is copied
    # directly to the source bucket it may have any object ID.
    # ====================================================================================================
    def move_text_to_destination(self, document_id: str):
        if not document_id:
            raise ValueError("document_id cannot be None or an empty string")

        try:
            logger.debug(f"move_text_to_destination({document_id})")
            metadata = self.get_document_metadata(document_id)
            logger.debug(f"metadata={metadata}")

            job_id = metadata[TAG_JOB_ID]
            logger.info(f"document_id is {document_id}, job_id is {job_id}")

            responseJson = get_full_json(job_id=job_id,
                                boto3_textract_client=txt,
                                textract_api= Textract_API.ANALYZE)
            logger.debug(f"responseJson={responseJson}")
            report_text = get_text_from_layout_json(
                responseJson, 
                exclude_page_header = True, 
                exclude_page_footer = True, 
                exclude_figure_text = True, 
                exclude_page_number = True)
            
            text = report_text[1]

            user_id = metadata[METADATA_KEY_USER_ID] if METADATA_KEY_USER_ID in metadata else None
            site_id = metadata[METADATA_KEY_SITE_ID] if METADATA_KEY_SITE_ID in metadata else None
            file_name = metadata[METADATA_KEY_FILE_NAME] if METADATA_KEY_FILE_NAME in metadata else document_id

            text_document_id = f'{document_id}.txt'

            logger.debug(f"saving text for document {document_id}, text starts with {text[:128]}")
            self.save_document_to_destination_bucket(user_id, site_id, text_document_id, file_name, text)

            return

        except Exception as e:
            raise e

    def move_json_to_destination(self, document_id: str):
        if not document_id:
            raise ValueError("document_id cannot be None or an empty string")
        try:
            logger.debug(f"move_json_to_destination({document_id})")
            metadata = self.get_document_metadata(document_id)
            logger.debug(f"metadata={metadata}")

            job_id = metadata[TAG_JOB_ID]
            logger.info(f"{document_id}, job_id is {job_id}")

            responseJson = get_full_json(job_id=job_id,
                                boto3_textract_client=txt,
                                textract_api= Textract_API.ANALYZE)
            logger.debug(f"responseJson={responseJson}")

            user_id = metadata[METADATA_KEY_USER_ID] if METADATA_KEY_USER_ID in metadata else None
            site_id = metadata[METADATA_KEY_SITE_ID] if METADATA_KEY_SITE_ID in metadata else None
            file_name = metadata[METADATA_KEY_FILE_NAME] if METADATA_KEY_FILE_NAME in metadata else document_id

            json_document_id = f'{document_id}.json'

            # safely log the first 128 characters of the JSON
            self.log_response_json(f"saving json for document {document_id}, json starts with", responseJson, 128)
            
            self.save_document_to_destination_bucket(user_id, site_id, json_document_id, file_name, str(responseJson))

            return

        except Exception as e:
            raise e


    # ====================================================================================================
    # Retrieve the document status for the given document_id
    # ====================================================================================================
    def get_document_status(self, user_id: str, site_id: str, document_id: str) -> str:
        if not document_id:
            raise ValueError("document_id cannot be None or an empty string")
        try:
            item = self.get_document_metadata(user_id, site_id, document_id)
            if item is None:
                return "UNKNOWN"
            else:
                metadata = item.get("Metadata")
                if (metadata is None) or (len(metadata) == 0):
                    return "UNKNOWN"
                else:
                    job_status = metadata.get('job_status')
                    if job_status is None:
                        return "UNKNOWN"
                    else:
                        logger.debug(f"status is {job_status}")
                        return "UNKNOWN"

        except Exception as e:
            raise e

    # ====================================================================================================
    # This function retrieves the ocr'd text for the given document_id
    # Note that the destination bucket, which is where we will get the text, is always the default destination.
    # ====================================================================================================
    def get_text(self, user_id: str, site_id: str, document_id: str) -> dict:
        if not document_id:
            raise ValueError("document_id cannot be None or an empty string")
        try:
            logger.debug(f"get_text({user_id}, {site_id}, {document_id})")
            item = self.get_document_metadata(document_id)
            job_id = item.get(TAG_JOB_ID)
            responseJson = get_full_json(job_id=job_id,
                                boto3_textract_client=txt,
                                textract_api= Textract_API.ANALYZE)
            report_text = get_text_from_layout_json(responseJson, exclude_page_header = True, exclude_page_footer = True, exclude_figure_text = True, exclude_page_number = True)

            logger.debug(f"returning {report_text}")
            return report_text

        except Exception as e:
            raise e

    # The document returned from get_text_from_layout_json looks something like this:
    # {
    # 1: "Patient: DOE, JOHN\\nMRN JD4USARAD\\n\\nExam Date:\\n05/25/2010\\n\\nReferring Physician: DR. DAVID LIVESEY\\n\\nDOB:\\n01/01/1961\\n\\nFAX:\\n(305) 418-8166\\n\\nPET/CT OF THE WHOLE BODY\\n\\nCLINICAL HISTORY: Melanoma January. 2008. rectum; metastases to liver and tail bone. Lymph\\nnode metastases. Vascular therapy performed on March 9th: radiation therapy June, 2009.\\n\\nTECHNIQUE A PET/CT scan was obtained from the level of the vertex of the skull to the distal toes\\nfollowing the administration of 13.4 mCi of FDG intravenously\\n\\nCOMPARISON: April 7. 2009.\\n\\nREPORT HEAD AND NECK: There is no intracranial hemorrhage. midline shift or hydrocephalus.\\n\\nThe cerebellum and brainstem are normal. The basal cistems are patent.\\n\\nThe skull is intact. The visualized paranasal sinuses and temporal mastoid bone air cells are clear.\\nThere is mild to moderate bowing of the nasal septum to the left side. The salivary glands of the\\nneck are normal\\n\\nThe epiglottic, aryepiglottic folds, true and false vocal cords and supra and subglottic airway are\\nintact. The thyroid gland is normal.\\n\\nThere is no abnormal radiotracer uplake located within the head and neck\\n\\nCHEST: The heart measures at the upper limits of normal in size There is no evidence of a\\npericardial effusion.\\n\\nThe ascending thoracic aorta is minimally ectatic measuring up to 3.2 cm in diameter. The distal tip\\nof a Port-a-Catheter device placed via the left subclavian vein resides within the superior vena cava.\\n\\nThere are stable right paratracheal lymph nodes. These lymph nodes are not radiotracer avid.\\n\\nThere is no evidence of pleural effusion.\\n\\nThere has been a significant interval increase in the size of a now 3 X 2.6 cm\\n\\n\\n\\n", 
    # 2: "Patient: DOE, JOHN\\nMRN JD4USARAD\\n\\nExam Date:\\n05/25/2010\\nDOB:\\n01/01/1961\\nFAX:\\n(305) 418-8166\\n\\nReferring Physician: DR. DAVID LIVESEY\\n\\nperipherally located metastasis located within the apical posterior segment of the left upper lobe.\\nPreviously, this metastasis measured only 0.7 x 0.5 cm. There is significantly increased radiotracer\\nuptake within this mass, which measures up to 8.6 SUVs. Previously the mass measured up to 3.3\\nSUVs.\\n\\nThere has been an interval increase in the size of a now 1.3 x 0,9 cm subpleural non-calcified\\nmetastasis located within the apical segment of the right upper lobe, which previously measured 0.4\\ncm in diameter This metastasis measures up to 6 SUVs There is mild dependent atelectasis\\nlocated within both mid and lower lung zones\\n\\nABDOMEN AND PELVIS: There has been an interval increase in size of a now 4.6 X 2.8 cm\\nmetastasis located within the low anterior and posterior segments of the right lobe of the liver.\\nPreviously, this metastasis measured approximately 1.9 X 1.5 cm. This metastasis measures up to\\n10.7 SUVs. There has been interval increase in the size of a now 3 x 1,9 cm metastasis located\\nwithin the posterior segment of the right lobe of the liver at the junction of segments 6 and 7.\\nPreviously this metastasis measured approximately 1.4 x 0.9 cm. This metastasis is radiotracer avid\\nand measures up to 8.1 SUVs. There has been no significant interval change in the size of a 0.6 cm\\nmetastasis located within the ventral high lateral segments of the left lobe of the liver. which\\nmeasures approximately 4.5 SUVs.\\n\\nThere is no intra or extrahepatic bile duct dilation.\\n\\nThe spleen. pancreas and adrenal glands are normal The gallbladder is normal.\\n\\nThere is no hydroureteronephrosis or nephrolithiasis. The abdominal aorta is normal in caliber.\\n\\nThere is no lymphadenopathy identified within the abdomen.\\n\\nThere is a short Hartmans pouch extending from the proximal to mid sigmoid colon to the anus.\\nThere is stable moderate thickening of the wall of the distal sigmoid colon and rectum. possibly due\\nto radiation induced changes.\\n\\nThe uterus appears to be smaller than on the prior study, a finding of uncertain etiology. There\\nappear to be tubal ligation rings in place.\\n\\nThere is an end colostomy stoma overlying the left mid to anterior abdominal wall.\\n\\n\\n\\n", 
    # 3: "Patient: DOE, JOHN\\nMRN JD4USARAD\\nReferring Physician: DR. DAVID LIVESEY\\n\\nExam Date:\\n05/25/2010\\nDOB:\\n01/01/1961\\nFAX:\\n(305) 418-8166\\n\\nThere is a moderate quantity of stool located within the colon consistent with constipation. The\\nappendix is not seen.\\n\\nThere is a stable centrally hypodense mass measuring approximately 1.6 X 1.2 cm located within the\\npresacral space which exhibits increased SUV measurement of up to 4.5.\\n\\nThere has been no interval change in the size or appearance of a 1.1 cm slightly hypodense mass\\nlocated to the right side of the distal rectum. This mass is not radiotracer avid.\\n\\nThere is no extraluminal air or fluid identified within the abdomen or pelvis. This is no\\nlymphadenopathy located within the abdomen or pelvis.\\n\\nThere is no abnormal radiotracer uptake located within either lower extremity\\n\\nSKELETON I do not see evidence of metastatic disease to bone.\\n\\nCONCLUSION There has been progressive metastatic disease within the chest and liver as\\ndescribed in the body of the report. Two lung metastases have increased in size when compared to\\nthe prior examination. The degree of metabolic activity within these metastases has also increased\\nwhen compared to the prior study. There has been an interval increase in the size of several liver\\nmetastases. There is a new metastasis located within the dorsal lobe of the posterior segment of the\\nright lobe of the liver\\n\\nElectronically Signed by\\n\\n08/21/2009 8:20:56 AM\\n\\n\\n\\n"
    # }

    def get_presigned_get_url(self, document_id: str, content_type: str) -> str:
        if not document_id:
            raise ValueError("document_id cannot be None or an empty string")
        if "text/plain" == content_type:
            document_text_key = self.create_text_result_id(document_id)
        else:
            document_text_key = self.create_json_result_id(document_id)

        logger.debug(f"get_presigned_get_url({self.destination_bucket}, {document_text_key}, {self.presigned_url_expiration})")

        # :param s3_client: A Boto3 Amazon S3 client.
        # :param client_method: The name of the client method that the URL performs.
        # :param method_parameters: The parameters of the specified client method.
        # :param expires_in: The number of seconds the presigned URL is valid for.
        # :return: The presigned URL.
        try:
            presigned_url_response = s3.generate_presigned_url(
                ClientMethod="get_object", 
                Params={
                    'Bucket': self.destination_bucket,
                    'Key': document_text_key
                }, 
                ExpiresIn=self.presigned_url_expiration
            )
            logger.info("Got presigned URL: %s", presigned_url_response)
            return presigned_url_response
        except ClientError:
            logger.exception(f"get_presigned_get_url({self.destination_bucket}, {document_text_key}, {self.presigned_url_expiration})")
            raise

    # ====================================================================================================
    # Internal 'helper' functions
    # ====================================================================================================

    # This function retrieves document information from the S3 metadata and tags using the document_id
    # with error handling and logging to help with debugging and troubleshooting.
    # see https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/head_object.html
    # for the returned format
    # The parts of the return format from metadata that we care about is something like:
    # {
    #   'ArchiveStatus': 'ARCHIVE_ACCESS'|'DEEP_ARCHIVE_ACCESS',
    #   'LastModified': datetime(2015, 1, 1),
    #   'ContentLength': 123,
    #   'Metadata': {
    #       'string': 'string'
    #   }
    # }
    # Note: the document status is stored as a Tag so that it can be mutated
    # Note: the result MUST not have any values of None, which confuses ALB
    def get_document_metadata(self, document_id : str) -> dict:
        if not document_id:
            raise ValueError("document_id cannot be None or an empty string")
        try:
            metadata_response = s3.head_object(
                Bucket= self.source_bucket,
                Key=document_id,
            )
        except ClientError as cx:
            logger.info(f"cx.response['Error'] is [{cx.response['Error']}]")
            # e.g. "message":"cx.response['Error'] is [{'Code': '404', 'Message': 'Not Found'}]",

            if cx.response['Error']['Code'] == '404':
                logger.info(f"No metadata available for {document_id}")
                return None
            else:
                logger.warning(f"ClientError getting metadata {cx}")
                raise

        logger.debug(f"get_document_metadata metadata={metadata_response}")
        metadata = metadata_response['Metadata']
        response_metadata = metadata_response['ResponseMetadata']
        response_metadata_headers = response_metadata['HTTPHeaders']

        tags_response = s3.get_object_tagging(
            Bucket= self.source_bucket,
            Key=document_id,
        )
        logger.debug(f"get_document_metadata tags_response={tags_response}")

        result = {}

        if "Date" in metadata:
            result["Date"] = metadata["Date"]
        if "Last-Modified" in metadata:
            result["Last-Modified"] = metadata["Last-Modified"]
        if "Content-Length" in metadata:
            result["Content-Length"] = metadata["Content-Length"]
        if "Content-Type" in metadata:
            result["Content-Type"] = metadata["Content-Type"] 

        # Documents that are written directly to the source S3 bucket may not have
        # any of the metadata specified,
        if METADATA_KEY_FILE_NAME in metadata:
            result[METADATA_KEY_FILE_NAME] = metadata[METADATA_KEY_FILE_NAME]
            
        if METADATA_KEY_SITE_ID in metadata:
            result[METADATA_KEY_SITE_ID] = metadata[METADATA_KEY_SITE_ID]

        if METADATA_KEY_USER_ID in metadata:
            result[METADATA_KEY_USER_ID] = metadata[METADATA_KEY_USER_ID]

        # add the tags that exist
        logger.debug(f"get_document_metadata tags={tags_response}")
        tag_set = tags_response['TagSet']
        logger.debug(f"get_document_metadata tag_set={tag_set}")

        status_element = next((item for item in tag_set if item['Key'] == TAG_KEY_STATUS), None)
        status = status_element['Value'] if status_element else None
        if status:
            result[TAG_KEY_STATUS] = status

        job_id_element = next((item for item in tag_set if item['Key'] == TAG_JOB_ID), None)
        job_id = job_id_element['Value'] if job_id_element else None
        if job_id:
            result[TAG_JOB_ID] = job_id

        logger.debug(f"get_document_metadata result={result}")
        return result

    # This method gets the metadata (and tags if available) from the OCR'd JSON
    # The text is always assumed to be in the destination bucket and the object key is the
    # document_id suffixed with ".json"
    def get_json_metadata(self, document_id: str) -> dict:
        if not document_id:
            raise ValueError("document_id cannot be None or an empty string")
        json_id = self.create_json_result_id(document_id)
        return self.get_result_metadata(document_id, json_id)

    # This method gets the metadata (and tags if available) from the OCR'd text
    # The text is always assumed to be in the destination bucket and the object key is the
    # document_id suffixed with ".txt"
    def get_text_metadata(self, document_id: str) -> dict:
        if not document_id:
            raise ValueError("document_id cannot be None or an empty string")
        text_id = self.create_text_result_id(document_id)
        return self.get_result_metadata(document_id, text_id)

    # This method gets the metadata (and tags if available) from the OCR'd text or JSON
    def get_result_metadata(self, document_id: str, result_id: str) -> dict:
        if not document_id:
            raise ValueError("document_id cannot be None or an empty string")
        try:
            metadata_response = s3.head_object(
                Bucket= self.destination_bucket,
                Key=result_id,
            )
        except ClientError as cx:
            if cx.response['Error']['Code'] == '404':
                logger.info(f"No result metadata available for {result_id}")
                return None
            else:
                logger.warning(f"ClientError getting metadata for {cx}")
                raise
        logger.debug(f"get_result_metadata metadata={metadata_response}")
        metadata = metadata_response['Metadata']
        response_metadata = metadata_response['ResponseMetadata']
        response_metadata_headers = response_metadata['HTTPHeaders']

        try:
            # get the tags from the source document metadata
            tags_response = s3.get_object_tagging(
                Bucket= self.source_bucket,
                Key=document_id,
            )
        except ClientError as cx:
            if cx.response['Error']['Code'] == '404':
                logger.info(f"No source metadata available for {document_id}")
                return None
            else:
                logger.warning(f"ClientError getting metadata for source {cx}")
                raise
        logger.debug(f"get_result_metadata tags_response={tags_response}")

        result = {}
        if "Date" in response_metadata_headers:
            result["Date"] = response_metadata_headers["Date"]
        if "Last-Modified" in response_metadata_headers:
            result["Last-Modified"] = response_metadata_headers["Last-Modified"]
        if "Content-Length" in response_metadata_headers:
            result["Content-Length"] = response_metadata_headers["Content-Length"]
        if "Content-Type" in response_metadata_headers:
            result["Content-Type"] = response_metadata_headers["Content-Type"] 

        # Documents may not have the file_name, site_id or user_id specified when the original document
        # was dropped directly into the source bucket
        if METADATA_KEY_FILE_NAME in metadata:
            result[METADATA_KEY_FILE_NAME] = metadata[METADATA_KEY_FILE_NAME]
            
        if METADATA_KEY_SITE_ID in metadata:
            result[METADATA_KEY_SITE_ID] = metadata[METADATA_KEY_SITE_ID]

        if METADATA_KEY_USER_ID in metadata:
            result[METADATA_KEY_USER_ID] = metadata[METADATA_KEY_USER_ID]

        # add the tags that exist
        logger.debug(f"get_result_metadata tags={tags_response}")
        tag_set = tags_response['TagSet']
        logger.debug(f"get_result_metadata tag_set={tag_set}")

        status_element = next((item for item in tag_set if item['Key'] == TAG_KEY_STATUS), None)
        status = status_element['Value'] if status_element else None
        if status:
            result[TAG_KEY_STATUS] = status

        job_id_element = next((item for item in tag_set if item['Key'] == TAG_JOB_ID), None)
        job_id = job_id_element['Value'] if job_id_element else None
        if job_id:
            result[TAG_JOB_ID] = job_id

        logger.debug(f"get_result_metadata result={result}")
        return result

    # ==================================================================================================================
    # Helper functions, which do not represent application capabilities
    # ==================================================================================================================

    # gets the HTTP headers from an Event and returns a Map from header key to value, where the header keys are converted to uppercase
    def get_headers(self, event) -> map:
        headers = event.get("headers")
        logger.debug(f"headers={headers}")
        newHeaders = {k.upper():v for k,v in headers.items()}
        logger.debug(f"newHeaders={newHeaders}")
        return newHeaders;

    # Get the value of a secret from AWS Secrets Manager
    def get_secret(self, secret_name : str, region_name : str):
        # get username/password from AWS key store, return a dict object

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

    # This function saves text to the destination S3 bucket, with error handling 
    # and logging to help with debugging and troubleshooting.
    # NOTE: the Metadata is stored with the S3 object with the prefix "x-amz-meta-" added.
    # i.e. site_id becomes x-amz-meta-site_id in S3
    def save_document_to_destination_bucket(self, user_id : str, site_id : str, document_id : str, file_name: str, body : str):
        logger.debug(f"moving : {document_id} to bucket {self.destination_bucket}")

        # Immutable properties are stored as metadata in S3
        if file_name is None:
            file_name = document_id
        if site_id is None:
            site_id = "unknown"
        if user_id is None:
            user_id = "unknown"

        try:
            s3.put_object(
            Bucket= self.destination_bucket,
            Key=document_id,
            Body=body,
            Metadata= {
                'file_name': file_name,
                'user_id': user_id,
                'site_id': site_id,
                'mime-type': self.get_mime_type(file_name)
            }
        )
        except Exception as e:
            logger.error(f"Error saving {document_id} to destination {self.destination_bucket}: {e}")
            raise e

    # ====================================================================================================
    # Managing Tag Sets in S3
    # ====================================================================================================
    # Get the current object tagging, update or add the given tag and then update the tag group in S3
    # Note that when first writing an object to S3 the tag_set must be a String
    # and must be encoded as URL Query parameters. (For example, “Key1=Value1”)
    # The TagSet is treated as a List of Dict for getObjectTagging and putObjectTagging.
    # For example: 
    # Tagging={
    #     'TagSet': [
    #         {
    #             'Key': 'string',
    #             'Value': 'string'
    #         },
    #     ]
    # }
    def update_tag_in_S3(self, document_id : str, new_tag_values: list):
        logger.debug(f"updating document tag: {document_id}, new_tag_values {new_tag_values}")
        if new_tag_values:
            try:
                get_tagging_response = s3.get_object_tagging(
                    Bucket= self.source_bucket,
                    Key=document_id,
                )
                tag_set = get_tagging_response['TagSet']
                # tag_set is a list of dictionaries, each dictionary contains a 'Key' and 'Value'
                logger.debug(f"tag_set={tag_set} is a {type(tag_set)}")
            except Exception as e:
                logger.error(f"Error retrieving document tags: {e}")
                raise

            try:
                updated_tag_set = self.update_tag_set(tag_set, new_tag_values)
                logger.debug(f"updated_tag_set={updated_tag_set} is a {type(updated_tag_set)}")

                s3.put_object_tagging(
                    Bucket=self.source_bucket,
                    Key=document_id,
                    Tagging={
                        'TagSet': updated_tag_set
                    }
                )
            except Exception as e:
                logger.error(f"Error updating document tags: {e}")

    def update_tag_set(self, tag_set: list, new_tag_values: list) -> list :
        logger.debug(f"update_tag_set({tag_set}, {new_tag_values})")

        for tag in new_tag_values:
            key = tag['Key']
            value = tag['Value']

            logger.debug(f"key={key}, value={value}")
            tag_set = self.update_tag(tag_set, key, value)

        logger.debug(f"update_tag_set, updated_tag_set={tag_set}")
        return tag_set

    # Update or add one tag into a TagSet
    def update_tag(self, tag_set: list, tag_key_to_modify, new_tag_value):
        logger.debug(f"update_tag({tag_set}, {tag_key_to_modify}, {new_tag_value})")

        modified_tag_set = []
        tag_modified = False
        for tag in tag_set:
            if tag['Key'] == tag_key_to_modify:
                tag['Value'] = new_tag_value
                tag_modified = True
            modified_tag_set.append(tag)
        
        # If the tag was not found, add a new tag
        if not tag_modified:
            modified_tag_set.append({'Key': tag_key_to_modify, 'Value': new_tag_value})

        logger.debug(f"update_tag, modified_tag_set={modified_tag_set}")

        return modified_tag_set

    # ====================================================================================================
    # Miscellaneous Helpful Stuff
    # ====================================================================================================
    def remove_leading_slash(self, input_string) -> str:
        if input_string and input_string[0] == '/':
            return input_string[1:]
        else:
            return input_string

    # given a slash delimited list, return the last element
    def return_last_path_element(self, path : str) -> str:
        # the path is expected to be something like: /text/<job_id>, where text is a constant
        path_elements = path.split('/')
        last_element = None
        if len(path_elements) > 0:
            last_element = path_elements[len(path_elements) - 1]
        return last_element

    # Returns the MIME type based on the file extension.
    # Args: filename (str): The name of the file, including the extension.
    # Returns: str: The MIME type corresponding to the file extension.
    def get_mime_type(self, filename) -> str:
        if filename:
            mime_type, _ = mimetypes.guess_type(filename)

        if not mime_type:
            return "application/octet-stream"
        else:
            return mime_type
    
    def create_text_result_id(self, document_id : str) -> str:
        if document_id:
            return f"{document_id}.txt"
        else:
            raise ValueError("document_id cannot be None")

    def create_json_result_id(self, document_id : str) -> str:
        if document_id:
            return f"{document_id}.json"
        else:
            raise ValueError("document_id cannot be None")

    def get_document_id_from_result_id(self, result_id : str) -> str:
        if result_id:
            return result_id.rsplit('.', 1)[0]

        else:
            raise ValueError("result_id cannot be None")
        
    def log_response_json(self, prefix: str, response_json, max_length: int):
        try:
            json_text = str(response_json)
            if len(json_text) > max_length:
                logger.debug(f"{prefix}: {json_text[:max_length]}...")
            else:
                logger.debug(f"{prefix}: {json_text}")
        except Exception as e:
            logger.error(f"Error logging responseJson: {e}")

# Notes
    # except ClientError as cx:
    #     logger.info(f"Client Error is [{cx}]")
    #     # e.g. "message":"Client Error is [An error occurred (404) when calling the HeadObject operation: Not Found]",

    #     logger.info(f"cx.response['Error'] is [{cx.response['Error']}]")
    #     # e.g. "message":"cx.response['Error'] is [{'Code': '404', 'Message': 'Not Found'}]",

    #     logger.info(f"cx.response['Error']['Code'] is [{cx.response['Error']['Code']}]")
    #     # e.g. "message":"cx.response['Error']['Code'] is [404]",
