import asyncio

from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient


async def main():
    client = OpenAIChatCompletionClient(
        model="qwen2.5:14b",
        base_url="http://127.0.0.1:11434/v1",
        api_key="ollama"
    )

    agent = AssistantAgent(
        name="assistant",
        model_client=client,
        system_message="Responde en español, de forma técnica, clara y útil."
    )

    result = await agent.run(
        task="Di hola, confirma que AutoGen está conectado a Ollama, y resume el estado actual del entorno en una frase."
    )

    print(result)


if __name__ == "__main__":
    asyncio.run(main())
