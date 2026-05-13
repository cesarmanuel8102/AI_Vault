import asyncio

from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_core.models import ModelFamily


async def main():
    client = OpenAIChatCompletionClient(
        model="qwen2.5:14b",
        base_url="http://127.0.0.1:11434/v1",
        api_key="ollama",
        model_info={
            "vision": False,
            "function_calling": True,
            "json_output": False,
            "structured_output": False,
            "family": ModelFamily.UNKNOWN,
        },
    )

    agent = AssistantAgent(
        name="assistant",
        model_client=client,
        system_message="Responde en español, claro, técnico y breve."
    )

    result = await agent.run(
        task="Di hola, confirma que AutoGen está conectado a Ollama, indica el modelo usado y resume el estado del entorno en una sola frase."
    )

    print("=" * 80)
    print("TIPO DE RESULTADO:", type(result).__name__)
    print("=" * 80)

    if hasattr(result, "messages"):
        for i, msg in enumerate(result.messages, 1):
            print(f"\\n--- MENSAJE {i} ---")
            print(msg)
    else:
        print(result)

    print("\\n" + "=" * 80)
    print("PRUEBA COMPLETADA")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
