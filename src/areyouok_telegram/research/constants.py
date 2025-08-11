RESEARCH_START_INFO = """
You are using the research version of "Are You OK?" Please note the following:

- You need to explicitly start a new session by sending the command `/start`.
- You can only interact with the bot in the context of that session.
- Sessions are automatically ended after {chat_session_timeout_mins} minutes of inactivity.
- You can end a session at any time by sending the command `/end`.
- Upon ending a session, you will be prompted to provide feedback about your experience (if you had bot interactions).
- Your past sessions are not carried over to the next session.

Note that regardless of the version you use, your data and information is still protected:
- Your messages and interactions are deleted within an hour of the session ending. Only summaries of \
    prior interactions are kept.
- Your Telegram identifiers are never stored.
- All stored data (even temporarily) is encrypted at rest.

This session is immediately started, and you can begin interacting with the bot.
If you want to end this session, please send the command `/end`.
"""

RESEARCH_ACTIVE_SESSION_INFO = """
You are currently in an active session. You can continue interacting with the bot.
If you want to end this session, please send the command `/end`.
"""

END_NO_ACTIVE_SESSION = """
You are using the research version of "Are You OK?".
You are not in an active session. Please start a new session by sending the command `/start`.
"""

NO_FEEDBACK_REQUEST = """
Thanks for your interest in "Are You OK?"! Your session is now ended.

You didn't really interact with the bot in this session, so we won't ask for your feedback.

If you want to start a new session, please send the command `/start`.
"""

FEEDBACK_REQUEST = """
Thanks for your interest in "Are You OK?"! Your session is now ended. If you'd like, you may start a new session by \
    sending the command `/start`.

We value your feedback to improve the bot's performance. We would really appreciate it if you could share \
    your thoughts and suggestions at {feedback_url}.

Rest assured that your feedback is provided anonymously, and your chat history is not shared with us.
"""
