"""O cérebro do agente: o modelo de conversa no Amazon Bedrock, com o guardrail na mesma chamada.

Serverless: não há servidor de modelo, paga-se por token. Trocar de modelo é trocar MODELO_CONVERSA.
"""
from functools import lru_cache

import boto3
from botocore.config import Config

from utils import config


def _guardrail() -> dict:
    """O guardrail é um parâmetro a mais na chamada ao modelo (Módulo 2). Vira o guardrailConfig da Converse API.

    O Bedrock checa a mensagem do paciente antes de o modelo rodar e a resposta antes de ela sair.
    As regras ficam no guardrail (infra/completa/template.yaml), não no código.
    """
    if not config.GUARDRAIL_ID:
        return {}  # sem GUARDRAIL_ID no .env, o agente roda sem os filtros
    return {
        "guardrail_id": config.GUARDRAIL_ID,
        "guardrail_version": config.GUARDRAIL_VERSAO,
        "guardrail_trace": "enabled",  # a resposta traz o que cada proteção encontrou: é o que o painel mostra
        "guardrail_latest_message": True,  # confere a mensagem nova do paciente, não o histórico inteiro de novo
        "guardrail_redact_input_message": "[mensagem retirada pelo guardrail]",  # o que fica na memória se for barrada
    }


def _raciocinio(modelo_id: str) -> dict:
    """O thinking: o modelo raciocina antes de responder. Vai em additionalModelRequestFields da Converse API.

    O campo muda de um fornecedor para o outro:

    Claude (Anthropic)      {"thinking": {"type": "enabled", "budget_tokens": 1024}}
        type                "enabled" liga, "disabled" desliga
        budget_tokens       quanto o modelo pode gastar pensando: no mínimo 1024, e menos que o max_tokens
        o texto do raciocínio volta na resposta e aparece no modo debug, em "Pensa"

    GPT (OpenAI)            {"reasoning": {"effort": "low"}}
        effort              "none", "low", "medium", "high", "xhigh" ou "max": quanto esforço de raciocínio
        o raciocínio volta criptografado: dá para ver que houve, mas não ler

    Aqui o nível é o mais baixo que liga o raciocínio: a tarefa é escolher ferramentas e escrever uma resposta curta.
    Nos testes, níveis mais altos não mudaram as respostas. Quanto mais esforço, mais tokens de output e mais espera.

    Para desligar o thinking, devolva {}.
    """
    if "anthropic" in modelo_id:
        return {"thinking": {"type": "enabled", "budget_tokens": 1024}}
    if "openai.gpt-" in modelo_id and "gpt-oss" not in modelo_id:
        return {"reasoning": {"effort": "low"}}
    return {}  # outros modelos: sem thinking, ou com o raciocínio padrão deles


@lru_cache
def modelo_conversa(modelo_id: str = ""):
    """O modelo do agente, no formato do Strands. Sem argumento, o principal (MODELO_CONVERSA).

    Não passamos temperature nem top_p: ficam os padrões do modelo, e assim o código serve para qualquer um.
    streaming=True usa a ConverseStream API: o texto chega aos pedaços, e a interface escreve enquanto o modelo gera.
    """
    from strands.models import BedrockModel  # import tardio: data/prepare.py não precisa do Strands

    modelo_id = modelo_id or config.MODELO_CONVERSA
    return BedrockModel(
        model_id=modelo_id,
        region_name=config.REGIAO,
        streaming=True,
        max_tokens=4096,  # o thinking do Claude exige um limite de saída maior que o budget_tokens
        additional_request_fields=_raciocinio(modelo_id),
        **_guardrail(),
        # Se o modelo ficar 30 s sem mandar nada, desiste e avisa, em vez de prender a conversa por minutos
        boto_client_config=Config(read_timeout=30, connect_timeout=5, retries={"max_attempts": 2}),
    )


def testar_modelo_conversa(pergunta: str = "Responda só: ok") -> str:
    """Uma chamada direta à Converse API, sem agente. Serve para conferir acesso ao modelo."""
    resposta = boto3.client("bedrock-runtime", region_name=config.REGIAO).converse(
        modelId=config.MODELO_CONVERSA,
        messages=[{"role": "user", "content": [{"text": pergunta}]}],
    )
    blocos = resposta["output"]["message"]["content"]
    return next((b["text"] for b in blocos if "text" in b), "")
