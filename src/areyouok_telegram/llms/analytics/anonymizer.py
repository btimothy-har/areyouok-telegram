import dspy


class TextAnonymizer(dspy.Signature):
    """Text anonymization"""

    text: str = dspy.InputField(desc="The text to be anonymized, which may contain sensitive information.")
    anonymized_text: str = dspy.OutputField(
        desc="The anonymized text, taking special care to retain the essence and meaning of the original."
    )


class AnonymizationModule(dspy.Module):
    """Module for anonymizing text"""

    def __init__(self):
        self.anonymizer = dspy.ChainOfThought(TextAnonymizer)

    def forward(self, text: str) -> dspy.Prediction:
        """Anonymize the given text."""

        anonymized_text = self.anonymizer(text=text)

        result = dspy.Prediction(
            anonymized_text=anonymized_text.anonymized_text,
        )
        
        # Preserve LLM usage data
        if hasattr(anonymized_text, "get_lm_usage"):
            usage = anonymized_text.get_lm_usage()
            if usage:
                result.set_lm_usage(usage)
        
        return result
