from ultralytics import YOLO
import cv2


def main():
    # Load a small YOLO pose model (auto-downloads on first run)
    model = YOLO("yolo11n-pose.pt")  # if this fails, we can switch to yolov8n-pose.pt

    # Open the default webcam (0)
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("Error: Could not open webcam.")
        return

    print("Webcam opened. Press 'q' in the video window to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: Failed to grab frame.")
            break

        # Run pose inference
        results = model(frame, verbose=False)

        # Draw skeletons and boxes on the frame
        annotated_frame = results[0].plot()

        # Show the result
        cv2.imshow("YOLO Pose – press 'q' to quit", annotated_frame)

        # Exit on 'q' or ESC
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q") or key == 27:
            print("Exiting...")
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
