"""Affirmative policies only for isolated integration fixtures, never approved templates."""
def fixture_policies(payload):
    rationale='Isolated assignment/source integration fixture; no participant preparation is prescribed or claimed.'
    payload['study']['preparation_policy']=[dict(occasion_key=o['key'],placement='before_baseline',demonstration_required=False,acknowledgement_required=False,comprehension=[],practice=[],rationale=rationale) for o in payload['study']['occasions']]
    payload['study']['repeat_policy']=dict(permitted_causes=['intentional_repeat','withdrawal','operator_stop','hardware_failure','software_failure','planned_interruption','unknown','participant_stop','technical_failure','lost_connection','other'],max_attempts=20,selection='explicit',rationale='Retain explicit repeats in this isolated lifecycle fixture.')
    payload['study']['interruption_policy']=dict(available_outcomes='retain_available',rationale='Retain observable fixture evidence without analysis eligibility claims.')
    payload['analysis']['eligibility_policy']=dict(repeat_selection='explicit',incomplete_denominator='assigned',missing_handling='exclude_outcome',source_requirement='report_status',physical_requirement='report_status',human_calibration_requirement='report_status',participant_preparation_requirement='report_status',protocol_requirement='report_status',configuration_pooling='identical_only',pooling_review=None,hcf_enabled=False,hcf_screen_keys=[],hcf_attempt_selection='explicit',rationale='No scientific analysis is executed by this integration fixture.')
    return payload
