"""Loading engine logic - pure functions without database or Flask"""

RIR_MAP = {'EASY': 4.0, 'TARGET': 2.5, 'HARD': 1.0, 'FAILURE': 0.0}


def mesocycle_phase(counter):
    """Determine the current mesocycle phase based on counter value.
    
    Args:
        counter: int - number of sessions completed for this exercise (0-11)

    Returns:
        str: Phase name ('BASELINE', 'PROGRESSING', 'CONTINUING', 'HARDEST', 'MESOCYCLE_DELOAD')
    """
    if 0 <= counter <= 2:
        return 'BASELINE'
    elif 3 <= counter <= 6:
        return 'PROGRESSING'
    elif 7 <= counter <= 9:
        return 'CONTINUING'
    elif counter == 10:
        return 'HARDEST'
    else:  # counter == 11
        return 'MESOCYCLE_DELOAD'


def step1(actual_reps, rep_range, rir_feedback, pec_affected=False):
    """Determine the first-step action based on reps and feedback.
    
    Args:
        actual_reps: list of int - actual repetitions for each set
        rep_range: tuple of (lo, hi) - target repetition range
        rir_feedback: str - RIR feedback ('EASY', 'TARGET', 'HARD', 'FAILURE')
        pec_affected: bool - whether pec status indicates affected muscles
        
    Returns:
        str: Action ('INCREASE_LOAD', 'DECREASE_LOAD', or 'HOLD_LOAD')
    """
    rep_range_lo, rep_range_hi = rep_range
    
    # Check if all reps are at or above the high end of the range
    all_at_ceiling = all(r >= rep_range_hi for r in actual_reps)
    
    # Determine increase_band based on pec_affected flag
    if pec_affected:
        increase_band = ('EASY', 'TARGET')  # EASY to TARGET when pec affected
    else:
        increase_band = ('TARGET', 'HARD')  # TARGET to HARD normally
    
    if all_at_ceiling and rir_feedback in increase_band:
        return 'INCREASE_LOAD'
    elif any(r < rep_range_lo for r in actual_reps) and rir_feedback == 'FAILURE':
        return 'DECREASE_LOAD'
    else:
        return 'HOLD_LOAD'


def step2(recent_sessions, session, rep_range, phase, pec_affected=False):
    """Determine the second-step action based on recent performance trends.
    
    Args:
        recent_sessions: list of dicts - last 3 sessions with actual_reps and rir_feedback 
        session: dict - current session's actual_reps and rir_feedback
        rep_range: tuple of (lo, hi) - target repetition range  
        phase: str - current mesocycle phase ('BASELINE', 'PROGRESSING', etc.)
        pec_affected: bool - whether pec status indicates affected muscles
        
    Returns:
        str or None: Action ('INCREASE_LOAD', 'DECREASE_LOAD') or None if no action
    """
    # Disable step2 in BASELINE phase
    if phase == 'BASELINE':
        return None
    
    # Extract rep data for recent sessions (assuming session is last in list)
    if not recent_sessions:
        return None
    
    # Early increase rules
    if len(recent_sessions) >= 2:
        # Last two sessions were all EASY and minimum reps meet midpoint target
        recent_two = recent_sessions[-2:]
        
        # Check if the last 2 are 'EASY'
        if all(s['rir_feedback'] == 'EASY' for s in recent_two):
            
            # Calculate midpoint of rep range
            lo, hi = rep_range
            midpoint = (lo + hi) / 2
            
            # Check if min reps in each session >= midpoint
            min_reps_all = all(min(s['actual_reps']) >= midpoint for s in recent_two)
            if min_reps_all:
                return 'INCREASE_LOAD'
    
    # Early decrease rules
    if len(recent_sessions) >= 1:
        # ONE FAILURE this session is enough to decrease (when pec_affected)  
        if pec_affected and session['rir_feedback'] == 'FAILURE':
            return 'DECREASE_LOAD'
        
        # TWO consecutive HARD sessions decrease when pec_affected
        if pec_affected and len(recent_sessions) >= 2:
            recent_two = recent_sessions[-2:]
            if all(s['rir_feedback'] == 'HARD' for s in recent_two):
                return 'DECREASE_LOAD'
                
        # If not pec affected, ONE failure this session is enough to decrease
        if not pec_affected and session['rir_feedback'] == 'FAILURE':
            return 'DECREASE_LOAD'
        
        # TWO consecutive HARD sessions decrease (non-pec affected)
        if len(recent_sessions) >= 2:
            recent_two = recent_sessions[-2:]
            if all(s['rir_feedback'] == 'HARD' for s in recent_two):
                return 'DECREASE_LOAD'
    
    # Performance drop rule
    if len(recent_sessions) >= 3:
        # Get the last three sessions (most recent first)
        top_sets = [max(s['actual_reps']) for s in recent_sessions[:3]]
        
        # Performance drop: top_set of this session < prev_top_set - 2 AND 
        # prev_top_set < prev_prev_top_set - 2
        if (top_sets[0] < top_sets[1] - 2 and 
            top_sets[1] < top_sets[2] - 2):
            return 'DECREASE_LOAD'
    
    return None


def evaluate_session(state, actual_reps, rir_feedback):
    """Evaluate a session and determine the next recommended action.
    
    Args:
        state: dict - exercise_state record
        actual_reps: list of int - actual repetitions performed
        rir_feedback: str - RIR feedback ('EASY', 'TARGET', 'HARD', 'FAILURE')
        
    Returns:
        dict: Recommendation with keys: exercise_id, action, reason, next_load, 
              next_rep_target, mesocycle_phase, sessions_in_mesocycle
    """
    # Extract state components
    exercise_id = state['exercise_id']
    current_load = state['current_load']
    rep_range_lo = state['rep_range_lo']
    rep_range_hi = state['rep_range_hi'] 
    load_step = state['load_step']
    rir_target_lo = state['rir_target_lo']
    rir_target_hi = state['rir_target_hi']
    sessions_in_mesocycle = state['sessions_in_mesocycle']
    recent_sessions_json = state['recent_sessions_json']
    progression_mode = state['progression_mode']
    
    # If mesocycle counter is 11 (MESOCYCLE_DELOAD), return MESOCYCLE_DELOAD immediately
    if sessions_in_mesocycle == 11:
        return {
            'exercise_id': exercise_id,
            'action': 'MESOCYCLE_DELOAD',
            'reason': 'Mesocycle complete - no further progression',
            'next_load': None,
            'next_rep_target': None,
            'mesocycle_phase': mesocycle_phase(sessions_in_mesocycle),
            'sessions_in_mesocycle': sessions_in_mesocycle
        }
    
    # Run step1 first
    recent_sessions = []  # In the actual implementation, this should come from recent_sessions_json
    
    # Determine if pec is affected (from rir_target)
    pec_affected = (rir_target_lo == 3 and rir_target_hi == 4)
    
    # Run Step1
    step1_action = step1(actual_reps, (rep_range_lo, rep_range_hi), rir_feedback, pec_affected)
    
    final_action = step1_action
    
    # If HOLD_LOAD and not in BASELINE phase, run Step2 
    if step1_action == 'HOLD_LOAD' and mesocycle_phase(sessions_in_mesocycle) != 'BASELINE':
        step2_action = step2(recent_sessions, {'actual_reps': actual_reps, 'rir_feedback': rir_feedback}, 
                           (rep_range_lo, rep_range_hi), mesocycle_phase(sessions_in_mesocycle), pec_affected)
        
        if step2_action is not None:
            final_action = step2_action
    
    # Apply action rules
    next_load = current_load
    next_rep_target = f"{rep_range_lo}-{rep_range_hi}"
    
    reason_text = ""
    
    if final_action == 'INCREASE_LOAD':
        next_load = current_load + load_step
        reason_text = f"All {len(actual_reps)} sets reached {rep_range_hi} reps at {rir_feedback.lower()} RIR."
        
    elif final_action == 'DECREASE_LOAD':
        next_load = current_load - load_step
        reason_text = "Below target or failed set detected."
        
    else:  # HOLD_LOAD
        reason_text = f"Session within target range; performance consistent with expectations." 
    
    return {
        'exercise_id': exercise_id,
        'action': final_action,
        'reason': reason_text,
        'next_load': next_load,
        'next_rep_target': next_rep_target,
        'mesocycle_phase': mesocycle_phase(sessions_in_mesocycle),
        'sessions_in_mesocycle': sessions_in_mesocycle
    }