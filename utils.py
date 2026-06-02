from langchain_core.callbacks import BaseCallbackHandler

# 1. Create a custom logging handler
class FallbackLoggingHandler(BaseCallbackHandler):
    def on_llm_error(self, error: BaseException, **kwargs) -> None:
        """This runs automatically the second the primary LLM fails."""
        print("\n⚠️ [FALLBACK TRIGGERED] Primary LLM failed with the following error:")
        print(f"👉 ERROR TYPE: {type(error).__name__}")
        print(f"👉 DETAILS: {error}\n")
        print("🔄 Routing request to the backup LLM model now...\n")