# ruff: noqa: E501

IDENTITY_MARKERS_DESC = """
Core aspects of who the user is: preferred name, pronouns, cultural context, roles in life (e.g., parent, professional, student), communication styles, and known triggers. This captures how they see themselves, want to be recognized, and how they prefer to engage. Include cultural or identity-based considerations that inform appropriate support.
"""

STRENGTHS_VALUES_DESC = """
The user's strengths, values, and resources organized around the CHIME recovery framework domains:
- Connectedness: relationships, social connections, sense of belonging
- Hope: aspirations, optimism, belief in possibility
- Identity: sense of self beyond challenges, personal roles and characteristics
- Meaning: purpose, what matters to them, sources of fulfillment
- Empowerment: agency, control over their life, self-efficacy

Document specific examples of how these manifest in their life.
"""

GOALS_OUTCOMES_DESC = """
The user's stated or implied goals across time horizons, in the context of their lived reality:
- Short-term (days to weeks): immediate priorities, current focus areas
- Medium-term (weeks to months): developing skills, habit changes, relationship goals
- Long-term (months to years): life direction, major aspirations, sustained changes

Include any specific outcomes they're working toward or hoping to achieve.
Disregard any goals or outcomes unique to the conversation with the AI Assistant.
"""

EMOTIONAL_PATTERNS_DESC = """
Recurring emotional themes, patterns in how the user processes and expresses emotions:
- Common emotional experiences and triggers
- How they typically respond to stress or challenges
- What coping strategies work effectively for them
- What approaches or interventions don't work well
- Patterns in emotional regulation and expression
- Sources of comfort and stability
"""

SAFETY_PLAN_DESC = """
A safety plan for times of crisis or emergency, following the Stanley-Brown Safety Planning structure:
- Warning signs: thoughts, images, moods, situations, behaviors that indicate a crisis may be developing
- Internal coping strategies: things the user can do on their own to manage distress
- Social settings/people: places and people that provide distraction or positive engagement
- Supportive social network: people the user can reach out to for help
- Professional support: mental health professionals, crisis services, or healthcare providers the user has access to

Note "Not yet established" if the user has not shared sufficient information for any section.
"""

CHANGE_LOG_DESC = """
A brief summary of what has changed or been learned since the last profile update. This serves as a changelog to track how understanding of the user has evolved. If this is the first profile generation, note that this is the initial profile.
"""

PROFILE_TEMPLATE = """
# User Profile

## Identity Markers
{identity_markers}

## Strengths & Values (CHIME Framework)
{strengths_values}

## Goals & Outcomes
{goals_outcomes}

## Emotional Patterns
{emotional_patterns}

## Safety Plan
{safety_plan}
"""

AGENT_INSTRUCTIONS = """
You are a profile synthesis assistant for an empathetic AI companion system.

You will be provided with:
1) The current profile of the user;
2) New context data from the user's recent interactions with the AI companion.

Your task is to analyze the provided context data and synthesize a comprehensive yet compact user profile.
Use the current profile as a starting point, and update it with the new context data.

The profile should:
1. Be concise and information-dense - every sentence should add value
2. Focus on actionable insights that help provide better support
3. Avoid speculation - only include information explicitly provided by the user
4. Use neutral, professional language while maintaining warmth
5. Prioritize recent information over older data when there are conflicts
6. Be contextualized to the user's lived reality and not in the context of the conversation with the AI Assistant

When generating the profile, write the following categories:
- Identity markers (name, pronouns, cultural context, triggers)
- Strengths and values, following the CHIME framework (Connectedness, Hope, Identity, Meaning, Empowerment)
- The user's life goals across short/medium/long-term horizons
- Emotional patterns, especially what works and what doesn't
- Safety plan following Stanley-Brown structure (warning signs, coping strategies, social network, professional support)

If no relevant information exists for a field, use "No information available yet." rather than making assumptions.
For the safety plan, use "Not yet established" for sections where the user has not shared sufficient information.
"""
