#!/usr/bin/env python3
"""
Task-008: Static Checker v1

This module is the single source of truth for static verification rules used by
the direct baseline, RAG baseline, IR-to-script generation, and later repair
loops.
"""

import argparse
import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from afsim_context_rules_v1 import get_command_context_rule, get_wsf_type_rule


ROOT = Path(__file__).resolve().parent.parent


BLOCK_STARTS = {
    "script_interface": "end_script_interface",
    "event_output": "end_event_output",
    "event_pipe": "end_event_pipe",
    "dis_interface": "end_dis_interface",
    "network": "end_network",
    "launch_computer": "end_launch_computer",
    "platform_type": "end_platform_type",
    "platform": "end_platform",
    "mover": "end_mover",
    "route": "end_route",
    "sensor": "end_sensor",
    "weapon": "end_weapon",
    "processor": "end_processor",
    "antenna_pattern": "end_antenna_pattern",
    "constant_pattern": "end_constant_pattern",
    "transmitter": "end_transmitter",
    "receiver": "end_receiver",
    "script_variables": "end_script_variables",
    "on_initialize": "end_on_initialize",
    "on_update": "end_on_update",
    "comm": "end_comm",
    "advanced_behavior": "end_advanced_behavior",
    "behavior_tree": "end_behavior_tree",
    "advanced_behavior_tree": "end_advanced_behavior_tree",
    "parallel": "end_parallel",
    "sequence": "end_sequence",
    "selector": "end_selector",
    "condition": "end_condition",
    "chaff_parcel": "end_chaff_parcel",
    "frequency_maximum_rcs_table": "end_frequency_maximum_rcs_table",
    "ejector": "end_ejector",
}

END_TO_START = {value: key for key, value in BLOCK_STARTS.items()}

UNIT_COMMANDS = {
    "maximum_speed",
    "minimum_speed",
    "default_radial_acceleration",
    "default_linear_acceleration",
    "frame_time",
    "update_interval",
    "pulse_width",
    "pulse_repetition_frequency",
    "frequency",
    "power",
    "bandwidth",
    "one_m2_detect_range",
    "altitude",
    "heading",
    "speed",
    "end_time",
    "maximum_range",
    "minimum_range",
}

DEFAULT_SYNTAX_ERROR_IDS = {"E001", "E002", "E004", "E007", "E008"}
DEFAULT_STATIC_BLOCKING_ERROR_IDS = {"E001", "E002", "E003", "E004", "E005", "E006", "E007", "E008"}

SUBCOMPONENT_PSEUDO_KEYWORDS = {"weapon_type", "sensor_type", "processor_type", "mover_type"}
NESTED_ONLY_KEYWORDS = {
    "command_chain": "platform",
    "task": "processor",
}
UNSUPPORTED_STANDALONE_COMMANDS = {
    "mission_log": "mission_log is not a valid standalone AFSIM command; use supported output blocks such as event_pipe or event_output",
    "output": "output is not a valid standalone AFSIM command in scenario scope",
}
UNSUPPORTED_DIRECTIVES = {
    "beam_pattern": "beam_pattern is not a validated AFSIM command in this project corpus",
    "beam": "beam is not a validated AFSIM command in this project corpus; use documented sensor patterns",
    "comm_link": "comm_link is not a validated AFSIM command in this project corpus",
    "comm_network": "comm_network is not a validated AFSIM command in this project corpus; use supported comm blocks instead",
    "comm_transceiver": "comm_transceiver is not a valid block keyword; use comm ... WSF_COMM_TRANSCEIVER",
    "constant": "constant is not a valid block keyword; use constant_pattern under antenna_pattern when needed",
    "directive": "directive is not a valid AFSIM script command in this context",
    "frequency_max": "frequency_max is not a verified AFSIM sensor command in this corpus; use verified band or detection_sensitivity patterns",
    "frequency_min": "frequency_min is not a verified AFSIM sensor command in this corpus; use verified band or detection_sensitivity patterns",
    "end_beam": "end_beam closes an unsupported beam block",
    "end_comm_network": "end_comm_network closes an unsupported comm_network block",
    "end_comm_transceiver": "end_comm_transceiver closes an unsupported comm_transceiver block",
    "end_constant": "end_constant closes an unsupported constant block",
    "end_explicit_weapon": "end_explicit_weapon closes an unsupported explicit_weapon block; use weapon ... end_weapon",
    "end_process": "end_process closes an unsupported process block; use end_processor",
    "end_radar_sensor": "end_radar_sensor closes an unsupported radar_sensor block; use sensor ... end_sensor",
    "end_task_processor": "end_task_processor closes an unsupported task_processor block; use processor ... end_processor",
    "end_track_processor": "end_track_processor closes an unsupported track_processor block; use processor ... end_processor",
    "explicit_weapon": "explicit_weapon is not a valid block keyword; use weapon ... WSF_EXPLICIT_WEAPON",
    "process": "process is not a valid block keyword; use processor ... end_processor",
    "radar_sensor": "radar_sensor is not a valid block keyword; use sensor ... WSF_RADAR_SENSOR",
    "sensitivity": "sensitivity is not a verified sensor command in this corpus; use detection_sensitivity or a documented mode template",
    "task_processor": "task_processor is not a valid block keyword; use processor ... WSF_TASK_PROCESSOR",
    "track_processor": "track_processor is not a valid block keyword; use processor ... WSF_TRACK_PROCESSOR",
    "track_output_comm": "track_output_comm is not a validated AFSIM command in this project corpus",
}
AIR_MOVER_UNSUPPORTED_COMMANDS = {"default_climb_rate", "default_descent_rate"}

# Commands that are only valid inside a mover block (not at platform or top level).
# Source: AFSIM 2.9.0 wsf_air_mover.html, wsf_ground_mover.html,
# wsf_surface_mover.html, wsf_subsurface_mover.html.
MOVER_ONLY_COMMANDS = {
    "maximum_speed", "minimum_speed",
    "altitude_offset", "at_end_of_path", "draw_route",
    "on_turn_failure", "pathfinder", "print_route",
    "start_at", "switch_on_approach", "switch_on_passing",
    "turn_failure_threshold",
    "forward_accel_max", "forward_accel_min",
    "vert_speed_max", "vert_speed_min",
    "bank_angle_max",
    "min_taxi_turn_radius", "taxi_speed_max_fps", "taxi_yaw_rate_max",
    "braking_coefficient_of_friction", "rolling_coefficient_of_friction",
    "scuffing_coefficient_of_friction",
    "nominal_height_above_ground_on_gear",
    "creates_smoke_trail", "engine_smokes_above_power_setting",
}

# WSF types that are cyber effects, NOT processors.
# Using them as a processor WSF type is an error.
# Source: AFSIM 2.9.0 wsf_cyber_script_effect.html, predefined_cyber_effect_types.html.
CYBER_EFFECT_TYPES = {
    "WSF_CYBER_SCRIPT_EFFECT", "WSF_CYBER_SCRIPT_EFFECT_ENHANCED",
    "WSF_CYBER_DETONATE_EFFECT", "WSF_CYBER_MAN_IN_THE_MIDDLE_EFFECT",
    "WSF_CYBER_TOGGLE_COMMS_EFFECT",
}
ANTENNA_REFERENCE_PARENTS = {"transmitter", "receiver"}
EDITABLE_BLOCKS = {"comm", "sensor", "processor", "weapon", "mover", "route"}

# Whitelist built from AFSIM 2.9.0 official Command Index (wsf-commandindex.html, 709 commands)
# plus programmatic sources (BLOCK_STARTS, END_TO_START, UNIT_COMMANDS) and known-good extras.
KNOWN_AFSIM_TOKENS = (
    BLOCK_STARTS.keys()
    | END_TO_START.keys()
    | UNIT_COMMANDS
    | UNSUPPORTED_DIRECTIVES.keys()
    | {
        'ATA_LAUNCH_COMPUTER_GENERATOR', 'access_report', 'acoustic_signature', 'action_activate_subobject_sequencer',
        'action_change_aero_mode', 'action_disable_controls', 'action_enable_controls', 'action_enable_size_factor',
        'action_ignite_engine', 'action_ignite_self', 'action_ignite_subobject', 'action_jett_obj',
        'action_jett_self', 'action_null', 'action_set_graphical_model', 'action_shutdown_engine',
        'action_shutdown_subobject', 'action_terminate_thrust', 'active_pilot', 'additional_radii',
        'additional_rings', 'advanced_behavior', 'advanced_behavior_tree', 'aero', 'aero_center_x', 'aero_center_y',
        'aero_center_z', 'aero_component', 'aero_data', 'aero_file', 'aero_mode',
        'afterburner_appearance_when_operating', 'afterburner_threshold', 'air_traffic',
        'aircraft_signature_parameters', 'align_north', 'all_events', 'alpha_max', 'alpha_min',
        'alpha_stabilizing_frequency_mach_table', 'alternate_locations', 'alternate_locations_global_debug',
        'alternate_locations_global_draw', 'alternate_locations_use_global_draw', 'altitude', 'altitude_range',
        'angle_label_color', 'angle_width', 'antenna_pattern', 'antenna_plot', 'apoapsis', 'apoapsis_altitude',
        'ascending_node', 'ascending_radius', 'atmosphere_calibration', 'atmosphere_model', 'atmosphere_table',
        'atmosphere_type', 'atmospheric_coefficients', 'attenuation_model', 'attitude_controller', 'autopilot_config',
        'autopilot_config_file', 'avoid_runway', 'azimuth_angle_increment', 'azimuth_angle_limit',
        'azimuth_beamwidth', 'ballistic_types', 'bandwidth', 'bank_angle_max', 'behavior', 'behavior_tree',
        'beta_max', 'beta_stabilizing_frequency_mach_table', 'bin_size', 'bloom_diameter',
        'braking_coefficient_of_friction', 'braking_control_surface_name', 'bullseye', 'burn_rate',
        'cLFactor_angle_mach_table', 'cL_alpha_beta_mach_table', 'cL_alpha_mach_table',
        'cL_alphadot_alpha_mach_table', 'cL_angle_alpha_mach_table', 'cLq_alpha_mach_table', 'callback', 'capacity',
        'cd_alpha_beta_mach_table', 'cd_alpha_mach_table', 'cd_angle_alpha_mach_table', 'cd_angle_beta_mach_table',
        'cd_angle_mach_table', 'cd_beta_mach_table', 'center_angle', 'center_of_mass_x', 'center_of_mass_x1',
        'center_of_mass_y', 'center_of_mass_y1', 'center_of_mass_z', 'center_of_mass_z1', 'center_radius',
        'central_body', 'chaff_parcel', 'cl_alpha_beta_mach_table', 'cl_alphadot_mach_table',
        'cl_angle_alpha_beta_table', 'cl_angle_mach_table', 'cl_beta_mach_table', 'cl_betadot_mach_table',
        'classification', 'classification_levels', 'clock_rate', 'clp_angle_mach_table', 'clp_mach_table',
        'clq_angle_mach_table', 'clq_mach_table', 'clr_angle_mach_table', 'clr_mach_table', 'clutter_model',
        'clutter_table', 'cm_alpha_beta_mach_table', 'cm_alpha_mach_table', 'cm_alphadot_mach_table',
        'cm_angle_alpha_mach_table', 'cmp_mach_table', 'cmq_angle_mach_table', 'cmq_mach_table',
        'cn_alpha_beta_mach_table', 'cn_angle_beta_mach_table', 'cn_beta_mach_table', 'cn_betadot_mach_table',
        'cnp_mach_table', 'cnr_angle_mach_table', 'cnr_mach_table', 'collision_check', 'comm',
        'common_autopilot_support_file', 'common_orbital_propagator_commands', 'conditional_section',
        'console_output', 'contrail_max_altitude', 'contrail_min_altitude', 'contrailing_altitude_ceiling',
        'contrailing_altitude_floor', 'control_augmentation_system_file', 'control_inputs', 'control_method',
        'control_name', 'control_surface_name', 'control_value', 'controls_config_file', 'correlation_method',
        'coverage', 'creates_smoke_trail', 'cross_sectional_area', 'csv_event_output', 'cy_alpha_beta_mach_table',
        'cy_angle_beta_mach_table', 'cy_beta_mach_table', 'cy_betadot_beta_mach_table', 'cyber_attack',
        'cyber_constraint', 'cyber_effect', 'cyber_protect', 'cyber_trigger', 'cyr_beta_mach_table',
        'damper_constant_lbs_per_fps', 'debug', 'debug_output_oe', 'debug_output_stk', 'debug_output_wsf',
        'debug_output_xyz', 'decay_constant', 'deceleration_rate', 'decoration', 'default_atmosphere_type',
        'default_fidelity', 'default_linear_acceleration', 'default_radial_acceleration', 'define_path_variable',
        'delta_atomic_time', 'delta_time', 'delta_universal_time', 'delta_v',
        'deprecated_orbital_propagator_commands', 'descending_node', 'descending_radius', 'detached',
        'detection_sensitivity', 'diffraction', 'dis_interface', 'drag_coefficient', 'draw', 'draw_file',
        'drift_rate', 'duration', 'dv_x', 'dv_y', 'dv_z', 'eccentricity', 'eclipse_entry', 'eclipse_exit',
        'eclipse_report', 'egm96', 'ejection_velocity', 'ejector', 'electronic_attack', 'electronic_protect',
        'electronic_warfare', 'electronic_warfare_effect', 'electronic_warfare_technique', 'elevation_beamwidth',
        'empty_mass', 'end_advanced_behavior_tree', 'end_antenna_pattern', 'end_behavior_tree', 'end_chaff_parcel',
        'end_comm', 'end_condition', 'end_constant_pattern', 'end_csv_event_output', 'end_dis_interface',
        'end_ejector', 'end_event_output', 'end_event_pipe', 'end_frequency_maximum_rcs_table', 'end_mover',
        'end_network', 'end_on_initialize', 'end_on_update', 'end_orbit', 'end_parallel', 'end_platform',
        'end_platform_type', 'end_processor', 'end_pursue', 'end_receiver', 'end_repeat', 'end_route',
        'end_script_interface', 'end_script_variables', 'end_selector', 'end_sensor', 'end_sequence', 'end_time',
        'end_transmitter', 'end_weapon', 'engage', 'engine', 'engine_smokes_above_power_setting', 'entity',
        'enumerate', 'epsilon_one', 'error_model', 'event', 'event_above_alt', 'event_below_alt',
        'event_boolean_input', 'event_dynamic_pressure_above', 'event_dynamic_pressure_below',
        'event_fuel_percent_below', 'event_ground_distance', 'event_lifetime', 'event_lifetime_int_msec',
        'event_lifetime_int_nanosec', 'event_manual_input_button', 'event_manual_input_button_released',
        'event_manual_input_trigger', 'event_null', 'event_nx_above', 'event_nx_below', 'event_ny_above',
        'event_ny_below', 'event_nz_above', 'event_nz_below', 'event_output', 'event_pipe',
        'event_released_from_parent', 'event_static_pressure_above', 'event_static_pressure_below', 'event_timer',
        'event_timer_int_msec', 'event_timer_int_nanosec', 'execute', 'exhaust_velocity', 'expansion_time_constant',
        'expiration_time', 'extrapolate', 'false_target', 'false_target_screener', 'fidelity', 'fidelity_table',
        'field_of_view', 'file', 'file_path', 'filter', 'final_mass', 'final_radius', 'final_run_number',
        'final_semi_major_axis', 'finite', 'flaps', 'flaps_dcL_mach_table', 'flaps_dcd_mach_table', 'flight_controls',
        'flight_path_analysis', 'fluence_model', 'format', 'formation', 'forward_accel_max', 'forward_accel_min',
        'frame_rate', 'frame_time', 'frequency', 'frequency_maximum_rcs_table', 'fuel', 'fuel_feed', 'fuel_mass',
        'fuel_tank', 'fuel_transfer', 'fuse', 'fusion_method', 'gain_table', 'gear_compression_vector_x',
        'gear_compression_vector_y', 'gear_compression_vector_z', 'gear_extended_relative_position_x',
        'gear_extended_relative_position_y', 'gear_extended_relative_position_z', 'gear_rolling_vector_x',
        'gear_rolling_vector_y', 'gear_rolling_vector_z', 'generate_random_seeds', 'global_environment',
        'gravitational_parameter', 'gravity_model', 'grid', 'grid_data_file', 'ground_reaction_point', 'group',
        'guidance', 'guidance_autopilot_bank_to_turn', 'guidance_autopilot_skid_to_turn', 'guidance_config_file',
        'guidance_program_types', 'hardware_autopilot_bank_to_turn', 'hardware_autopilot_skid_to_turn', 'heading',
        'horizontal_coverage', 'horizontal_map', 'iff_mapping', 'ignore_friction', 'ignore_large_error_accum',
        'ignore_small_error_accum', 'image', 'inclination', 'include', 'include_once', 'independent_variable',
        'infrared_signature', 'inherent_contrast', 'inherit_controls', 'initial', 'initial_mass',
        'initial_run_number', 'inop_ref_area', 'integrator', 'intercept_maneuver', 'internal_link',
        'interpolation_interval', 'intersect_mesh', 'is_complete', 'is_contact_point', 'is_landing_gear',
        'is_nose_gear', 'isp_vs_alt', 'j2', 'jet', 'jet_engine_type', 'justify', 'kd', 'ki', 'kp',
        'kt_anti_windup_gain', 'land', 'landing_gear', 'latch_fuel_injection', 'lateral_middle_loop_rate_factor',
        'lateral_outer_loop_rate_factor', 'latitude', 'launch_computer', 'lead', 'line_of_sight_manager',
        'link16_interface', 'liquid_propellant_rocket', 'liquid_propellant_rocket_type', 'location', 'log',
        'log_file', 'longitude', 'loop', 'loop_after_table_end', 'low_pass_alpha', 'mach_range', 'maneuver',
        'maneuver_update_interval', 'maneuvering', 'manual_pilot_augmented_controls',
        'manual_pilot_augmented_stability', 'manual_pilot_simple_controls', 'map_p6dof_object_to_platform',
        'map_vehicle_to_platform', 'masking_pattern', 'mass', 'mass_properties', 'match_velocity_maneuver',
        'max_compression', 'max_error_accum', 'max_thrust_sealevel', 'max_thrust_vacuum', 'maximum_acceleration',
        'maximum_delta_time', 'maximum_delta_v', 'maximum_pitch_acceleration_mach_table', 'maximum_range',
        'maximum_roll_acceleration_mach_table', 'maximum_speed', 'maximum_yaw_acceleration_mach_table', 'mean_radius',
        'medium', 'member_platform', 'message_table', 'min_taxi_turn_radius', 'minimum_mover_timestep',
        'minimum_proportional_thrust', 'minimum_range', 'minimum_speed', 'missile_wez_parameters', 'mission_sequence',
        'model', 'model_list', 'moe', 'moment_of_inertia_ixx', 'moment_of_inertia_iyy', 'moment_of_inertia_izz',
        'motor', 'mover', 'multi_thread', 'multi_thread_update_interval', 'multi_thread_update_rate',
        'multi_threading', 'multiresolution_acoustic_signature', 'multiresolution_comm', 'multiresolution_fuel',
        'multiresolution_infrared_signature', 'multiresolution_mover', 'multiresolution_multirun_table',
        'multiresolution_optical_signature', 'multiresolution_processor', 'multiresolution_radar_signature',
        'multiresolution_sensor', 'natural_motion_circumnavigation', 'network', 'no_collision_check', 'noise_cloud',
        'nominal_height_above_ground_on_gear', 'non-realtime', 'normalized_spindown', 'normalized_spinup',
        'normalized_thrust_vs_alt', 'northern_intersection', 'number_dip', 'number_dipoles', 'number_of_threads',
        'nws_angle_control_surface_name', 'nws_enable_control_name', 'observer', 'off', 'offset', 'offset_ara',
        'offset_lla', 'on', 'on_complete', 'on_initialize', 'on_initialize2', 'on_platform_injection', 'on_update',
        'one_m2_detect_range', 'optical_reflectivity', 'optical_signature', 'optimize_cost', 'optimize_delta_v',
        'optimize_time', 'orbit', 'orbit_determination_fusion', 'orbital_maneuver_types',
        'orbital_propagator_commands', 'orientation', 'osm_traffic', 'output', 'p6dof_atmosphere', 'p6dof_gravity',
        'p6dof_integrator', 'p6dof_integrators', 'p6dof_object_type', 'p6dof_object_types', 'p6dof_terrain',
        'p6dof_wind', 'parcel_type', 'parent_rel_pitch', 'parent_rel_roll', 'parent_rel_x', 'parent_rel_y',
        'parent_rel_yaw', 'parent_rel_z', 'parking_spot', 'peak_gain', 'periapsis', 'periapsis_altitude', 'period',
        'pilot_manager', 'pitch_control_augmentation_factor_g', 'pitch_control_mapping_table', 'pitch_gload_max',
        'pitch_gload_min', 'pitch_rate_max', 'pitch_rate_min', 'pitch_stability_augmentation', 'pitch_trim_factor',
        'platform', 'platform_availability', 'platform_update_multiplier', 'poi', 'point_mass_engine_type',
        'point_mass_vehicle_type', 'position', 'post_processor', 'power', 'precision', 'preset', 'print',
        'print_mks_atmosphere_tables', 'process_priority', 'processor', 'propagation', 'propagation_model',
        'propagator', 'propellant_mass', 'propulsion_data', 'protocol', 'pulse_repetition_frequency', 'pulse_width',
        'pursue', 'quantitative_track_quality', 'quantity', 'raan', 'radar_signature', 'radial_color',
        'radial_offset_at_poca', 'radial_rate', 'radial_width', 'ramjet', 'ramjet_engine_type', 'random_seed',
        'random_seed_time', 'random_seeds', 'randomize_radar_frequencies', 'range_label_color', 'range_ring',
        'rated_thrust_ab', 'rated_thrust_idle', 'rated_thrust_mil', 'rcs', 'realtime', 'ref_area_sqft', 'reference',
        'reflectivity', 'reflectivity_delta', 'rel_pitch', 'rel_pos_x', 'rel_pos_y', 'rel_pos_z', 'rel_roll',
        'rel_yaw', 'relative_time', 'remove_sequencer', 'rendezvous_maneuver', 'repeat', 'repetitions',
        'reports_altitude', 'reports_bearing', 'reports_frequency', 'reports_location', 'reports_radial_velocity',
        'reports_range', 'reports_speed', 'reset_file_path', 'rigid_body_engine_type', 'rigid_body_vehicle_type',
        'ring_color', 'ring_width', 'road_traffic', 'roll_control_augmentation_factor_dps',
        'roll_control_mapping_table', 'roll_rate_max', 'roll_stability_augmentation',
        'roll_stabilizing_frequency_mach_table', 'roll_trim_factor', 'rolling_coefficient_of_friction',
        'roughness_factor', 'route', 'route_allowable_angle_error', 'route_network', 'router', 'router_protocol',
        'rudder_right', 'run', 'run_number_increment', 'scheduler_type', 'script', 'script_struct',
        'scuffing_coefficient_of_friction', 'sea_relaxation', 'sea_traffic', 'sea_wind_speed', 'section',
        'semi_major_axis', 'sensitivity', 'sensor', 'sensor_mode', 'sensor_plot', 'sensor_update_break_time',
        'sensor_update_multiplier', 'separation_omega_x', 'separation_omega_y', 'separation_omega_z', 'separation_vx',
        'separation_vy', 'separation_vz', 'sequencer', 'show_angle_labels', 'show_range_labels', 'side', 'sigma_zero',
        'sigmac', 'signal_processor', 'simdis_interface', 'simple_yaw_damper', 'simulation_name', 'six_dof_formation',
        'six_dof_object_types', 'six_dof_section', 'six_dof_unit', 'soil_moisture', 'soil_moisture_fraction',
        'solid_propellant_rocket', 'solid_propellant_rocket_type', 'sosm_interface', 'southern_intersection',
        'specific_impulse', 'spectrum_data', 'speed', 'speed_middle_loop_rate_factor', 'speed_outer_loop_rate_factor',
        'speed_range', 'speedbrake_dcd_mach_table', 'speedbrake_threshold', 'speedbrakes', 'spherical_map',
        'spin_down_ab_per_sec', 'spin_down_mil_per_sec', 'spin_down_table_ab_per_sec', 'spin_down_table_mil_per_sec',
        'spin_up_ab_per_sec', 'spin_up_mil_per_sec', 'spin_up_table_ab_per_sec', 'spin_up_table_mil_per_sec',
        'spoilers', 'spoilers_dcL_mach_table', 'spoilers_dcd_mach_table', 'spring_constant_lbs_per_ft', 'start_date',
        'start_epoch', 'start_time', 'start_time_now', 'state', 'statistic', 'std_flaps_down',
        'std_landing_gear_down', 'std_nose_wheel_steering', 'std_nws_enabled', 'std_nws_steering', 'std_rudder_right',
        'std_speed_brakes_out', 'std_spoilers_out', 'std_stick_back', 'std_stick_right', 'std_throttle_ab',
        'std_throttle_mil', 'std_thrust_reverser', 'std_thrust_vectoring_pitch', 'std_thrust_vectoring_roll',
        'std_thrust_vectoring_yaw', 'std_wheel_brake_left', 'std_wheel_brake_right', 'stddev_surface_height',
        'steering_control_surface_name', 'stick_back', 'stick_right', 'subobject', 'swap_axes', 'synthetic_pilot',
        'table', 'takeoff', 'target', 'target_maneuver', 'target_model', 'target_platform', 'taxi_speed_max_fps',
        'taxi_yaw_rate_max', 'term', 'terminal_velocity', 'terrain', 'terrain_conductivity',
        'terrain_dielectric_constant', 'terrain_scattering_coefficient', 'text', 'thermal_system', 'thread_count',
        'throttle_range', 'throttle_setting_ab', 'throttle_setting_mil', 'throttle_setting_pitch',
        'throttle_setting_reverser', 'throttle_setting_yaw', 'thrust', 'thrust_ab_alt_mach_table',
        'thrust_ab_mach_alt_table', 'thrust_alt_mach_table', 'thrust_idle_alt_mach_table',
        'thrust_idle_mach_alt_table', 'thrust_mil_alt_mach_table', 'thrust_mil_mach_alt_table', 'thrust_offset',
        'thrust_table_ab', 'thrust_table_idle', 'thrust_table_mil', 'time_to_poca', 'timing_method', 'tolerance',
        'top_level', 'total_mass', 'track', 'track_manager', 'transceiver', 'tsfc_ab_pph', 'tsfc_alt_mach_table',
        'tsfc_idle_pph', 'tsfc_mil_pph', 'turn_roll_in_multiplier', 'type', 'uci_component', 'uci_interface',
        'uncompressed_length', 'undefine_path_variable', 'unit', 'update_interval', 'use_constant_required_pd',
        'use_default_radar_frequencies', 'use_legacy_beta', 'use_legacy_data', 'use_legacy_derivatives',
        'use_native_terrain_masking', 'use_proportional_throttle', 'use_reduced_frequency', 'use_simple_yaw_damper',
        'vert_speed_max', 'vert_speed_min', 'vertical_coverage', 'vertical_map', 'vertical_middle_loop_rate_factor',
        'vertical_outer_loop_rate_factor', 'visual_elements', 'visual_part', 'warhead', 'water_temperature',
        'water_type', 'weapon', 'weapon_effects', 'weapon_tools', 'wgs84', 'width', 'wing_area_sqft', 'wing_chord_ft',
        'wing_span_ft', 'wsf_weapon_server', 'xio_interface', 'yaw_control_augmentation_factor_deg',
        'yaw_control_augmentation_factor_g', 'yaw_control_mapping_table', 'yaw_gload_max', 'yaw_rate_max',
        'yaw_stability_augmentation', 'yaw_trim_factor', 'zone', 'zone_set',
    }
)

TAXONOMY_PATH = Path(__file__).resolve().parent.parent / "docs" / "machine" / "error_taxonomy_v1.json"

# Verified WSF_ types extracted from AFSIM 2.9.0 demo scripts that pass mission.exe.
VALID_WSFS = {
    "WSF_PLATFORM", "WSF_BRAWLER_PLATFORM", "WSF_GROUP",
    "WSF_AIR_MOVER", "WSF_KINEMATIC_MOVER", "WSF_GUIDED_MOVER",
    "WSF_GROUND_MOVER", "WSF_BRAWLER_MOVER", "WSF_SIX_DOF_MOVER",
    "WSF_FIRES_MOVER", "WSF_STRAIGHT_LINE_MOVER", "WSF_OFFSET_MOVER",
    "WSF_POINT_MASS_SIX_DOF_MOVER", "WSF_UNGUIDED_MOVER",
    "WSF_INTEGRATING_SPACE_MOVER", "WSF_OLD_GUIDED_MOVER", "WSF_AERO",
    "WSF_RADAR_SENSOR", "WSF_ESM_SENSOR", "WSF_EOIR_SENSOR",
    "WSF_GEOMETRIC_SENSOR", "WSF_SAR_SENSOR", "WSF_IRST_SENSOR",
    "WSF_ACOUSTIC_SENSOR", "WSF_LASER_TRACKER", "WSF_RF_JAMMER",
    "WSF_SCRIPT_PROCESSOR", "WSF_TRACK_PROCESSOR", "WSF_TASK_PROCESSOR",
    "WSF_BRAWLER_PROCESSOR", "WSF_SA_PROCESSOR",
    "WSF_QUANTUM_TASKER_PROCESSOR", "WSF_THREAT_PROCESSOR",
    "WSF_PERCEPTION_PROCESSOR", "WSF_PERFECT_TRACKER",
    "WSF_KALMAN_FILTER", "WSF_ALPHA_BETA_FILTER",
    "WSF_LINKED_PROCESSOR", "WSF_IMAGE_PROCESSOR",
    "WSF_DIRECTION_FINDER_PROCESSOR", "WSF_RIPR_PROCESSOR",
    "WSF_WEAPON_TRACK_PROCESSOR", "WSF_STATE_MACHINE",
    "WSF_FT_SCREENER", "WSF_SIMPLE_SENSORS_MANAGER",
    "WSF_SENSORS_MANAGER_FOV", "WSF_WEAPONS_MANAGER_SAM",
    "WSF_WEAPONS_MANAGER_AI", "WSF_UPLINK_PROCESSOR",
    "WSF_UNCLASS_DISSEMINATE_C", "WSF_UNCLASS_BM",
    "WSF_UNCLASS_ASSET_MANAGER", "WSF_SCRIPT_LAUNCH_COMPUTER",
    "WSF_EXPLICIT_WEAPON", "WSF_IMPLICIT_WEAPON",
    "WSF_AIR_TO_AIR_MISSILE", "WSF_CHAFF_WEAPON",
    "WSF_GRADUATED_LETHALITY", "WSF_SPHERICAL_LETHALITY",
    "WSF_AIR_TARGET_FUSE", "WSF_GROUND_TARGET_FUSE",
    "WSF_WEAPON_FUSE", "WSF_GUIDANCE_COMPUTER",
    "WSF_AIR_TO_AIR_LAUNCH_COMPUTER", "WSF_ATG_LAUNCH_COMPUTER",
    "WSF_ATA_LAUNCH_COMPUTER", "WSF_FIRES_LAUNCH_COMPUTER",
    "WSF_OLD_GUIDANCE_COMPUTER", "WSF_BALLISTIC_MISSILE_LAUNCH_COMPUTER",
    "WSF_COMM_TRANSCEIVER", "WSF_COMM_XMTR", "WSF_COMM_RCVR",
    "WSF_COMM_ROUTER", "WSF_RADIO_TRANSCEIVER", "WSF_RADIO_XMTR",
    "WSF_RADIO_RCVR", "WSF_COMM_ROUTER_PROTOCOL_AD_HOC",
    "WSF_COMM_NETWORK_AD_HOC", "WSF_TRACK_MESSAGE", "WSF_CONTROL_MESSAGE",
    "WSF_ASSET_MESSAGE", "WSF_TRACK_DROP_MESSAGE", "WSF_TRACK_NOTIFY_MESSAGE",
    "WSF_ELECTRONIC_ATTACK", "WSF_ELECTRONIC_PROTECT",
    "WSF_EA_TECHNIQUE", "WSF_EP_TECHNIQUE", "WSF_SLB_EFFECT",
    "WSF_SLC_EFFECT", "WSF_RPJ_EFFECT", "WSF_FALSE_TARGET_EFFECT",
    "WSF_FALSE_TARGET", "WSF_JAMMER_POWER_EFFECT", "WSF_POWER_EFFECT",
    "WSF_AGILITY_EFFECT", "WSF_TRACK_EFFECT", "WSF_COVER_PULSE_EFFECT",
    "WSF_PULSE_SUPPRESS_EFFECT", "WSF_SIMPLE_FT_EFFECT", "WSF_POL_MOD_EFFECT",
    "WSF_CYBER_ATTACK", "WSF_CYBER_PROTECT", "WSF_CYBER_SCRIPT_EFFECT",
    "WSF_CYBER_DETONATE_EFFECT", "WSF_CYBER_MAN_IN_THE_MIDDLE_EFFECT",
    "WSF_CYBER_CONSTRAINT", "WSF_FUEL", "WSF_BRAWLER_FUEL",
    "WSF_TABULAR_RATE_FUEL", "WSF_RADAR_SIGNATURE", "WSF_LASER_DESIGNATOR",
    "WSF_CHAFF_PARCEL", "WSF_TRACK_MANAGER",
}


def load_taxonomy():
    raw = TAXONOMY_PATH.read_text(encoding="utf-8-sig")
    taxonomy = json.loads(raw)
    categories = taxonomy.get("categories", [])
    by_id = {item["id"]: item for item in categories}

    syntax_ids = {
        item["id"] for item in categories if item.get("affects_syntax", False)
    } or DEFAULT_SYNTAX_ERROR_IDS
    static_blocking_ids = {
        item["id"] for item in categories if item.get("blocks_static_pass", False)
    } or DEFAULT_STATIC_BLOCKING_ERROR_IDS

    return taxonomy, by_id, frozenset(syntax_ids), frozenset(static_blocking_ids)


ERROR_TAXONOMY, ERROR_TAXONOMY_BY_ID, SYNTAX_ERROR_IDS, STATIC_BLOCKING_ERROR_IDS = load_taxonomy()


def make_finding(error_id: str, line: int, message: str) -> dict:
    return {"error_id": error_id, "line": line, "message": message}


def build_block(head, parts, line_no):
    if head == "edit" and len(parts) >= 2 and parts[1] in EDITABLE_BLOCKS:
        head = parts[1]
        parts = [head, *parts[2:]]

    if head == "platform_type":
        wsf_type = parts[2] if len(parts) >= 3 else ""
    elif head == "network":
        wsf_type = parts[2] if len(parts) >= 3 else ""
    elif head == "mover":
        wsf_type = parts[1] if len(parts) >= 2 else ""
    elif head in {"sensor", "weapon", "processor", "comm", "launch_computer"}:
        wsf_type = parts[2] if len(parts) >= 3 else ""
    else:
        wsf_type = ""

    return {
        "kind": head,
        "line": line_no,
        "name": parts[1] if len(parts) >= 2 else "",
        "wsf_type": wsf_type,
        "has_transmitter": False,
        "has_constant_pattern": False,
    }


def find_enclosing_block(stack, kind):
    for block in reversed(stack):
        if block["kind"] == kind:
            return block
    return None


def check_units(lines):
    errors = []
    unit_pattern = re.compile(
        r"\b(m/sec|km/hr|knots|sec|min|hr|m|km|ft|fps|nm|deg|rad|g|ghz|mhz|khz|hz|kw|db|msl|agl)\b",
        re.IGNORECASE,
    )
    numeric_pattern = re.compile(r"^-?\d+(\.\d+)?([eE][+-]?\d+)?$")
    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if parts and parts[0] in UNIT_COMMANDS:
            tokens = parts[1:]
            if not tokens:
                errors.append((line_no, "numeric argument missing value"))
                continue
            if any(token.lower() == "microsec" for token in tokens):
                errors.append((line_no, "unsupported unit microsec"))
                continue
            if numeric_pattern.match(tokens[0]) and not unit_pattern.search(" ".join(tokens[1:])):
                errors.append((line_no, "numeric argument missing unit"))
                continue
            if parts[0] == "maximum_speed" and numeric_pattern.match(tokens[0]) and float(tokens[0]) <= 0:
                errors.append((line_no, "maximum_speed must be greater than 0"))
    return errors


def has_inline_block_close(head: str, parts: list[str]) -> bool:
    if head == "edit" and len(parts) >= 2 and parts[1] in EDITABLE_BLOCKS:
        return f"end_{parts[1]}" in parts[2:]
    if head not in BLOCK_STARTS:
        return False
    return BLOCK_STARTS[head] in parts[1:]


def is_block_start(head, parts, stack):
    if head == "edit" and len(parts) >= 2 and parts[1] in EDITABLE_BLOCKS:
        return not has_inline_block_close(head, parts)
    if head not in BLOCK_STARTS:
        return False
    if head == "antenna_pattern":
        if stack and stack[-1]["kind"] in ANTENNA_REFERENCE_PARENTS:
            return False
    if has_inline_block_close(head, parts):
        return False
    return True


def check_blocks(lines):
    stack = []
    errors = []
    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        head = parts[0]
        if is_block_start(head, parts, stack):
            stack.append(build_block(head, parts, line_no))
        elif head in END_TO_START:
            if not stack:
                errors.append((line_no, f"unexpected {head}"))
                continue
            expected_block = stack.pop()
            expected_end = BLOCK_STARTS[expected_block["kind"]]
            if head != expected_end:
                errors.append((line_no, f"{head} closes {expected_block['kind']} from line {expected_block['line']}"))
    for block in stack:
        errors.append((block["line"], f"missing {BLOCK_STARTS[block['kind']]}"))
    return errors


def extract_defined_symbols(lines):
    platform_types = set()
    antenna_patterns = {}
    comm_definitions = set()
    advanced_behaviors = set()
    stack = []

    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        head = parts[0]

        if is_block_start(head, parts, stack):
            block = build_block(head, parts, line_no)
            stack.append(block)
            if head == "platform_type" and block["name"]:
                platform_types.add(block["name"])
            elif head == "antenna_pattern" and block["name"]:
                antenna_patterns[block["name"]] = line_no
            elif head == "comm" and not stack[:-1] and block["name"]:
                comm_definitions.add(block["name"])
            elif head == "advanced_behavior" and block["name"]:
                advanced_behaviors.add(block["name"])
            continue

        if head in END_TO_START and stack:
            stack.pop()

    return platform_types, antenna_patterns, comm_definitions, advanced_behaviors


def script_has_external_includes(lines):
    for raw in lines:
        line = raw.strip()
        if line.startswith("include ") or line.startswith("include_once "):
            return True
    return False


@lru_cache(maxsize=1)
def _repo_file_name_index():
    roots = [
        ROOT / "benchmarks" / "benchmark_v1" / "demo_sources",
        ROOT / "references",
        ROOT / "docs",
    ]
    index = {}
    for base in roots:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file():
                index.setdefault(path.name.lower(), []).append(path)
    return index


def resource_exists(resource_path: str, script_label: str) -> bool:
    if not resource_path:
        return False

    candidate = Path(resource_path.strip().strip('"'))
    if candidate.exists():
        return True

    if script_label:
        script_path = Path(script_label)
        if script_path.exists():
            local_candidate = script_path.parent / candidate
            if local_candidate.exists():
                return True
            if "demo_sources" in script_path.parts:
                return candidate.name.lower() in _repo_file_name_index()

    return False


def check_references(lines):
    platform_types, antenna_patterns, comm_definitions, advanced_behaviors = extract_defined_symbols(lines)
    errors = []
    stack = []
    local_only_validation = not script_has_external_includes(lines)

    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        head = parts[0]

        if is_block_start(head, parts, stack):
            if local_only_validation and head == "comm" and len(parts) >= 3:
                current_kind = stack[-1]["kind"] if stack else ""
                # Named comm definitions / references are validated in type-style
                # declaration contexts. Platform instances may legitimately use
                # instance-control forms such as "comm link on".
                if current_kind in {"platform_type", "weapon"}:
                    comm_type = parts[2]
                    if not comm_type.startswith("WSF_") and comm_type not in comm_definitions:
                        errors.append((line_no, f"unknown comm definition {comm_type}"))
            stack.append(build_block(head, parts, line_no))
            continue

        if head in END_TO_START:
            if stack:
                stack.pop()
            continue

        current_kind = stack[-1]["kind"] if stack else ""

        if head == "platform" and len(parts) >= 3 and parts[2] not in platform_types:
            errors.append((line_no, f"undefined platform type {parts[2]}"))

        if local_only_validation and head == "comm" and len(parts) >= 3 and current_kind in {"platform_type", "weapon"}:
            comm_type = parts[2]
            if not comm_type.startswith("WSF_") and comm_type not in comm_definitions:
                errors.append((line_no, f"unknown comm definition {comm_type}"))

        if head == "antenna_pattern" and len(parts) >= 2 and current_kind in ANTENNA_REFERENCE_PARENTS:
            if parts[1] not in antenna_patterns:
                errors.append((line_no, f"undefined antenna pattern {parts[1]}"))

        if local_only_validation and head == "behavior_node" and len(parts) >= 2 and find_enclosing_block(stack, "advanced_behavior_tree") is not None:
            if parts[1] not in advanced_behaviors:
                errors.append((line_no, f"unknown advanced_behavior {parts[1]}"))

    return errors


def check_external_resources(lines, script_label: str):
    errors = []
    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        # aero_file appears as a sub-command inside mover, not at line start
        for i, token in enumerate(parts):
            if token == "aero_file" and i + 1 < len(parts) and not resource_exists(parts[i + 1], script_label):
                errors.append((line_no, f"missing external resource {parts[i + 1]}"))
                break
    return errors


def check_coordinates(lines):
    errors = []
    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line.startswith("position "):
            continue
        if "altitude" in line:
            if not re.search(r"\b\d+(\.\d+)?\s+(m|ft)\s+(msl|agl)\b", line):
                errors.append((line_no, "invalid altitude format"))
        else:
            parts = line.split()
            if len(parts) < 3:
                errors.append((line_no, "position too short"))
        if not (
            re.search(r"\b\d+(\.\d+)?[ns]\b", line.lower())
            and re.search(r"\b\d+(\.\d+)?[ew]\b", line.lower())
        ):
            if not re.search(r"position\s+-?\d+(\.\d+)?\s+-?\d+(\.\d+)?\s+-?\d+(\.\d+)?", line.lower()):
                errors.append((line_no, "invalid coordinate format"))
    return errors


def check_hallucinated_types(lines):
    errors = []
    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        for token in line.split():
            if token.startswith("WSF_") and token not in VALID_WSFS:
                errors.append((line_no, f"unknown or ungrounded type {token}"))
    return errors


def check_required_fields(lines):
    text = "\n".join(lines)
    errors = []
    if "end_time" not in text:
        errors.append((0, "missing end_time"))
    if "platform " in text and "route" not in text and "position " not in text:
        errors.append((0, "platforms missing route or position"))
    return errors


def check_top_level_requirements(lines):
    findings = []
    stack = []

    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split()
        head = parts[0]

        if is_block_start(head, parts, stack):
            stack.append(build_block(head, parts, line_no))
            continue

        if head in END_TO_START:
            if stack:
                stack.pop()
            continue

        if head == "end_time" and stack:
            findings.append(make_finding("E007", line_no, "end_time must appear at top level, not inside another block"))

    return findings


def check_script_language(lines):
    errors = []
    text = "\n".join(lines)
    if "cout <<" in text:
        errors.append((0, "unsupported cout"))
    if re.search(r"\?.*:", text):
        errors.append((0, "unsupported ternary operator"))
    if "fmod(" in text:
        errors.append((0, "unsupported fmod"))

    # Mission-verified API shape guards for script-processor code.
    # Sources:
    # - benchmark_v1/demo_sources/example_scripts/proc_mover_demo.txt
    # - benchmark_v1/demo_sources/*/brawler_script_util*.txt
    # - mission.exe compile diagnostics from BV1-021
    #
    # Verified good forms in the corpus are instance-style:
    #   direction.Normalize();
    #   direction.Scale(myDist);
    #   WsfGeoPoint.Construct(...)
    #   WsfGeoPoint().Construct(...)
    #
    # Rejected runtime forms include:
    #   Vec3.Normalize(direction)
    #   Vec3.Scale(deltaPos, myDist)
    #   a.LLA()
    stack = []
    in_script_context = False

    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line:
            continue

        parts = line.split()
        head = parts[0]

        if head in BLOCK_STARTS:
            stack.append(head)
            if head in _SCRIPT_CONTAINER_BLOCKS:
                in_script_context = True
            # Still allow same-line checks for compact script statements after block starts.
        elif head in END_TO_START:
            if stack:
                closed = stack.pop()
                if closed in _SCRIPT_CONTAINER_BLOCKS:
                    in_script_context = any(block in _SCRIPT_CONTAINER_BLOCKS for block in stack)
            continue

        if "PLATFORM_NAME" in line:
            errors.append((line_no, "unsupported script identifier PLATFORM_NAME; use PLATFORM.Name() or remove the script block"))

        if not in_script_context:
            continue

        if re.search(r"\bVec3\.Normalize\s*\(", line):
            errors.append(
                (
                    line_no,
                    "unsupported script API form Vec3.Normalize(...); use the verified instance-style vector normalization pattern from the official demos",
                )
            )
        if re.search(r"\bVec3\.Scale\s*\(", line):
            errors.append(
                (
                    line_no,
                    "unsupported script API form Vec3.Scale(...); use the verified instance-style vector scaling pattern from the official demos",
                )
            )
        if re.search(r"\.\s*LLA\s*\(", line):
            errors.append(
                (
                    line_no,
                    "unsupported script API call .LLA(); use a verified WsfGeoPoint construction pattern from the official demos instead",
                )
            )

    return errors


# Blocks that contain script / C++ code — anything inside them is not an AFSIM command.
_SCRIPT_CONTAINER_BLOCKS = {
    "script_interface", "script", "script_variables",
    "on_initialize", "on_update", "on_initialize2",
    "processor", "behavior_tree", "advanced_behavior_tree", "advanced_behavior",
}

# Supplementary AFSIM commands verified in project demo sources and documentation
# that are not in the official command index. Source: benchmark_v1/demo_sources/,
# references/sensor_types_reference.md, project SKILL.md.
_DEMO_VERIFIED_COMMANDS = {
    # Sensor commands (radar, ESM, acoustic)
    "ignore_same_side", "mode_template", "detection_probability",
    "reports_range_rate", "reports_elevation", "reports_velocity",
    "reports_signal_to_noise", "reports_side", "scan_mode", "beamwidth", "antenna_height",
    "beam_tilt", "frequency_band", "pulse_density", "noise_power",
    "required_pd", "slew_mode", "azimuth_scan_limits", "elevation_scan_limits",
    "azimuth_slew_limits", "hits_to_establish_track", "hits_to_maintain_track",
    "minimum_gain", "pulse_repetition_interval", "probability_of_false_alarm",
    "swerling_case", "track_quality", "purge_interval", "evaluation_interval",
    "internal_loss", "mode", "freq", "mach",
    # Fuse / weapon commands
    "radius_and_pk",
    # Platform commands
    "launched_platform_type", "commander", "icon", "enable",
    "category", "report_to", "network_name", "technique", "effect",
    "command_chain", "variable", "values", "precondition",
    "flight_id", "next_state", "reason",
    # Brawler commands
    "salvo_interval",
    # Other verified commands
    "script_debug_writes", "on_init",
}


def check_unknown_commands(lines):
    """Flag tokens that look like AFSIM commands but aren't in the known-valid whitelist.

    Skips checking inside blocks that contain script/C++ code (processor bodies,
    behavior trees, event handlers), where arbitrary C++ tokens are expected.

    These slip past the static checker because they aren't block-starts or WSF_ types,
    but mission.exe will reject them. Examples from real runs:
    "alternate_locations", "start_date" (misused), "function", "demo_effect".
    """
    findings = []
    _value_pattern = re.compile(
        r"^\d+\.?\d*$|"
        r"^\d+\.?\d*\s+\D|"
        r"^\d{1,2}[ns]\s|"
        r"^\d{1,2}:\d|"
        r"^[A-Z_]+$|"
        r"^\"|"
        r"^//"
    )
    _script_lang_kw = {
        "if", "else", "elseif", "endif", "for", "while", "foreach",
        "return", "break", "continue", "double", "int", "bool", "string",
        "void", "class", "struct", "enum", "new", "delete", "switch",
        "case", "default", "try", "catch", "throw", "const", "static",
        "virtual", "public", "private", "protected", "true", "false",
        "null", "nullptr", "this", "auto", "extern", "typedef", "namespace",
        "using", "template", "include", "printf", "sprintf", "fprintf",
        "cout", "cin", "cerr", "endl",
    }
    _extended_whitelist = KNOWN_AFSIM_TOKENS | _DEMO_VERIFIED_COMMANDS

    stack = []  # block stack to track script containers
    in_script_context = False

    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        parts = line.split()
        head = parts[0]

        # Track block stack to know when inside script containers
        if head in BLOCK_STARTS:
            stack.append(head)
            if head in _SCRIPT_CONTAINER_BLOCKS:
                in_script_context = True
            continue
        if head in END_TO_START:
            if stack:
                closed = stack.pop()
                if closed in _SCRIPT_CONTAINER_BLOCKS:
                    # Re-evaluate: are we still inside a script container?
                    in_script_context = any(b in _SCRIPT_CONTAINER_BLOCKS for b in stack)
            continue
        if in_script_context:
            continue

        # Skip known tokens (official + demo-verified)
        if head in _extended_whitelist:
            continue
        # Auto-accept end_xxx variants
        if head.startswith("end_") and head[4:] in _extended_whitelist:
            continue
        # Skip WSF_ types
        if head.startswith("WSF_"):
            continue
        # Skip script-language keywords
        if head in _script_lang_kw:
            continue
        # Skip values (numbers, coordinates, strings)
        if _value_pattern.match(line):
            continue
        # Skip bare names (platform/component references, identifiers that look like AFSIM names)
        if re.match(r"^[a-zA-Z_][\w.]*$", head) and len(parts) >= 2:
            # Programming-language keywords that are NOT valid AFSIM commands
            if head in {"function", "end_function", "var", "let", "const", "return", "for", "while",
                         "class", "import", "export", "def", "lambda", "async", "await", "try",
                         "catch", "throw", "switch", "case", "break", "continue", "new", "delete",
                         "void", "typeof", "instanceof"}:
                findings.append(make_finding("E007", line_no, f"programming keyword used as AFSIM command: {head}"))
                continue
            # Could be a platform instance name, component reference, etc.
            continue

        findings.append(make_finding("E007", line_no, f"unknown command: {head}"))
    return findings


def check_component_syntax(lines):
    findings = []
    stack = []

    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split()
        head = parts[0]
        current_kind = stack[-1]["kind"] if stack else ""
        current_sensor = find_enclosing_block(stack, "sensor")
        current_mover = find_enclosing_block(stack, "mover")

        if is_block_start(head, parts, stack):
            if head == "route" and current_kind != "platform":
                findings.append(make_finding("E007", line_no, "route block must be nested under platform"))
            if head == "constant_pattern" and current_kind != "antenna_pattern":
                findings.append(make_finding("E007", line_no, "constant_pattern must be nested under antenna_pattern"))
            if head == "network" and len(parts) < 3:
                findings.append(make_finding("E007", line_no, "network block must declare a backing WSF_* type"))
            if head == "processor" and len(parts) >= 3 and parts[2] in CYBER_EFFECT_TYPES:
                findings.append(make_finding("E007", line_no, f"{parts[2]} is a cyber_effect type, not a processor type"))
            if head == "weapon" and len(parts) >= 3 and parts[2] == "WSF_AIR_TO_AIR_MISSILE":
                findings.append(
                    make_finding(
                        "E007",
                        line_no,
                        "WSF_AIR_TO_AIR_MISSILE cannot be used directly as a standalone weapon block type; use a self-contained explicit weapon profile or omit the weapon block",
                    )
                )
            if current_kind == "weapon" and head in {"mover"}:
                findings.append(make_finding("E007", line_no, f"{head} is not a valid nested block inside weapon blocks in this project corpus"))

            block = build_block(head, parts, line_no)
            host_rule = get_wsf_type_rule(block["wsf_type"])
            if host_rule and block["kind"] not in set(host_rule.get("allowed_block_kinds", [])):
                allowed = ", ".join(host_rule.get("allowed_block_kinds", [])) or "documented host blocks"
                preferred = host_rule.get("preferred_declaration", "")
                message = f"{block['wsf_type']} is valid but cannot be declared as {block['kind']}; allowed host blocks: {allowed}"
                if preferred:
                    message += f"; preferred form: {preferred}"
                findings.append(make_finding("E007", line_no, message))

            # Dynamic command-context check from afsim_context_rules_v1.json.
            cmd_rule = get_command_context_rule(head)
            if cmd_rule and current_kind not in set(cmd_rule.get("allowed_parent_blocks", [])):
                allowed = " | ".join(cmd_rule.get("allowed_parent_blocks", []))
                findings.append(make_finding("E007", line_no, cmd_rule.get("message", f"{head} must be nested under {allowed}")))

            if head == "transmitter" and current_sensor is not None:
                current_sensor["has_transmitter"] = True
            if head == "constant_pattern":
                antenna_block = find_enclosing_block(stack, "antenna_pattern")
                if antenna_block is not None:
                    antenna_block["has_constant_pattern"] = True
            # Ejector must be inside a chaff weapon (source: mission.exe "Chaff ejectors can only be added to chaff weapons")
            # Ejector host check: multi-line ejector blocks land here.
            if head == "ejector" and current_kind == "weapon":
                weapon_block = find_enclosing_block(stack, "weapon")
                if weapon_block and weapon_block.get("wsf_type") != "WSF_CHAFF_WEAPON":
                    findings.append(make_finding("E007", line_no, "ejector is only valid inside a weapon WSF_CHAFF_WEAPON block"))

            stack.append(block)
            # Track Brawler companion components on platform_type
            if current_kind == "platform_type":
                parent_pt = find_enclosing_block(stack, "platform_type")
                if parent_pt and parent_pt.get("wsf_type") == "WSF_BRAWLER_PLATFORM":
                    if head == "mover" and block.get("wsf_type") == "WSF_BRAWLER_MOVER":
                        parent_pt["has_brawler_mover"] = True
                    if head == "processor" and block.get("wsf_type") == "WSF_THREAT_PROCESSOR":
                        parent_pt["has_threat_processor"] = True
            continue

        if head in END_TO_START:
            if stack:
                closed = stack.pop()
                if closed["kind"] == "sensor" and closed["wsf_type"] == "WSF_RADAR_SENSOR" and not closed["has_transmitter"]:
                    findings.append(make_finding("E007", closed["line"], "WSF_RADAR_SENSOR missing transmitter block"))
                # Passive/ESM sensors need frequency bands (source: mission.exe "No frequency bands defined for passive sensor")
                if closed["kind"] == "sensor" and closed["wsf_type"] in ("WSF_ESM_SENSOR", "WSF_ACOUSTIC_SENSOR") and not closed.get("has_frequency_band"):
                    findings.append(make_finding("E007", closed["line"], f"{closed['wsf_type']} missing frequency_band or mode definition"))
                if closed["kind"] == "antenna_pattern" and not closed["has_constant_pattern"]:
                    findings.append(make_finding("E007", closed["line"], "antenna_pattern missing constant_pattern block"))
                # Brawler platform_type companion rules (source: mission.exe crash analysis)
                if closed["kind"] == "platform_type" and closed.get("wsf_type") == "WSF_BRAWLER_PLATFORM":
                    if not closed.get("has_brawler_mover"):
                        findings.append(make_finding("E007", closed["line"], "WSF_BRAWLER_PLATFORM requires mover WSF_BRAWLER_MOVER"))
                    if not closed.get("has_threat_processor"):
                        findings.append(make_finding("E007", closed["line"], "WSF_BRAWLER_PLATFORM requires processor WSF_THREAT_PROCESSOR"))
            continue

        if head in SUBCOMPONENT_PSEUDO_KEYWORDS:
            findings.append(make_finding("E007", line_no, f"{head} is a pseudo keyword and cannot be used as a standalone command"))

        if head in UNSUPPORTED_STANDALONE_COMMANDS:
            findings.append(make_finding("E007", line_no, UNSUPPORTED_STANDALONE_COMMANDS[head]))

        if head in UNSUPPORTED_DIRECTIVES:
            findings.append(make_finding("E007", line_no, UNSUPPORTED_DIRECTIVES[head]))

        expected_parent = NESTED_ONLY_KEYWORDS.get(head)
        if expected_parent and current_kind != expected_parent:
            findings.append(make_finding("E007", line_no, f"{head} must be nested under {expected_parent}"))

        if head == "antenna_pattern" and len(parts) >= 2 and current_kind not in ANTENNA_REFERENCE_PARENTS:
            findings.append(make_finding("E007", line_no, "antenna_pattern reference must be nested under transmitter or receiver"))

        if current_mover is not None and current_mover["wsf_type"] == "WSF_AIR_MOVER" and head in AIR_MOVER_UNSUPPORTED_COMMANDS:
            findings.append(make_finding("E007", line_no, f"{head} is not supported by WSF_AIR_MOVER"))

        # Track sensor frequency_band / mode for passive/ESM sensor validation
        if current_sensor is not None and head in ("frequency_band", "mode"):
            current_sensor["has_frequency_band"] = True

        if current_sensor is not None and current_sensor["wsf_type"] == "WSF_ACOUSTIC_SENSOR" and head == "mode":
            findings.append(
                make_finding(
                    "E007",
                    line_no,
                    "mode is not validated inside WSF_ACOUSTIC_SENSOR in this project corpus and fails mission.exe in current benchmark runs",
                )
            )

        if current_kind == "weapon" and head in {"guidance", "fuse", "lethality"}:
            findings.append(make_finding("E007", line_no, f"{head} is not a valid nested command inside weapon blocks in this project corpus"))

        # Ejector host check (source: mission.exe "Chaff ejectors can only be added to chaff weapons").
        # Inline ejector blocks (ejector ... end_ejector on one line) are skipped by is_block_start,
        # so we check here in the content-command section.
        if head == "ejector" and current_kind == "weapon":
            weapon_block = find_enclosing_block(stack, "weapon")
            if weapon_block and weapon_block.get("wsf_type") != "WSF_CHAFF_WEAPON":
                findings.append(make_finding("E007", line_no, "ejector is only valid inside a weapon WSF_CHAFF_WEAPON block"))

        # Mover-only commands appearing outside a mover block (source: wsf_air_mover.html et al.)
        if head in MOVER_ONLY_COMMANDS and current_mover is None:
            findings.append(make_finding("E007", line_no, f"{head} is only valid inside a mover block, not at {current_kind or 'top'} level"))

    return findings


def static_analysis(script_text: str, script_label: str = ""):
    lines = script_text.splitlines()
    findings = []

    mapping = {
        "E001": check_units(lines),
        "E002": check_blocks(lines),
        "E003": check_references(lines),
        "E004": check_coordinates(lines),
        "E005": check_hallucinated_types(lines),
        "E006": check_required_fields(lines),
        "E009": check_external_resources(lines, script_label),
        "E008": check_script_language(lines),
    }

    for error_id, items in mapping.items():
        for line_no, message in items:
            findings.append(make_finding(error_id, line_no, message))

    findings.extend(check_component_syntax(lines))
    findings.extend(check_top_level_requirements(lines))
    findings.extend(check_unknown_commands(lines))
    return findings


def analyze_script_text(script_text: str, script_label: str = "") -> dict:
    findings = static_analysis(script_text, script_label=script_label)
    static_error_ids = sorted({item["error_id"] for item in findings})
    primary_error = findings[0]["error_id"] if findings else ""

    return {
        "script": script_label,
        "syntax_correct": not any(item["error_id"] in SYNTAX_ERROR_IDS for item in findings),
        "static_pass": not any(item["error_id"] in STATIC_BLOCKING_ERROR_IDS for item in findings),
        "primary_error": primary_error,
        "static_error_ids": static_error_ids,
        "findings": findings,
    }


def read_script(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def check_script(path: Path) -> dict:
    return analyze_script_text(read_script(path), script_label=str(path))


def collect_scripts(inputs: list[Path], recursive: bool) -> list[Path]:
    scripts = []
    for item in inputs:
        if item.is_file():
            scripts.append(item)
        elif item.is_dir():
            pattern = "**/*.txt" if recursive else "*.txt"
            scripts.extend(sorted(item.glob(pattern)))
    return sorted(dict.fromkeys(scripts))


def build_summary(results: list[dict]) -> dict:
    total = len(results)
    syntax_correct = sum(1 for row in results if row["syntax_correct"])
    static_pass = sum(1 for row in results if row["static_pass"])
    error_counter = Counter()
    for row in results:
        for error_id in row["static_error_ids"]:
            error_counter[error_id] += 1

    return {
        "total": total,
        "syntax_correct": syntax_correct,
        "static_pass": static_pass,
        "syntax_correct_rate": round(syntax_correct / total, 4) if total else 0.0,
        "static_pass_rate": round(static_pass / total, 4) if total else 0.0,
        "error_counts": dict(sorted(error_counter.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Static Checker v1 on AFSIM .txt scripts.")
    parser.add_argument("inputs", nargs="+", type=Path, help="Script file(s) or directory path(s).")
    parser.add_argument("--recursive", action="store_true", help="Scan directories recursively for *.txt files.")
    parser.add_argument("--summary-only", action="store_true", help="Only print aggregate summary JSON.")
    parser.add_argument("--fail-on-findings", action="store_true", help="Exit with code 1 when any static finding exists.")
    args = parser.parse_args()

    scripts = collect_scripts(args.inputs, args.recursive)
    results = [check_script(path) for path in scripts]
    payload = build_summary(results) if args.summary_only else {"summary": build_summary(results), "results": results}

    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if args.fail_on_findings and any(row["findings"] for row in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
