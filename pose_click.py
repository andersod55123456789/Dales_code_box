from ultralytics import YOLO
import cv2
import pyautogui
import time


# Indices for COCO keypoints used by YOLO pose models
RIGHT_SHOULDER = 6
RIGHT_ELBOW = 8
RIGHT_WRIST = 10


def is_right_hand_raised(keypoints_xy, min_vertical_gap=40):
    """
    keypoints_xy: shape (num_kpts, 2) for ONE person.
    Returns True if the right wrist is clearly above the right shoulder.
    """
    if keypoints_xy is None or len(keypoints_xy) <= RIGHT_WRIST:
        return False

    shoulder = keypoints_xy[RIGHT_SHOULDER]
    wrist = keypoints_xy[RIGHT_WRIST]

    # Some models use (0,0) for missing keypoints
    if (shoulder[0] == 0 and shoulder[1] == 0) or (wrist[0] == 0 and wrist[1] == 0):
        return False

    # y is top-down. Smaller y = higher in the image.
    shoulder_y = shoulder[1]
    wrist_y = wrist[1]

    # Hand is "raised" if wrist is noticeably above shoulder
    return (shoulder_y - wrist_y) > min_vertical_gap


def main():
    print("Starting pose_click.py")

    # Make sure pyautogui can operate
    pyautogui.FAILSAFE = False
    print("pyautogui initialized")

    # Load pose model
    try:
        print("Loading YOLO pose model...")
        model = YOLO("yolo11n-pose.pt")  # change to "yolov8n-pose.pt" if needed
        print("Model loaded.")
    except Exception as e:
        print("Error loading model:", e)
        return

    print("Opening webcam...")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: Could not open webcam.")
        return

    print("Webcam opened.")
    print("Instructions:")
    print("  1) Focus the window you want to click in (e.g., Notepad).")
    print("  2) Raise your RIGHT hand above your shoulder to trigger a LEFT mouse click.")
    print("  3) Press 'q' in the video window to quit.")

    hand_raised_prev = False
    last_click_time = 0.0
    click_cooldown = 0.7  # seconds between allowed clicks

    frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: Failed to grab frame.")
            break

        frame_count += 1
        if frame_count % 60 == 0:
            print(f"Processing frames... (frame {frame_count})")

        # Run pose inference
        results = model(frame, verbose=False)

        annotated_frame = frame.copy()
        status_text = "Hand: down"

        if len(results) > 0 and results[0].keypoints is not None:
            kpts = results[0].keypoints

            # Take the first person (index 0) for now
            k_xy = kpts.xy[0].cpu().numpy()  # shape (num_kpts, 2)

            hand_raised_now = is_right_hand_raised(k_xy)

            # Draw default annotations from YOLO
            annotated_frame = results[0].plot()

            if hand_raised_now:
                status_text = "Hand: RAISED"

                current_time = time.time()
                if not hand_raised_prev and (current_time - last_click_time) > click_cooldown:
                    print("Hand raised detected → CLICK")
                    pyautogui.click()
                    last_click_time = current_time

            hand_raised_prev = hand_raised_now
        else:
            hand_raised_prev = False

        # Overlay status text on the frame
        cv2.putText(
            annotated_frame,
            status_text,
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )

        cv2.imshow("Pose Click – raise RIGHT hand to click (press 'q' to quit)", annotated_frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q") or key == 27:
            print("Exiting...")
            break

    cap.release()
    cv2.destroyAllWindows()
    print("Shutdown complete.")


if __name__ == "__main__":
    main()
