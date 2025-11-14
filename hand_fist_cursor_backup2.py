"""
Hand mouse control with:
- FIST       (0 fingers)         -> left mouse drag/click (primary hand)
- ONE FINGER (1 finger up)       -> used for two-hand zoom/pan
- OPEN HAND  (2+ fingers up)     -> normal

Global behavior:
- Primary hand (usually RIGHT):
    - Moves mouse cursor
    - FIST: left mouseDown while fist, mouseUp when not
      -> quick close+open = left click
      -> hold+move = left drag

- Two-hand gesture (two single fingers, mid-height):
    - Both hands visible, each with ONE FINGER, both mid-height:
        * If distance between hands is CHANGING -> zoom (mouse scroll)
        * If distance between hands is STEADY  -> middle mouse drag (press scroll wheel)
"""

import cv2
import math
import pyautogui
import mediapipe as mp

pyautogui.FAILSAFE = False

SCREEN_WIDTH, SCREEN_HEIGHT = pyautogui.size()

mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

# MediaPipe indices:
# Index: 5 (MCP), 6 (PIP), 7 (DIP), 8 (TIP)
# Middle: 9, 10, 11, 12
# Ring:   13, 14, 15, 16
# Pinky:  17, 18, 19, 20

FINGER_DEFS = [
    (8, 6),   # index:  (TIP, PIP)
    (12, 10), # middle: (TIP, PIP)
    (16, 14), # ring:   (TIP, PIP)
    (20, 18), # pinky:  (TIP, PIP)
]


def count_extended_fingers(landmarks, margin=0.02):
    """
    Count how many fingers are extended for a single hand
    (ignores thumb).

    Finger is "extended" if tip y is clearly ABOVE
    (smaller than) its PIP y by margin.
    """
    extended_count = 0

    for tip_idx, pip_idx in FINGER_DEFS:
        tip = landmarks[tip_idx]
        pip = landmarks[pip_idx]

        # y increases downward; extended: tip.y significantly LESS than pip.y
        if tip.y < (pip.y - margin):
            extended_count += 1

    return extended_count


def get_hand_state(landmarks):
    """
    Returns (hand_state_str, extended_finger_count) for a single hand.

    States:
      - "FIST"       when 0 fingers extended
      - "ONE FINGER" when 1 finger extended
      - "OPEN HAND"  when >= 2 fingers extended
    """
    ext = count_extended_fingers(landmarks)

    if ext == 0:
        return "FIST", ext
    elif ext == 1:
        return "ONE FINGER", ext
    else:
        return "OPEN HAND", ext


def main():
    print("Starting hand_fist_cursor.py (two-hand zoom + pan via steady distance)")
    print("Per-hand states:")
    print("  - FIST       (0 fingers)       -> left drag/click (primary hand)")
    print("  - ONE FINGER (1 finger up)     -> used in two-hand gestures")
    print("  - OPEN HAND  (2+ fingers up)")
    print("\nControls (primary hand, usually RIGHT):")
    print("  - Move hand            : mouse cursor moves")
    print("  - FIST                 : left mouse drag/click")
    print("\nTwo-hand gesture (mid-height, one finger each hand):")
    print("  - Distance CHANGING -> zoom (scroll)")
    print("  - Distance STEADY   -> middle button drag (pan frame)")
    print("Press 'q' or ESC in the video window to quit.\n")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: Could not open webcam.")
        return
    print("Webcam opened.")

    hands = mp_hands.Hands(
        model_complexity=0,
        max_num_hands=2,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    # Primary hand state
    prev_primary_state = "None"
    primary_left_drag_active = False

    # Cursor smoothing
    cursor_x = SCREEN_WIDTH / 2
    cursor_y = SCREEN_HEIGHT / 2
    smoothing = 0.55

    # Two-hand zoom/pan state
    prev_hand_distance = None
    zoom_deadzone = 0.005    # below this = "steady"
    zoom_gain = 1200.0       # distance change -> scroll amount
    middle_pan_active = False

    # Mid-height zoom band
    ZOOM_Y_MIN = 0.3
    ZOOM_Y_MAX = 0.7

    frame_count = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Frame grab error.")
                break

            frame_count += 1
            if frame_count % 60 == 0:
                print(f"Processing frames... (frame {frame_count})")

            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.process(rgb)

            display_text = "No hand"
            two_hand_zoom_active = False
            two_hand_pan_active = False

            if results.multi_hand_landmarks:
                hand_lms_list = results.multi_hand_landmarks
                num_hands = len(hand_lms_list)

                # Choose primary hand (prefer Right if available)
                primary_index = 0
                if results.multi_handedness:
                    for i, mh in enumerate(results.multi_handedness):
                        label = mh.classification[0].label  # "Left" or "Right"
                        if label == "Right":
                            primary_index = i
                            break

                hand_states = []
                hand_centers = []

                for i, hlm in enumerate(hand_lms_list):
                    lm_list = hlm.landmark
                    state, ext = get_hand_state(lm_list)
                    hand_states.append(state)

                    index_mcp = lm_list[5]
                    hand_centers.append(index_mcp)

                    mp_drawing.draw_landmarks(
                        frame,
                        hlm,
                        mp_hands.HAND_CONNECTIONS,
                        mp_drawing.DrawingSpec(thickness=2, circle_radius=2),
                        mp_drawing.DrawingSpec(thickness=2),
                    )

                # --- Primary hand cursor + left drag ---
                primary_lm_list = hand_lms_list[primary_index].landmark
                primary_state = hand_states[primary_index]
                primary_is_fist = (primary_state == "FIST")

                primary_index_mcp = primary_lm_list[5]
                norm_x = primary_index_mcp.x
                norm_y = primary_index_mcp.y

                target_x = norm_x * SCREEN_WIDTH
                target_y = norm_y * SCREEN_HEIGHT

                cursor_x = (1 - smoothing) * cursor_x + smoothing * target_x
                cursor_y = (1 - smoothing) * cursor_y + smoothing * target_y
                pyautogui.moveTo(int(cursor_x), int(cursor_y))

                # Handle left-button drag transitions
                if prev_primary_state == "FIST" and primary_state != "FIST":
                    if primary_left_drag_active:
                        pyautogui.mouseUp(button="left")
                        primary_left_drag_active = False
                        print("Primary fist ended → left mouseUp")

                if primary_state == "FIST" and prev_primary_state != "FIST":
                    pyautogui.mouseDown(button="left")
                    primary_left_drag_active = True
                    print("Primary fist start → left mouseDown")

                prev_primary_state = primary_state

                # --- Two-hand zoom/pan ---
                if num_hands >= 2:
                    center0 = hand_centers[0]
                    center1 = hand_centers[1]
                    state0 = hand_states[0]
                    state1 = hand_states[1]

                    # Both one-finger and mid-height
                    both_one_finger = (state0 == "ONE FINGER" and state1 == "ONE FINGER")
                    both_mid_height = (
                        ZOOM_Y_MIN <= center0.y <= ZOOM_Y_MAX
                        and ZOOM_Y_MIN <= center1.y <= ZOOM_Y_MAX
                    )

                    if both_one_finger and both_mid_height:
                        dx = center0.x - center1.x
                        dy = center0.y - center1.y
                        dist = math.sqrt(dx * dx + dy * dy)

                        if prev_hand_distance is not None:
                            delta = dist - prev_hand_distance

                            if abs(delta) > zoom_deadzone:
                                # ZOOM MODE (distance changing)
                                two_hand_zoom_active = True
                                two_hand_pan_active = False

                                # If we were panning, stop middle drag
                                if middle_pan_active:
                                    pyautogui.mouseUp(button="middle")
                                    middle_pan_active = False
                                    print("Two-hand: distance changed → end middle pan")

                                scroll_amount = int(delta * zoom_gain)
                                if scroll_amount != 0:
                                    pyautogui.scroll(scroll_amount)
                            else:
                                # PAN MODE (distance steady)
                                two_hand_pan_active = True
                                two_hand_zoom_active = False

                                if not middle_pan_active:
                                    pyautogui.mouseDown(button="middle")
                                    middle_pan_active = True
                                    print("Two-hand: steady distance → start middle pan")
                        prev_hand_distance = dist
                    else:
                        # Left two-hand mode; release middle button if active
                        prev_hand_distance = None
                        if middle_pan_active:
                            pyautogui.mouseUp(button="middle")
                            middle_pan_active = False
                            print("Two-hand condition lost → end middle pan")
                else:
                    # Only one or zero hands
                    prev_hand_distance = None
                    if middle_pan_active:
                        pyautogui.mouseUp(button="middle")
                        middle_pan_active = False
                        print("Hands <2 → end middle pan")

                display_text = primary_state
                if two_hand_zoom_active:
                    display_text += " + ZOOM"
                if middle_pan_active:
                    display_text += " + PAN"
            else:
                # No hands: release any drag state
                if primary_left_drag_active:
                    pyautogui.mouseUp(button="left")
                    primary_left_drag_active = False
                    print("No hand → left mouseUp (safety)")

                if middle_pan_active:
                    pyautogui.mouseUp(button="middle")
                    middle_pan_active = False
                    print("No hand → middle mouseUp (safety)")

                prev_primary_state = "None"
                prev_hand_distance = None

            cv2.putText(
                frame,
                display_text,
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )

            cv2.imshow("Hand Control (fist + two-hand zoom/pan) – 'q' to quit", frame)

            key = cv2.waitKey(1) & 0xFF
            if key in [ord('q'), 27]:
                print("Exiting...")
                break

    finally:
        # Cleanup
        cap.release()
        hands.close()
        cv2.destroyAllWindows()

        # Safety: make sure buttons are up
        try:
            pyautogui.mouseUp(button="left")
        except Exception:
            pass
        try:
            pyautogui.mouseUp(button="middle")
        except Exception:
            pass

        print("Shutdown complete.")


if __name__ == "__main__":
    main()
