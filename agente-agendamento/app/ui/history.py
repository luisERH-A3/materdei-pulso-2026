"""As conversas salvas: cada conversa do chat vira um arquivo em logs/conversas/, com as mensagens e o rastro.

Assim dá para reabrir uma conversa antiga e ver, no modo debug, o caminho de cada resposta. Como o AgentCore
Memory guarda o histórico por 7 dias, uma conversa reaberta dentro desse prazo também pode continuar de onde parou.

A gravação acontece em dois momentos: quando o paciente envia a mensagem e quando a resposta chega. Abrir outra
conversa, trocar de paciente ou fechar a janela no meio de uma resposta não perde o que já foi escrito.
"""
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from utils import config

PASTA = config.RAIZ / "logs" / "conversas"


def _arquivo(sessao: str) -> Path:
    return PASTA / (re.sub(r"[^A-Za-z0-9_-]", "", sessao) + ".json")


def salvar(sessao: str, paciente: dict, mensagens: list[dict]) -> None:
    """Grava a conversa inteira de novo a cada resposta: são poucas mensagens, e o arquivo nunca fica pela metade."""
    if not mensagens:
        return
    try:
        PASTA.mkdir(parents=True, exist_ok=True)
        arquivo = _arquivo(sessao)
        anterior = json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else {}
        if anterior.get("mensagens") == json.loads(json.dumps(mensagens, default=str)):
            return  # nada mudou: abrir uma conversa antiga não mexe na data nem na ordem do histórico
        agora = datetime.now().isoformat(timespec="seconds")
        conversa = {
            "sessao": sessao,
            "paciente_id": paciente["paciente_id"],
            "paciente_nome": paciente["nome"],
            "agente": "AgentCore Runtime",
            "inicio": anterior.get("inicio", agora),
            "atualizado": agora,
            "mensagens": mensagens,
        }
        temporario = arquivo.with_suffix(".tmp")
        temporario.write_text(json.dumps(conversa, ensure_ascii=False, default=str), encoding="utf-8")
        temporario.replace(arquivo)
    except OSError:  # disco só de leitura: o chat segue, só não fica salvo
        pass


def listar() -> list[dict]:
    """Todas as conversas salvas, da mais recente para a mais antiga: sessão, paciente, título, quando e tamanho."""
    conversas = []
    for arquivo in PASTA.glob("*.json"):
        try:
            conversa = json.loads(arquivo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        perguntas = [m["texto"] for m in conversa["mensagens"] if m["papel"] == "user"]
        conversas.append({
            "sessao": conversa["sessao"],
            "paciente_id": conversa["paciente_id"],
            "paciente_nome": conversa["paciente_nome"],
            "titulo": perguntas[0] if perguntas else "Conversa sem perguntas",
            "atualizado": conversa["atualizado"],
            "perguntas": len(perguntas),
        })
    return sorted(conversas, key=lambda c: c["atualizado"], reverse=True)


def abrir(sessao: str) -> dict | None:
    try:
        return json.loads(_arquivo(sessao).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def apagar(sessao: str) -> None:
    _arquivo(sessao).unlink(missing_ok=True)


def quando(iso: str) -> str:
    """hoje 14:32, ontem 09:10 ou 03/10 18:20."""
    momento = datetime.fromisoformat(iso)
    hoje = datetime.now().date()
    if momento.date() == hoje:
        return f"hoje {momento:%H:%M}"
    if momento.date() == hoje - timedelta(days=1):
        return f"ontem {momento:%H:%M}"
    return f"{momento:%d/%m %H:%M}"
