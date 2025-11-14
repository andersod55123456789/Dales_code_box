#!/usr/bin/env python3
import time
import glob
import subprocess

import cv2
import numpy as np
import gpiod
from gpiod.line import Direction, Value

# --- Debug / safety ---
DEBUG    = True
DRY_RUN  = True          # keep relay OFF while tuning
PRINT_HZ = 5

# ==============================
# CAMERA AUTO-DETECT (PREFERS USB)
# ==============================

def select_camera():
    """
    Scan /dev/video* devices, test each with OpenCV,
    classify as USB vs internal via udev info,
    and prefer external USB webcams.
    """
    cams = sorted(glob.glob("/dev/video*"))
    if not cams:
        raise RuntimeError("No video devices found in /dev/video*")

    usable_cams = []

    for dev in cams:
        # Extract numeric index, e.g. /dev/video2 -> 2
        try:
            idx = int(dev.replace("/dev/video", ""))
        except ValueError:
            continue

        # Try opening with OpenCV to verify it works
        test = cv2.VideoCapture(idx)
        if not test.isOpened():
            test.release()
            continue

        ret, _ = test.read()
        test.release()
        if not ret:
            continue

        # Determine if webcam is USB or internal via udev info
        try:
            result = subprocess.run(
                ["udevadm", "info", "--query=all", "--name", dev],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            info = result.stdout.lower()
            # Very simple heuristic: if udev info mentions "usb", assume external
            is_usb = "usb" in info
        except Exception:
            is_usb = False

        usable_cams.append((idx, is_usb))

    if not usable_cams:
        raise RuntimeError("No usable cameras detected (OpenCV could not read any).")

    # Prefer external USB cameras
    for idx, usb in usable_cams:
        if usb:
            print(f"[INFO] Using external USB camera: /dev/video{idx}")
            return idx

    # Otherwise, fall back to first internal camera
    idx, _ = usable_cams[0]
    print(f"[INFO] Using internal camera: /dev/video{idx}")
    return idx


# Pick camera index once at startup
CAM_INDEX = select_camera()

# ==============================
# OPEN CAMERA VIA GSTREAMER / V4L2
# ==============================

GST_PIPELINE = (
    f"v4l2src device=/dev/video{CAM_INDEX} ! "
    "video/x-raw,format=YUY2,width=640,height=480,framerate=30/1 ! "
    "videoconvert ! video/x-raw,format=BGR ! "
    "appsink drop=true max-buffers=1"
)

cap = cv2.VideoCapture(GST_PIPELINE, cv2.CAP_GSTREAMER)
if not cap.isOpened():
    raise RuntimeError(f"Cannot open camera pipeline for /dev/video{CAM_INDEX}")

cv2.namedWindow("Hand Switch", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Hand Switch", 960, 720)
if DEBUG:
    cv2.namedWindow("Skin (combined)", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Skin (combined)", 640, 480)
    cv2.namedWindow("Motion Mask", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Motion Mask", 640, 480)
    cv2.namedWindow("Overlap (skin∩motion)", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Overlap (skin∩motion)", 640, 480)

# ==============================
# RELAY (ACTIVE-LOW) ON GPIO 17
# ==============================

PIN = 17
RELAY_ON  = Value.INACTIVE   # LOW energizes module (active-low)
RELAY_OFF = Value.ACTIVE     # HIGH de-energizes

chip = gpiod.Chip("/dev/gpiochip0")
req  = chip.request_lines(
    consumer="hand-relay",
    config={PIN: gpiod.LineSettings(direction=Direction.OUTPUT,
                                    output_value=RELAY_OFF)}
)

# ==============================
# BACKGROUND MODEL (MOTION GATE)
# ==============================

bg_gray = None
BG_ALPHA = 0.01           # slow adapt to ignore flicker
MOTION_THRESH = 20        # tuned motion threshold
MORPH_K = np.ones((3,3), np.uint8)
frames = 0
WARMUP_FRAMES = 120       # ~4s warmup

# Size / coverage thresholds
MIN_AREA_PX = 1200        # minimum contour area for a valid hand blob
MIN_OVERLAP_COV = 0.20    # min % of frame that must overlap to count (0.2%)

# ==============================
# HAND DETECTION
# ==============================

def detect_hand(frame_bgr):
    global bg_gray

    # ---- Dual color gate: YCrCb ∩ HSV ----
    ycrcb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2YCrCb)
    lower_ycc = np.array([0, 133, 77],   dtype=np.uint8)
    upper_ycc = np.array([255, 173, 127],dtype=np.uint8)
    skin_ycc = cv2.inRange(ycrcb, lower_ycc, upper_ycc)

    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    lower_hsv = np.array([0, 25, 50], dtype=np.uint8)
    upper_hsv = np.array([25,255,255], dtype=np.uint8)
    skin_hsv = cv2.inRange(hsv, lower_hsv, upper_hsv)

    skin = cv2.bitwise_and(skin_ycc, skin_hsv)
    skin = cv2.medianBlur(skin, 5)
    skin = cv2.morphologyEx(skin, cv2.MORPH_OPEN, MORPH_K, iterations=1)
    skin = cv2.dilate(skin, MORPH_K, iterations=2)   # merge fragments

    # ---- Motion mask ----
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    gray_blur = cv2.GaussianBlur(gray, (5,5), 0)

    if bg_gray is None:
        bg_gray = gray_blur.astype(np.float32)
    else:
        cv2.accumulateWeighted(gray_blur, bg_gray, BG_ALPHA)

    bg_u8 = cv2.convertScaleAbs(bg_gray)
    diff  = cv2.absdiff(gray_blur, bg_u8)
    _, motion = cv2.threshold(diff, MOTION_THRESH, 255, cv2.THRESH_BINARY)
    motion = cv2.morphologyEx(motion, cv2.MORPH_OPEN, MORPH_K, iterations=1)
    motion = cv2.dilate(motion, MORPH_K, iterations=2)

    # ---- Overlap: (skin ∩ motion) ----
    overlap = cv2.bitwise_and(skin, motion)

    # Metrics
    skin_cov = (skin > 0).mean()   * 100.0
    mot_cov  = (motion > 0).mean() * 100.0
    ovl_cov  = (overlap > 0).mean()* 100.0

    # Largest moving-skin contour with geometry checks
    cnts, _ = cv2.findContours(overlap, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    hand_found = False
    best = None
    for c in cnts:
        area = cv2.contourArea(c)
        if area < MIN_AREA_PX:
            continue
        x,y,w,h = cv2.boundingRect(c)
        aspect = w / float(h + 1e-6)
        hull = cv2.convexHull(c)
        solidity = area / (cv2.contourArea(hull) + 1e-6)
        if 0.4 < aspect < 2.5 and solidity > 0.80:
            hand_found = True
            if best is None or area > cv2.contourArea(best):
                best = c

    # Coverage floor (ignore tiny scattered noise)
    if ovl_cov < MIN_OVERLAP_COV:
        hand_found = False
        best = None

    if DEBUG:
        cv2.imshow("Skin (combined)", skin)
        cv2.imshow("Motion Mask", motion)
        cv2.imshow("Overlap (skin∩motion)", overlap)

    return hand_found, best, skin_cov, mot_cov, ovl_cov

# ==============================
# RELAY PULSE (RESPECTS DRY_RUN)
# ==============================

PULSE_SEC = 0.5
COOLDOWN  = 1.5
last_fire = 0.0

def pulse_relay():
    global last_fire
    if DRY_RUN:
        return
    now = time.time()
    if now - last_fire < COOLDOWN:
        return
    req.set_value(PIN, RELAY_ON)
    time.sleep(PULSE_SEC)
    req.set_value(PIN, RELAY_OFF)
    last_fire = time.time()

# ==============================
# MAIN LOOP
# ==============================

last_print = 0.0

try:
    while True:
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.01)
            continue
        frames += 1

        hand, contour, skin_cov, mot_cov, ovl_cov = detect_hand(frame)

        # Warmup gate
        if frames < WARMUP_FRAMES:
            hand = False

        # HUD
        cv2.putText(frame, f"Skin %: {skin_cov:.1f}", (12, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2, cv2.LINE_AA)
        cv2.putText(frame, f"Motion %: {mot_cov:.1f}", (12, 48),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2, cv2.LINE_AA)
        cv2.putText(frame, f"Overlap %: {ovl_cov:.2f}", (12, 72),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2, cv2.LINE_AA)
        status = "HAND: YES" if hand else "HAND: NO"
        cv2.putText(frame, status, (12, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                    (0,255,0) if hand else (255,255,255), 2, cv2.LINE_AA)

        if contour is not None:
            x,y,w,h = cv2.boundingRect(contour)
            cv2.rectangle(frame, (x,y), (x+w, y+h), (0,255,0), 2)
            cv2.putText(frame, "HAND", (x, max(0,y-8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2, cv2.LINE_AA)

        cv2.imshow("Hand Switch", frame)

        # Console prints
        now = time.time()
        if now - last_print >= 1.0 / PRINT_HZ:
            print(f"Skin%={skin_cov:5.1f}  Mot%={mot_cov:5.1f}  Ovl%={ovl_cov:5.2f}  Hand={hand}  Warmup={frames < WARMUP_FRAMES}")
            last_print = now

        if hand:
            pulse_relay()

        if (cv2.waitKey(1) & 0xFF) == ord('q'):
            break

finally:
    try:
        req.set_value(PIN, RELAY_OFF)
    except Exception:
        pass
    cap.release()
    cv2.destroyAllWindows()
