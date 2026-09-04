import yaml
from pathlib import Path

# Module-level cache for the config
_phase2_config = None

def load_phase2_config():
    """Parse and validate the phase 2 exercise configuration.
    
    Raises:
        ValueError: If validation fails with a clear message.
    """
    global _phase2_config
    
    if _phase2_config is not None:
        return _phase2_config
        
    config_path = Path('phase2_exercise_config.yaml')
    
    if not config_path.exists():
        raise ValueError("Phase 2 exercise configuration file not found")
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Validate: all 20 exercises present
    expected_exercises = [
        'back_squat', 'barbell_row', 'ohp', 'deadlift', 'dips', 
        'pull_ups', 'incline_bench', 'lat_pull_down',
        'seated_cable_row', 'weighted_squats', 'calf_raise',
        'landmine_press', 'bulgarian_split_squat', 'tricep_pushdown',
        'leg_press', 'push_ups', 'band_pull_aparts', 'chest_fly',
        'shoulder_shrug', 'pull_ups_fri'
    ]
    
    for exercise_id in expected_exercises:
        if exercise_id not in config:
            raise ValueError(f"Missing exercise configuration: {exercise_id}")
        
    # Validate each exercise has required fields
    valid_progression_modes = ['standard', 'reps_only', 'ramp_governed', 'excluded']
    
    for exercise_id, exercise_config in config.items():
        if 'category' not in exercise_config:
            raise ValueError(f"Exercise {exercise_id} missing category")
        if 'muscle_group' not in exercise_config:
            raise ValueError(f"Exercise {exercise_id} missing muscle_group")
        if 'sets' not in exercise_config:
            raise ValueError(f"Exercise {exercise_id} missing sets")
        if 'progression_mode' not in exercise_config:
            raise ValueError(f"Exercise {exercise_id} missing progression_mode")
        if exercise_config['progression_mode'] not in valid_progression_modes:
            raise ValueError(f"Exercise {exercise_id} has invalid progression_mode: {exercise_config['progression_mode']}")
        
        # For non-excluded exercises, validate rep_range is present
        if exercise_config['progression_mode'] != 'excluded':
            if 'rep_range' not in exercise_config or exercise_config['rep_range'] is None:
                raise ValueError(f"Exercise {exercise_id} missing rep_range")
            
        # Validate muscle_group_ceilings block exists and has exactly 8 groups
        if 'muscle_group_ceilings' not in config:
            raise ValueError("Missing muscle_group_ceilings block")
        
        muscle_groups = config['muscle_group_ceilings']
        if len(muscle_groups) != 8:
            raise ValueError(f"Expected exactly 8 muscle groups in ceiling config, got {len(muscle_groups)}")
    
    # Cache the config
    _phase2_config = config
    return config

def seed_exercise_state():
    """Seed exercise_state with initial data from the configuration."""
    from trainlog.db import execute, query_one
    
    config = load_phase2_config()
    
    # Create a set of all muscle groups mentioned in exercises
    muscle_groups_in_use = set()
    for exercise_id, exercise_config in config.items():
        if 'muscle_group' in exercise_config:
            muscle_groups_in_use.add(exercise_config['muscle_group']) 
    muscle_groups_in_use = list(muscle_groups_in_use)
    
    # Seed muscle_group_state table
    for group in muscle_groups_in_use:
        execute("""
            INSERT OR IGNORE INTO muscle_group_state (muscle_group, current_weekly_sets, last_increase_date, cooldown_sessions_left)
            VALUES (?, ?, NULL, 0)
        """, (group, config['muscle_group_ceilings'][group]))
    
    # Seed exercise_state table
    for exercise_id, exercise_config in config.items():
        # Get the ceiling value for this exercise's muscle group
        muscle_group_ceiling = config['muscle_group_ceilings'][exercise_config['muscle_group']]
        
        # Handle different progression modes
        if exercise_config['progression_mode'] == 'reps_only':
            current_load = None
            load_step = None
            added_weight_lb = 0
        elif exercise_config['progression_mode'] == 'excluded':
            current_load = None
            load_step = None
            added_weight_lb = 0
        else:
            current_load = exercise_config.get('start_load', 0)
            load_step = exercise_config.get('load_step')
            added_weight_lb = 0
        
        # Set defaults 
        rir_target_lo = exercise_config.get('rir_target', [2, 3])[0]
        rir_target_hi = exercise_config.get('rir_target', [2, 3])[1]        
        rep_range_lo = exercise_config['rep_range'][0] if 'rep_range' in exercise_config and exercise_config['rep_range'] is not None else 0
        rep_range_hi = exercise_config['rep_range'][1] if 'rep_range' in exercise_config and exercise_config['rep_range'] is not None else 0
        
        # Insert or ignore (prevents duplicating seed data on subsequent startups)
        execute("""
            INSERT OR IGNORE INTO exercise_state 
            (exercise_id, current_load, added_weight_lb, rep_range_lo, rep_range_hi, 
             target_sets, load_step, rir_target_lo, rir_target_hi, progression_mode, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            exercise_id,
            current_load,
            added_weight_lb,
            rep_range_lo,
            rep_range_hi,
            exercise_config['sets'],
            load_step,
            rir_target_lo,
            rir_target_hi,
            exercise_config['progression_mode']
        ))