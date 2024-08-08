import json
import os
import mimetypes
from src.cies_ocr_core import *
from aws_lambda_powertools import Logger, Metrics, Tracer


def test_answer():
    updated_tags = cies_ocr_core.update_tag_set({"a": 1}, {"b": 2})
    assert "a" in updated_tags
    assert "b" in updated_tags