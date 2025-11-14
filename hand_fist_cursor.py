"""
Hand mouse control with:
- FIST       (0 fingers)         -> left mouse click/drag (with click lock)
- ONE FINGER (1 finger up)       -> used for two-hand zoom/pan
- OPEN HAND  (2+ fingers up)     -> normal

Global behavior:
- Primary hand (usually RIGHT):
    - Moves mouse cursor (anchored at wrist)
    - FIST: state machine:
        * IDLE -> PENDING_CLICK when fist first closes
        * PENDING_CLICK: cursor locked at click_origin (no tiny movement)
        * DRAGGING: once wrist moves beyond threshold, cursor follows (drag)
      -> quick close + open without moving much = precise click

- Two-hand gesture (two single fingers, mid-height):
    - Both hands visible, each with ONE FINGER, both mid-height:
        * If distance between hands is CHANGING -> zoom (mouse scroll)
        * If distance between hands is STEADY  -> middle mouse drag (pan frame)
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
# Wrist: 0
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
    print("Starting hand_fist_cursor.py (click lock + two-hand zoom/pan)")
    print("Per-hand states:")
    print("  - FIST       (0 fingers)       -> left click/drag with click lock")
    print("  - ONE FINGER (1 finger up)     -> used in two-hand gestures")
    print("  - OPEN HAND  (2+ fingers up)")
    print("\nControls (primary hand, usually RIGHT):")
    print("  - Move hand            : mouse cursor moves (wrist anchor)")
    print("  - FIST                 :")
    print("       * small motion -> click at fixed spot")
    print("       * big motion   -> drag from that spot")
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

    # Primary hand click/drag state machine
    # States: "IDLE", "PENDING_CLICK", "DRAGGING"
    click_state = "IDLE"
    click_origin_x = None
    click_origin_y = None
    origin_wrist_x = None
    origin_wrist_y = None

    # Cursor smoothing
    cursor_x = SCREEN_WIDTH / 2
    cursor_y = SCREEN_HEIGHT / 2
    smoothing = 0.55

    # Threshold for transitioning from click to drag (in normalized wrist distance)
    DRAG_START_NORM = 0.03

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

                    # Use index MCP as hand center for zoom/pan
                    index_mcp = lm_list[5]
                    hand_centers.append(index_mcp)

                    mp_drawing.draw_landmarks(
                        frame,
                        hlm,
                        mp_hands.HAND_CONNECTIONS,
                        mp_drawing.DrawingSpec(thickness=2, circle_radius=2),
                        mp_drawing.DrawingSpec(thickness=2),
                    )

                # --- Primary hand cursor + click state machine ---
                primary_lm_list = hand_lms_list[primary_index].landmark
                primary_state = hand_states[primary_index]
                primary_is_fist = (primary_state == "FIST")

                # Wrist for more stable cursor anchor
                wrist = primary_lm_list[0]
                wrist_x = wrist.x
                wrist_y = wrist.y

                # Compute smoothed target position for when we allow motion
                target_x = wrist_x * SCREEN_WIDTH
                target_y = wrist_y * SCREEN_HEIGHT

                cursor_x = (1 - smoothing) * cursor_x + smoothing * target_x
                cursor_y = (1 - smoothing) * cursor_y + smoothing * target_y

                # --- Click state transitions ---
                if not primary_is_fist:
                    # Leaving any fist state: ensure mouseUp and reset state
                    if click_state in ("PENDING_CLICK", "DRAGGING"):
                        pyautogui.mouseUp(button="left")
                        print("Primary fist released → left mouseUp")
                    click_state = "IDLE"
                    origin_wrist_x = None
                    origin_wrist_y = None
                    click_origin_x = None
                    click_origin_y = None
                else:
                    # primary_is_fist == True
                    if click_state == "IDLE":
                        # Just entered fist: start pending click
                        click_state = "PENDING_CLICK"
                        origin_wrist_x = wrist_x
                        origin_wrist_y = wrist_y

                        # Use current cursor position as click origin
                        click_origin_x, click_origin_y = pyautogui.position()
                        pyautogui.mouseDown(button="left")
                        print("Primary fist start → left mouseDown (PENDING_CLICK)")

                    elif click_state == "PENDING_CLICK":
                        # Check how far the wrist moved from origin
                        dx = wrist_x - origin_wrist_x
                        dy = wrist_y - origin_wrist_y
                        dist = math.sqrt(dx * dx + dy * dy)

                        if dist >= DRAG_START_NORM:
                            # Promote to dragging
                            click_state = "DRAGGING"
                            print("Primary fist moved → DRAGGING")
                        # else remain in PENDING_CLICK

                    elif click_state == "DRAGGING":
                        # Nothing special; dragging continues
                        pass

                # --- Cursor movement depending on click state ---
                if click_state == "PENDING_CLICK" and click_origin_x is not None:
                    # Lock cursor at click origin for stable click
                    pyautogui.moveTo(click_origin_x, click_origin_y)
                else:
                    # Normal movement (IDLE or DRAGGING)
                    pyautogui.moveTo(int(cursor_x), int(cursor_y))

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
                                if not middle_pan_active:
                                    pyautogui.mouseDown(button="middle")
                                    middle_pan_active = True
                                    print("Two-hand: steady distance → start middle pan")
                        prev_hand_distance = dist
                    else:
                        prev_hand_distance = None
                        if middle_pan_active:
                            pyautogui.mouseUp(button="middle")
                            middle_pan_active = False
                            print("Two-hand condition lost → end middle pan")
                else:
                    prev_hand_distance = None
                    if middle_pan_active:
                        pyautogui.mouseUp(button="middle")
                        middle_pan_active = False
                        print("Hands <2 → end middle pan")

                display_text = f"{primary_state} [{click_state}]"
                if two_hand_zoom_active:
                    display_text += " + ZOOM"
                if middle_pan_active:
                    display_text += " + PAN"
            else:
                # No hands: release any drag state
                if click_state in ("PENDING_CLICK", "DRAGGING"):
                    pyautogui.mouseUp(button="left")
                    click_state = "IDLE"
                    print("No hand → left mouseUp (safety)")

                if middle_pan_active:
                    pyautogui.mouseUp(button="middle")
                    middle_pan_active = False
                    print("No hand → middle mouseUp (safety)")

                prev_hand_distance = None
                display_text = "No hand"

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

            cv2.imshow("Hand Control (click lock + two-hand zoom/pan) – 'q' to quit", frame)

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
