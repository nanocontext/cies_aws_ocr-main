import json
import os
import mimetypes
from src.cies_ocr_core import *

cies_ocr_core = CiesOcrCore(
    os.getenv('SOURCE_BUCKET'), 
    os.getenv('DESTINATION_BUCKET'), 
    os.getenv('TEXTRACT_SERVICE_ROLE'), 
    os.getenv('TEXTRACT_STATUS_TOPIC'), 
    os.getenv("AWS_REGION"))

def test_answer():
    updated_tags = cies_ocr_core.update_tag_set({"a": 1}, {"b": 2})
    assert "a" in updated_tags
    assert "b" in updated_tags