import cv2
import numpy as np
from datetime import datetime

def calc_center(indexes, points, img, draw=False):
    (cx, cy), radius = cv2.minEnclosingCircle(points[indexes])
    center = np.array([cx, cy], dtype=np.int32)
    if draw:
        cv2.circle(img, center, int(radius), (0, 0, 255), 1, cv2.LINE_AA)
    return center

def eye_direction(iris_center, eye_center):
    if abs(iris_center[0] - eye_center[0]) < 5:
        return "CENTER"
    elif iris_center[0] - eye_center[0] < 0:
        return "LEFT"
    elif iris_center[0]-eye_center[0] > 0:
        return "RIGHT"

def warn(img=None):
    if img is not None:
        h, w, c = img.shape
        cv2.rectangle(img, (0,0), (w, h), (0, 0, 255), -1)
        cv2.putText(img, "!انتبه ركز في الشاشة", (w//4, h//2), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3)

def format_duration(seconds):
    seconds = int(seconds)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    
    if hours > 0:
        return f"{hours} ساعة {minutes} دقيقة {seconds} ثانية"
    elif minutes > 0:
        return f"{minutes} دقيقة {seconds} ثانية"
    else:
        return f"{seconds} ثانية"

def get_percentage_class(percentage):
    if percentage >= 70:
        return "high"
    elif percentage >= 40:
        return "medium"
    else:
        return "low"