"""A memória do agente: AgentCore Memory, de curto prazo.

O modelo não lembra de nada entre uma mensagem e outra. A cada pergunta, o agente relê aqui a conversa inteira.
"""
from functools import lru_cache

import boto3
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager

from utils import config


@lru_cache
def _sessao_aws() -> boto3.Session:
    """Uma sessão do boto3 para o processo todo: os clientes de cada mensagem saem dela mais rápido."""
    return boto3.Session(region_name=config.REGIAO)


def gerenciador_memoria(sessao_id: str, paciente_id: str) -> AgentCoreMemorySessionManager:
    """actor_id = paciente, session_id = conversa. O histórico fica no AgentCore Memory (7 dias).

    batch_size: as mensagens da resposta são gravadas juntas, no fim, e não uma chamada por mensagem.
    Isso tira cerca de 2 segundos de cada resposta. Quem grava é o close(), chamado em agent.py.
    """
    return AgentCoreMemorySessionManager(
        agentcore_memory_config=AgentCoreMemoryConfig(
            memory_id=config.MEMORIA_ID,
            session_id=sessao_id,
            actor_id=paciente_id,
            batch_size=25,
        ),
        region_name=config.REGIAO,
        boto_session=_sessao_aws(),
    )
