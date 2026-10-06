"""Ponto de entrada do AgentCore Runtime.

O Runtime executa este arquivo (opentelemetry-instrument main.py) numa microVM por sessão.

Entrada (JSON):  {"prompt": "...", "paciente_id": "P-001", "paciente_nome": "Helena Duarte"}
                 Opcional: "prompt_versao": "1" usa essa versão do system prompt, em vez da última publicada.
                 {"aquecer": true} só prepara o agente (Gateway, prompt, cliente do modelo), sem chamar o modelo.
Saída (stream):  eventos SSE, um JSON por linha "data:". O entrypoint é um gerador, e o Runtime envia cada evento
                 assim que ele sai:
                     {"tipo": "etapa", "nome": "..."}        o que o agente começou a fazer: preparo ou modelo (com o loop)
                     {"tipo": "texto", "texto": "..."}       um pedaço da resposta
                     {"tipo": "ferramenta", "nome": "..."}   o modelo pediu uma ferramenta
                     {"tipo": "fim", "resposta": "...", "sessao_id": "...", "rastro": {...}}   (rastro: veja utils/trace.py)
"""
from bedrock_agentcore import BedrockAgentCoreApp

from agent import aquecer, responder
from utils.logs import configurar

configurar()  # o tempo de cada etapa de cada resposta, e os erros, no CloudWatch Logs do Runtime
app = BedrockAgentCoreApp()


@app.entrypoint
async def invocar(payload: dict, context):
    if payload.get("aquecer"):
        yield await aquecer()
        return
    pergunta = (payload.get("prompt") or "").strip()
    if not pergunta:
        yield {"tipo": "fim", "resposta": "Escreva a sua dúvida, por favor."}
        return

    # O Runtime manda o id da sessão no cabeçalho; ele vira o session_id do Memory.
    sessao_id = getattr(context, "session_id", None) or payload.get("sessao_id") or "sessao-local-desenvolvimento-0000000001"
    eventos = responder(
        pergunta=pergunta,
        sessao_id=sessao_id,
        paciente_id=payload.get("paciente_id", "P-001"),
        paciente_nome=payload.get("paciente_nome", ""),
        prompt_versao=str(payload.get("prompt_versao") or ""),
    )
    async for evento in eventos:
        if evento["tipo"] == "fim":
            evento["sessao_id"] = sessao_id
        yield evento


if __name__ == "__main__":
    app.run()
