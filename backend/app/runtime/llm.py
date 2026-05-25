from langchain_core.language_models.chat_models import BaseChatModel
from app.config import settings


def get_llm(provider: str = None, model: str = None) -> BaseChatModel:
    provider = provider or settings.DEFAULT_MODEL_PROVIDER
    model = model or settings.DEFAULT_MODEL

    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0.1,
            convert_system_message_to_human=True,
        )
    elif provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=model,
            api_key=settings.GROQ_API_KEY,
            temperature=0.1,
        )
    elif provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=model,
            temperature=0.1,
            format="json",
        )

    raise ValueError(f"Unknown provider: {provider}")
