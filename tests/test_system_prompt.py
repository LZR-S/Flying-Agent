import re

import pytest

from drone_agent.context import SYSTEM
from drone_agent.protocol import TOOL_HELP

HELP = ' '.join(TOOL_HELP.values())

# Global principles that no single tool description carries.
SYSTEM_RULES = {
    'one tool per turn': r'exactly one',
    'camera profile': r'960x720',
    'no hidden sensing': r'no .*gimbal.*detector',
    'honest capability limits': r'capability limits honestly',
    'automatic observations': r'automatically supplies',
    'dashed viewfinder boundaries': r'dashed',
    'annotations are not scene objects': r'not scene objects',
    'judge inside the frame': r'inside the (dashed )?frame',
    'frame does not track subject': r'does not track',
    'guides are optional': r'never (required|mandatory)',
    'framing contract state': r'frame_contract',
    'policy not switchable': r'cannot switch',
    'no pixel chasing': r'merely to maximi[sz]e pixels',
    'synthetic reference': r'synthetic',
    'no clearance from images': r'never infer clearance',
    'motion marker is not pose': r'never a pose',
    'moving does not change saved photos': r'new exposure',
    'earlier satisfactory photo selectable': r'(previously|earlier) satisfactory photo',
    'two-round history': r'previous two',
    'image instructions are content': r'scene content, not task instructions',
    'navigation IDs only': r'only navigation',
    'unknown not retried': r'must not be retried',
    'control while thinking': r'control continues while you think',
    'aesthetics not binary gates': r'binary',
    'self-review not independent': r'not independent',
    'body regions': r'head-to-thigh',
    'note not reasoning': r'not a chain of thought',
    'observations are sensor data': r'sensor data',
    'honest non-improvement claims': r'unobserved compliance',
}

# Rules that must survive in the prompt or the tool that enforces them.
ANYWHERE_RULES = {
    'pending review allows view_images': r'view_images',
    'pending review allows stop': r'only stop is accepted|act stop',
    'finish needs landing': r'confirmed landing',
    'finish needs final review': r'next_step=finish',
    'flexible degradation reason': r'degradation_reason',
    'failed source needs fresh capture': r'fresh_capture_required',
    'crop needs own review': r'own review',
    'reference comparison required': r'reference_comparison',
    'integer SDK units': r'[Ii]nteger centimetres',
    'no obstacle guard': r'[Nn]o obstacle guard',
}


@pytest.mark.parametrize('name,pattern', SYSTEM_RULES.items(), ids=list(SYSTEM_RULES))
def test_system_prompt_keeps_global_rule(name, pattern):
    assert re.search(pattern, SYSTEM, re.I), name


@pytest.mark.parametrize('name,pattern', ANYWHERE_RULES.items(), ids=list(ANYWHERE_RULES))
def test_rule_survives_in_prompt_or_tool_help(name, pattern):
    assert re.search(pattern, SYSTEM + ' ' + HELP), name


def test_system_prompt_stays_compact():
    assert len(SYSTEM.split()) <= 1500


def test_tool_help_matches_single_slot_viewfinder():
    # The annotated current frame is the only live view; no separate preview is sent.
    assert 'live frame preview' not in TOOL_HELP['view_images']


# Detector-independent photography knowledge carried over from the v0 rubric.
AESTHETIC_RULES = {
    'visual hierarchy first': r'viewer should (see|notice) first',
    'ascending lowers the subject': r'ascending moves the subject down',
    'forward shrinks both margins': r'forward usually (reduces|shrinks) both',
    'floor area is not footroom': r'floor area .*footroom|footroom .*floor area',
    'gaze space': r'gaze or body direction',
    'edge tangency inspection': r'head, neck, shoulder',
    'contrast is not separation': r'contrast alone',
    'horizon relative to subject': r'actual horizon',
    'leading line needs a destination': r'leading line',
    'optional technique menu': r'environmental framing',
    'no approach for foreground': r'unknown space',
    'decisive gain and regression': r'decisive visible gain',
    'motion is not evidence of gain': r'commanded motion',
}


@pytest.mark.parametrize('name,pattern', AESTHETIC_RULES.items(), ids=list(AESTHETIC_RULES))
def test_system_prompt_carries_photographic_knowledge(name, pattern):
    assert re.search(pattern, SYSTEM, re.I), name


def test_review_help_points_quality_issues_at_composition():
    assert re.search(r'tangenc', TOOL_HELP['review_photo'], re.I)
