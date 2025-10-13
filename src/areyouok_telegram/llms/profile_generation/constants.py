# ruff: noqa: E501

IDENTITY_DESC = """
Core aspects of who the user is, including their preferred name, role in life (e.g., parent, professional, student), and any self-identified characteristics they've shared. This captures how they see themselves and want to be recognized.
"""

PREFERENCES_DESC = """
The user's stated preferences about communication, support style, and interaction patterns. This includes their preferred pace of conversation, depth of engagement, and any specific ways they've indicated they like to be supported or approached.
"""

EMOTIONAL_PATTERNS_DESC = """
Recurring emotional themes, triggers, coping strategies, and patterns in how the user processes and expresses emotions. This includes their typical responses to stress, sources of comfort, and any patterns in their emotional regulation that have emerged over time.
"""

KEY_INFORMATION_DESC = """
Important contextual information about the user's life that provides essential background - relationships, ongoing situations, health considerations, or any other significant details that inform how to provide appropriate support.
"""

PROFILE_UPDATE_DESC = """
A brief summary of what has changed or been learned since the last profile update. This serves as a changelog to track how understanding of the user has evolved. If this is the first profile generation, note that this is the initial profile.
"""

PROFILE_TEMPLATE = """
# User Profile

## Identity
{identity}

## Preferences
{preferences}

## Emotional Patterns
{emotional_patterns}

## Key Information
{key_information}

---
**Profile Update**: {profile_update}
"""

AGENT_INSTRUCTIONS = """
You are a profile synthesis assistant for an empathetic AI companion system.

Your task is to analyze the provided context data and synthesize a comprehensive yet compact user profile.

The profile should:
1. Be concise and information-dense - every sentence should add value
2. Focus on actionable insights that help provide better support
3. Avoid speculation - only include information explicitly provided by the user
4. Use neutral, professional language while maintaining warmth
5. Prioritize recent information over older data when there are conflicts
6. Track what has changed in the profile_update field

When generating the profile:
- Extract core identity markers the user has shared
- Identify communication and support preferences
- Note emotional patterns and coping mechanisms
- Capture key contextual information about their life
- Document what's new or changed since the last profile (if previous profile exists)

If no relevant information exists for a field, use "No information available yet." rather than making assumptions.
"""
