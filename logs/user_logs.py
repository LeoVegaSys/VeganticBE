import os
import json
from typing import Union

from config import FEEDBACK_LOG_FILE, LOG_FILE

class FileLogger:
    def __init__(self):
        self.log_file = LOG_FILE
        self.feedback_log_file = FEEDBACK_LOG_FILE

    def write_to_log(self, content: Union[str, dict], feedback: bool = False):
        write_to_file = self.feedback_log_file if feedback else self.log_file
        try:
            with open(write_to_file, "a") as f:
                f.write(json.dumps(content, default=str) + "\n")
        except Exception:
            print(f"Failed while opening {write_to_file}")
            pass