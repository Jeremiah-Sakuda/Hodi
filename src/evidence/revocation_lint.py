import re

class RevocationLintError(Exception):
    pass

class RevocationLint:
    # 1. Must explicitly state termination.
    TERMINATION_PATTERNS = [
        r"terminate",
        r"revok(e|ed|ation)",
        r"rescind"
    ]
    
    # 2. Must explicitly state the limitation (does not un-train/remove).
    DISCLAIMER_PATTERNS = [
        r"does not imply removal",
        r"does not un-train",
        r"cannot un-train",
        r"does not require removal from existing models",
        r"does not constitute a mandate to unlearn",
        r"does not mean the model will forget"
    ]
    
    # 3. Must NOT make model-removal or un-training claims.
    OVERCLAIM_PATTERNS = [
        r"will be removed from the model",
        r"model will forget",
        r"deletes your data from their system",
        r"will un-train",
        r"unlearn",
        r"erased from the weights",
        r"purge.*from the model"
    ]

    @classmethod
    def check_notice(cls, notice_text: str) -> bool:
        """
        Lints a revocation notice.
        Returns True if it passes. Raises RevocationLintError if it fails.
        """
        text_lower = notice_text.lower()
        
        # Check termination
        if not any(re.search(p, text_lower) for p in cls.TERMINATION_PATTERNS):
            raise RevocationLintError("Notice must explicitly state that the grant is terminated.")
            
        # Check explicit disclaimer (understatement)
        if not any(re.search(p, text_lower) for p in cls.DISCLAIMER_PATTERNS):
            raise RevocationLintError("Notice must contain an explicit disclaimer that revocation does not un-train the model.")
            
        # Check overclaims
        for pattern in cls.OVERCLAIM_PATTERNS:
            if re.search(pattern, text_lower):
                raise RevocationLintError(f"Notice violates invariant: contains model-removal overclaim matching '{pattern}'.")
                
        return True
