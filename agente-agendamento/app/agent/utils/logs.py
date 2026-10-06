"""Registro do agente: a saída padrão do Runtime, que o AgentCore envia ao CloudWatch Logs.

Cada resposta vira uma linha com o tempo de cada etapa. Cada erro vai com o rastro completo.
É o primeiro lugar para olhar quando algo demora ou falha: o grupo /aws/bedrock-agentcore/runtimes/<id>-DEFAULT.
"""
import json
import logging

registro = logging.getLogger("agente")


def configurar() -> None:
    """Liga o registro do agente na saída padrão."""
    registro.setLevel(logging.INFO)
    tela = logging.StreamHandler()
    tela.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    registro.addHandler(tela)


def anotar(evento: str, **campos) -> None:
    """Uma linha no registro: o nome do evento e os campos em JSON."""
    registro.info("%s %s", evento, json.dumps(campos, ensure_ascii=False, default=str))
