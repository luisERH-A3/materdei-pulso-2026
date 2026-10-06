"""As instruções do agente: o system prompt, que mora no Bedrock Prompt Management, versionado lá (Módulo 2, prompt como código).

O texto, com tags XML e regras numeradas, não fica mais no código. Aqui o agente só:
    1. busca a versão publicada do prompt (a última, ou a fixada em PROMPT_VERSAO)
    2. preenche as variáveis {{paciente_id}}, {{paciente_nome}} e {{hoje}}

Mudou o prompt? Edite no console do Bedrock e crie uma versão. O agente passa a usá-la em até um minuto,
sem novo deploy. O texto inicial está em infra/completa/template.yaml.
"""
import time
from datetime import date, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

import boto3

from utils import config

_DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
_VALIDADE_S = 60  # por quanto tempo o texto buscado vale, antes de conferir se saiu versão nova
_guardado = {}  # versão pedida -> (validade, texto, versão)


@lru_cache
def _bedrock_agent():
    return boto3.client("bedrock-agent", region_name=config.REGIAO)


def _ultima_versao() -> str:
    """O número da versão publicada mais recente. Versões são imutáveis e numeradas: 1, 2, 3..."""
    paginas = _bedrock_agent().get_paginator("list_prompts").paginate(promptIdentifier=config.PROMPT_ID)
    numeros = [int(p["version"]) for pagina in paginas for p in pagina["promptSummaries"] if p["version"].isdigit()]
    if not numeros:
        raise RuntimeError("O prompt ainda não tem versão publicada. Crie uma no console do Bedrock Prompt Management.")
    return str(max(numeros))


def prompt_publicado(versao: str = "") -> tuple[str, str]:
    """O texto do prompt e a versão dele (por exemplo "v2"), direto do Prompt Management.

    versao vazia = a que estiver fixada em PROMPT_VERSAO ou, sem isso, a última publicada.
    No Prompt Management não existe versão "ativa": quem escolhe a versão é a aplicação, a cada chamada.
    """
    if not config.PROMPT_ID:
        raise RuntimeError("Falta PROMPT_ID no .env. Rode: bash agente-agendamento/demo.sh")
    pedida = versao or config.PROMPT_VERSAO
    validade, texto, usada = _guardado.get(pedida, (0.0, "", ""))
    if time.time() < validade:
        return texto, usada
    numero = pedida or _ultima_versao()
    prompt = _bedrock_agent().get_prompt(promptIdentifier=config.PROMPT_ID, promptVersion=numero)
    variante = next(v for v in prompt["variants"] if v["name"] == prompt["defaultVariant"])
    _guardado[pedida] = (time.time() + _VALIDADE_S, variante["templateConfiguration"]["text"]["text"], f"v{numero}")
    return _guardado[pedida][1:]


def montar_prompt(paciente_id: str, paciente_nome: str = "", versao: str = "", hoje: date | None = None) -> tuple[str, str]:
    """O system prompt desta conversa, com as variáveis preenchidas, e a versão usada."""
    texto, usada = prompt_publicado(versao)
    hoje = hoje or datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    variaveis = {
        "paciente_id": paciente_id,
        "paciente_nome": paciente_nome or "não informado",
        "hoje": f"{_DIAS[hoje.weekday()]}, {hoje:%d/%m/%Y}",
    }
    for nome, valor in variaveis.items():
        texto = texto.replace("{{" + nome + "}}", valor)
    return texto.strip(), usada
