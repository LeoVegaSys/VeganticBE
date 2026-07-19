import os
import json
from typing import Union
from dotenv import load_dotenv

load_dotenv()

class FileLogger:
    def __init__(self):
        self.log_file = os.environ.get("QA_LOG_FILE", "qa_log.jsonl")
        self.feedback_log_file = os.environ.get("QA_FEEDBACK_LOG_FILE", "qa_feedback.jsonl")

    def write_to_log(self, content: Union[str, dict], feedback: bool = False):
        write_to_file = self.feedback_log_file if feedback else self.log_file
        try:
            with open(write_to_file, "a") as f:
                f.write(json.dumps(content, default=str) + "\n")
        except Exception:
            print(f"Failed while opening {write_to_file}")
            pass