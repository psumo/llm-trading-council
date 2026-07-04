"""
JSON序列化辅助工具 - 处理datetime, numpy等非标准类型
"""
import json
import numpy as np
import pandas as pd
from datetime import datetime


class CustomJSONEncoder(json.JSONEncoder):
    """Custom JSON Encoder to handle datetime and numpy types"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(obj, (np.integer, np.int32, np.int64)):
            return int(obj)
        if isinstance(obj, (np.floating, np.float32, np.float64)):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, pd.Timestamp):
            return obj.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(obj, pd.Timedelta):
            return str(obj)
        return super().default(obj)


def safe_json_dump(data, fp, **kwargs):
    """Wrapper for json.dump that uses CustomJSONEncoder by default"""
    kwargs.setdefault('cls', CustomJSONEncoder)
    json.dump(data, fp, **kwargs)


def safe_json_dumps(data, **kwargs):
    """Wrapper for json.dumps that uses CustomJSONEncoder by default"""
    kwargs.setdefault('cls', CustomJSONEncoder)
    return json.dumps(data, **kwargs)
