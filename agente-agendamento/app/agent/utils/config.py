"""Configuração: tudo o que muda de um ambiente para outro fica aqui.

Na nuvem, os valores chegam como variáveis de ambiente (definidas em infra/completa/template.yaml).
Na sua máquina, vêm do arquivo .env que infra/completa/deploy.sh grava a partir das saídas da stack.
"""
import os
from pathlib import Path

APP = Path(__file__).resolve().parents[2]  # pasta app/
RAIZ = APP.parent                          # raiz do projeto, onde fica o .env


def _carregar_env(arquivo: Path) -> None:
    """Lê um .env simples (CHAVE=valor). Não sobrescreve variáveis que já existem."""
    if not arquivo.exists():
        return
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            chave, valor = linha.split("=", 1)
            os.environ.setdefault(chave.strip(), valor.strip())


_carregar_env(RAIZ / ".env")

# Região: tudo roda em us-east-1.
REGIAO = os.getenv("REGIAO", "us-east-1")

# Modelos (Módulo 2: escolher o modelo pela tarefa)
MODELO_CONVERSA = os.getenv("MODELO_CONVERSA", "us.openai.gpt-5.6-luna")  # leve, rápido e barato
MODELO_RESERVA = os.getenv("MODELO_RESERVA", "us.anthropic.claude-haiku-4-5-20251001-v1:0")  # entra se o principal falhar
MODELO_EMBEDDING = os.getenv("MODELO_EMBEDDING", "cohere.embed-v4:0")    # in-region em us-east-1
DIMENSAO_EMBEDDING = int(os.getenv("DIMENSAO_EMBEDDING", "1024"))        # 256, 512, 1024 ou 1536

# Dados estruturados (as bases do Excel, convertidas para JSON no S3)
DADOS_BUCKET = os.getenv("DADOS_BUCKET", "")
DADOS_CHAVE = os.getenv("DADOS_CHAVE", "bases/bases.json")

# RAG
VETORES_BUCKET = os.getenv("VETORES_BUCKET", "")
VETORES_INDICE = os.getenv("VETORES_INDICE", "conhecimento")
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))

# AgentCore
MEMORIA_ID = os.getenv("MEMORIA_ID", "")
GATEWAY_URL = os.getenv("GATEWAY_URL", "")
RUNTIME_ARN = os.getenv("RUNTIME_ARN", "")

# System prompt, no Bedrock Prompt Management. PROMPT_VERSAO vazio = a última versão publicada
PROMPT_ID = os.getenv("PROMPT_ID", "")
PROMPT_VERSAO = os.getenv("PROMPT_VERSAO", "")

# Guardrail: o id e a versão publicada. Sem o id, o agente roda sem os filtros de entrada e de saída
GUARDRAIL_ID = os.getenv("GUARDRAIL_ID", "")
GUARDRAIL_VERSAO = os.getenv("GUARDRAIL_VERSAO", "DRAFT")
