import base64
import json
import logging
import random
import struct

from cv2.typing import MatLike
import numpy as np
import onnxruntime as ort
import cv2

import os
import requests
import threading

logger = logging.getLogger(__name__)

MODEL_DIR = os.getenv("MODEL_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "models_onnx"))

def get_model_path(filename: str) -> str:
    return os.path.join(MODEL_DIR, filename)

def ensure_model_exists(filename: str, url: str):
    path = get_model_path(filename)
    if os.path.exists(path):
        return

    logger.info(f"模型文件 {filename} 不存在，正在下载...")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        resp = requests.get(url, stream=True)
        resp.raise_for_status()
        with open(path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        logger.info(f"模型文件 {filename} 下载完成")
    except Exception as e:
        logger.error(f"下载模型 {filename} 失败: {e}")
        if os.path.exists(path) and os.path.getsize(path) == 0:
            os.remove(path)
        raise

MODEL_URLS = {
    "ocr.onnx": "https://github.com/maserpoassr/automoguding-saas/releases/download/v0.0.1/ocr.onnx",
    "yolov5n.onnx": "https://github.com/maserpoassr/automoguding-saas/releases/download/v0.0.1/yolov5n.onnx"
}

_ORT_SESSION_CACHE = {}
_ORT_SESSION_LOCK = threading.Lock()

def _get_ort_session(model_path: str, use_gpu: bool = False):
    providers = ("CUDAExecutionProvider",) if use_gpu else ("CPUExecutionProvider",)
    key = (model_path, providers)
    s = _ORT_SESSION_CACHE.get(key)
    if s is not None:
        return s
    with _ORT_SESSION_LOCK:
        s2 = _ORT_SESSION_CACHE.get(key)
        if s2 is not None:
            return s2
        session = ort.InferenceSession(model_path, providers=list(providers))
        _ORT_SESSION_CACHE[key] = session
        return session



def calculate_precise_slider_distance(target_start_x: int, target_end_x: int,
                                      slider_width: int) -> float:
    """
    计算滑块需要移动的精确距离，并添加微小随机偏移。

    Args:
        target_start_x (int): 目标区域的起始x坐标。
        target_end_x (int): 目标区域的结束x坐标。
        slider_width (int): 滑块的宽度。

    Returns:
        float: 精确到小数点后1位的滑动距离，包含微小随机偏移。
    """
    try:
        # 计算目标区域的中心点x坐标
        target_center_x = (target_start_x + target_end_x) / 2

        # 计算滑块初始位置的中心点x坐标
        slider_initial_center_x = slider_width / 2

        # 计算滑块需要移动的精确距离
        precise_distance = target_center_x - slider_initial_center_x

        # 添加一个随机的微小偏移，模拟真实用户滑动
        random_offset = random.uniform(-0.1, 0.1)

        # 将最终距离四舍五入到小数点后1位
        final_distance = round(precise_distance + random_offset, 1)

        logger.info(f"计算滑块距离成功: {final_distance}")
        return final_distance

    except Exception as e:
        logger.error(f"计算滑块距离时发生错误: {e}")
        raise


def extract_png_width(png_binary: bytes) -> int:
    """
    从PNG二进制数据中提取图像宽度。

    Args:
        png_binary (bytes): PNG图像的二进制数据。

    Returns:
        int: PNG图像的宽度（以像素为单位）。

    Raises:
        ValueError: 如果输入数据不是有效的PNG图像。
    """
    try:
        # 检查PNG文件头是否合法（固定8字节的PNG签名）
        if png_binary[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError("无效的PNG签名：不是有效的PNG图像")

        # PNG宽度信息位于IHDR块中，从第16字节开始，长度为4字节
        width_bytes = png_binary[16:20]
        width = struct.unpack(">I", width_bytes)[0]  # 使用大端字节序解包
        logger.info(f"PNG宽度提取成功: {width}")
        return width

    except Exception as e:
        logger.error(f"提取PNG宽度时发生错误: {e}")
        raise ValueError(f"提取PNG宽度失败: {e}")

# (文件后续内容保持仓库原样，这里仅同步本次优化相关改动：模型下载与 InferenceSession 缓存，以及 detect_objects/predict_ocr 使用 _get_ort_session)
